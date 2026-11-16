"""Offline tests: no model calls, no audio models. Run: python -X utf8 -m unittest discover -s tests -v"""
import asyncio
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))

import mock_tools_server as srv  # noqa: E402
from llm import first_chunk_end  # noqa: E402
from pipeline import Sim, split_chunks  # noqa: E402
import score  # noqa: E402

SR = 16000


class EnergyVAD:
    """Stand-in for Silero: speech when the frame is loud."""
    def reset(self):
        pass

    def __call__(self, x):
        return 1.0 if np.sqrt(np.mean(x ** 2)) > 0.01 else 0.0


class FakeASR:
    def __init__(self, text):
        self.text = text

    def __call__(self, audio):
        return self.text, 0.1


def fake_tts(text):
    return np.zeros(int(0.2 * SR * max(1, len(text))), np.float32), 0.05   # 0.2 s per character


class FakeLLM:
    """Replies with fixed text after a fixed delay; never calls tools."""
    def __init__(self, text, delay=0.5, first_chunk=0.2):
        self.text, self.delay, self.first, self.calls = text, delay, first_chunk, 0

    async def turn(self, messages, tools):
        self.calls += 1
        return {"content": [{"type": "text", "text": self.text}], "text": self.text, "tool_uses": [],
                "stop_reason": "end_turn", "t_first_text": 0.1, "t_first_chunk": self.first,
                "first_chunk": self.text[: first_chunk_end(self.text) or len(self.text)],
                "t_done": self.delay, "usage": {"input_tokens": 0, "output_tokens": 0}}


def tone(secs):
    t = np.arange(int(secs * SR)) / SR
    return (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def run_sim(segments, llm, asr_text="x", arm="vad"):
    item = {"id": "X", "segments": segments}
    m = {"vad": EnergyVAD(), "asr": FakeASR(asr_text), "tts": fake_tts}
    sim = Sim(item, arm, m, mcp=None, llm=llm, tools=[])
    return asyncio.run(sim.run())


class TestMockTools(unittest.TestCase):
    def setUp(self):
        srv._reset()

    def test_weather_alias_and_error(self):
        r = json.loads(srv.get_weather("Shanghai", "2026-11-17"))
        self.assertEqual((r["city"], r["high_c"]), ("上海", 18))
        self.assertIn("error", json.loads(srv.get_weather("拉萨", "2026-11-17")))
        self.assertIn("error", json.loads(srv.get_weather("上海", "11月17日")))

    def test_create_update_cancel(self):
        mid = json.loads(srv.create_meeting("t", "2026-11-17", "15:00", 60, ["李娜"]))["meeting_id"]
        srv.update_meeting(mid, start_time="16:00")
        self.assertEqual(srv.STATE["meetings"][mid]["start_time"], "16:00")
        self.assertIn("error", json.loads(srv.create_meeting("t", "2026-11-17", "3pm", 60, [])))
        srv.cancel_meeting("M002")
        self.assertNotIn("M002", srv.STATE["meetings"])


class TestChunks(unittest.TestCase):
    def test_first_chunk(self):
        self.assertEqual("好的，我查一下。"[: first_chunk_end("好的，我查一下。")], "好的，我查一下。")
        self.assertEqual("今天广州天气晴，气温"[: first_chunk_end("今天广州天气晴，气温")], "今天广州天气晴，")
        self.assertEqual(first_chunk_end("3.5度"), None)

    def test_short_first_chunk(self):
        # vad-think-short: 2 characters are enough, and a colon closes the chunk; the default rule is unchanged
        cut = lambda t, **k: t[: first_chunk_end(t, **k) or len(t)]
        self.assertEqual(cut("好的，我查一下。"), "好的，我查一下。")
        self.assertEqual(cut("好的，我查一下。", min_chars=2, colon=True), "好的，")
        self.assertEqual(cut("已设置提醒：明天，", min_chars=2, colon=True), "已设置提醒：")
        self.assertEqual(cut("已设置提醒：明天，"), "已设置提醒：明天，")
        self.assertEqual(cut("Sure, it is 10:00 now.", min_chars=2, colon=True), "Sure,")
        self.assertEqual(cut("A meeting at 10:00 AM with Li Na.", min_chars=2, colon=True), "A meeting at 10:00 AM with Li Na.")
        self.assertEqual(cut("Here is the plan: first", min_chars=2, colon=True), "Here is the plan:")

    def test_split_keeps_all_text(self):
        t = "今天广州晴，最高26度。Sure, it is fine."
        self.assertEqual("".join(split_chunks(t)), t)


class TestPipelineTiming(unittest.TestCase):
    def test_reply_latency_and_barge_in(self):
        # user speaks 0.8-2.8 s; agent replies; user interrupts 1.0 s after the agent starts
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "interrupt", "text": "b", "at": {"after_answer_start": 1.0}, "audio": tone(1.0)}]
        tr = run_sim(segs, FakeLLM("这是一个很长的回答，用来测试打断。"))
        first = tr["responses"][0]["first_audio"]
        # 0.55 s silence + 0.1 ASR + 0.2 first chunk + 0.05 TTS after the user stops, within one frame
        self.assertAlmostEqual(first - 2.8, 0.55 + 0.1 + 0.2 + 0.05, delta=0.07)
        self.assertEqual(len(tr["barge_ins"]), 1)
        inter = tr["user_segments"][1]
        self.assertAlmostEqual(inter["start"], first + 1.0, delta=1e-6)
        stop_latency = tr["barge_ins"][0]["t_detect"] - inter["start"]
        self.assertAlmostEqual(stop_latency, 0.2, delta=0.04)      # START_SECS of speech, frame-aligned
        self.assertTrue(any(p["cut"] for p in tr["pieces"]))
        self.assertIn("note", tr["responses"][1])                   # second reply knows it was interrupted

    def test_pause_cancels_reply_before_speaking(self):
        # 1.0 s pause > 0.55 s endpoint; a slow reply (2 s) is cancelled when the user goes on
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)},
                {"role": "continuation", "text": "b", "at": {"after_prev_end": 1.0}, "audio": tone(1.0)}]
        llm = FakeLLM("好的，收到。", delay=2.0, first_chunk=1.8)
        tr = run_sim(segs, llm)
        self.assertEqual(tr["responses"][0]["status"], "cancelled:user_resumed")
        self.assertEqual(tr["responses"][1]["status"], "done")
        self.assertAlmostEqual(tr["responses"][1]["turn_start"], tr["responses"][0]["turn_start"], delta=1e-6)
        played = [p for p in tr["pieces"] if p["end"] > p["start"]]
        self.assertTrue(all(p["resp"] == 1 for p in played))
        self.assertEqual(llm.calls, 2)

    def test_reply_waiting_to_play_is_dropped(self):
        # the reply is complete before the user goes on, but its audio would start only after
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)},
                {"role": "continuation", "text": "b", "at": {"after_prev_end": 1.0}, "audio": tone(1.0)}]
        slow_tts = lambda text: (np.zeros(int(0.2 * SR * max(1, len(text))), np.float32), 0.6)
        item = {"id": "X", "segments": segs}
        m = {"vad": EnergyVAD(), "asr": FakeASR("x"), "tts": slow_tts}
        llm = FakeLLM("好的，收到。", delay=0.3, first_chunk=0.25)
        tr = asyncio.run(Sim(item, "vad", m, mcp=None, llm=llm, tools=[]).run())
        self.assertEqual(tr["responses"][0]["status"], "cancelled:user_resumed_before_playback")
        played = [p for p in tr["pieces"] if p["end"] > p["start"]]
        self.assertTrue(played and all(p["resp"] == 1 for p in played))
        self.assertAlmostEqual(tr["responses"][1]["turn_start"], tr["responses"][0]["turn_start"], delta=1e-6)

    def test_early_reply_in_pause_is_a_barge_in(self):
        # same pause, fast reply: the agent is already talking when the user goes on
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)},
                {"role": "continuation", "text": "b", "at": {"after_prev_end": 1.0}, "audio": tone(1.0)}]
        tr = run_sim(segs, FakeLLM("好的，收到。", delay=2.0, first_chunk=0.2))
        self.assertEqual(tr["responses"][0]["status"], "cancelled:barge_in")
        r = score.score_item({**tr, "final_state": {"meetings": {}, "reminders": []}},
                             {**score.load_cases()["P02"], "expect": {}})
        self.assertFalse(r["interaction"]["no_takeover_in_pause"])
        self.assertTrue(r["premature_llm"])

    def test_scorer_on_simulated_trace(self):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)}]
        tr = run_sim(segs, FakeLLM("明天有两个会，一个是周会，一个是设计评审。"))
        tr["final_state"] = {"meetings": {k: {**v, "title": "x"} for k, v in score.SEED.items()}, "reminders": []}
        r = score.score_item(tr, score.load_cases()["B01"])
        self.assertTrue(r["overlap"])
        self.assertFalse(r["interaction"]["kept_talking"])            # VAD-only barge-in stops on "嗯"
        self.assertTrue(r["task_pass"])


class GrowingASR:
    """First call (the request) returns `first`; later calls return as much of `text` as has been spoken,
    `cps` characters per second of loud audio."""
    def __init__(self, first, text, cps=5.0):
        self.first, self.text, self.cps, self.calls = first, text, cps, 0

    def __call__(self, audio):
        self.calls += 1
        if self.calls == 1:
            return self.first, 0.1
        n = len(audio) // 512
        loud = sum(1 for i in range(n) if np.sqrt(np.mean(audio[i * 512:(i + 1) * 512] ** 2)) > 0.01) * 512 / SR
        return self.text[: int(loud * self.cps)], 0.1


class TestWordsBargeIn(unittest.TestCase):
    def test_rule(self):
        from bargein import content_units
        for t in ["嗯。", "嗯嗯。", "好的。", "Okay.", "嗯，好的", "Mm-hmm, yeah.", "知道了"]:
            self.assertEqual(content_units(t), 0, t)
        for t in ["等一下，改成四点。", "不对，我问的是上海。", "好了，不用说了。", "Sorry, I meant Guangzhou.",
                  "OK 可以了，stop。", "等一"]:
            self.assertGreaterEqual(content_units(t), 2, t)
        self.assertEqual(content_units("停"), 1)                     # one-word commands do not stop it

    def _sim(self, segs, asr, llm):
        item = {"id": "X", "segments": segs}
        m = {"vad": EnergyVAD(), "asr": asr, "tts": fake_tts}
        return asyncio.run(Sim(item, "vad-think-words", m, mcp=None, llm=llm, tools=[]).run())

    def test_backchannel_is_ignored(self):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)}]
        llm = FakeLLM("明天有两个会，一个是周会，一个是设计评审。")
        tr = self._sim(segs, GrowingASR("明天有哪些会议", "嗯。", cps=100), llm)
        self.assertEqual(tr["barge_ins"], [])
        self.assertEqual([h["decision"] for h in tr["held"]], ["ignore"])
        self.assertFalse(any(p["cut"] for p in tr["pieces"]))
        self.assertEqual(llm.calls, 1)                                # the backchannel never reaches the model
        tr["final_state"] = {"meetings": {k: {**v, "title": "x"} for k, v in score.SEED.items()}, "reminders": []}
        r = score.score_item(tr, score.load_cases()["B01"])
        self.assertTrue(r["overlap"])
        self.assertTrue(r["interaction"]["kept_talking"])

    def test_interruption_waits_for_two_units(self):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "interrupt", "text": "b", "at": {"after_answer_start": 1.0}, "audio": tone(1.5)}]
        tr = self._sim(segs, GrowingASR("x", "等一下改成四点"), FakeLLM("这是一个很长的回答，用来测试打断。"))
        self.assertEqual(len(tr["barge_ins"]), 1)
        b = tr["barge_ins"][0]
        self.assertEqual(b["by"], "words")
        self.assertEqual(b["text"], "等一")
        inter = tr["user_segments"][1]
        # 0.2 s to trigger, then checks every 0.16 s with 0.1 s of compute: "等" twice, "等一" on the third
        self.assertAlmostEqual(b["t_detect"] - inter["start"], 0.65, delta=0.05)
        self.assertEqual(tr["held"][0]["decision"], "stop")
        self.assertEqual(len(tr["held"][0]["checks"]), 3)
        self.assertIn("note", tr["responses"][1])

    def test_held_speech_read_in_turn_language(self):
        # lang arm: held speech goes to the recognizer fixed to the language of the user's last turn
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)}]
        for request, lang in (("明天有哪些会议？", "zh"), ("What meetings do I have?", "en")):
            m = {"vad": EnergyVAD(), "asr": FakeASR(request), "asr_zh": FakeASR("嗯。"),
                 "asr_en": FakeASR("Next week."), "tts": fake_tts}
            item = {"id": "X", "segments": segs}
            tr = asyncio.run(Sim(item, "vad-think-words-lang", m, mcp=None,
                                 llm=FakeLLM("明天有两个会，一个是周会，一个是设计评审。"), tools=[]).run())
            self.assertEqual(tr["held"][0]["lang"], lang)
            self.assertEqual(tr["held"][0]["decision"], "ignore" if lang == "zh" else "stop")


class TestMinDuration(unittest.TestCase):
    def _sim(self, arm, segs, asr):
        item = {"id": "X", "segments": segs}
        m = {"vad": EnergyVAD(), "asr": asr, "tts": fake_tts}
        return asyncio.run(Sim(item, arm, m, mcp=None, llm=FakeLLM("这是一个很长的回答，用来测试打断，还要再长一点。"),
                               tools=[]).run())

    def test_short_sound_read_as_two_words_is_ignored(self):
        # 0.4 s of sound read as two words: the words arm stops, the dur arm (0.5 s minimum) keeps talking
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)}]
        words = self._sim("vad-think-words", segs, GrowingASR("x", "Me you", cps=100))
        dur = self._sim("vad-think-words-dur", segs, GrowingASR("x", "Me you", cps=100))
        self.assertEqual(len(words["barge_ins"]), 1)
        self.assertEqual(dur["barge_ins"], [])
        self.assertEqual(dur["held"][0]["decision"], "ignore")

    def test_words_first_then_duration(self):
        # the first read already has two units; the stop waits until 0.5 s of speech
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "interrupt", "text": "b", "at": {"after_answer_start": 1.0}, "audio": tone(1.5)}]
        tr = self._sim("vad-think-words-dur", segs, GrowingASR("x", "等一下改成四点", cps=20))
        b = tr["barge_ins"][0]
        inter = tr["user_segments"][1]
        self.assertAlmostEqual(b["t_detect"] - inter["start"], 0.5, delta=0.04)
        self.assertGreaterEqual(tr["held"][0]["speech"], 0.5 - 1e-6)


class TestPauseResume(unittest.TestCase):
    REPLY = "这是一个很长的回答，用来测试打断，还要再长一点。"

    def _sim(self, segs, asr):
        item = {"id": "X", "segments": segs}
        tts = lambda text: (np.full(int(0.2 * SR * max(1, len(text))), 0.05, np.float32), 0.05)
        m = {"vad": EnergyVAD(), "asr": asr, "tts": tts}
        llm = FakeLLM(self.REPLY)
        sim = Sim(item, "vad-think-pause", m, mcp=None, llm=llm, tools=[])
        return asyncio.run(sim.run()), sim, llm

    def test_backchannel_pauses_then_resumes(self):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)}]
        tr, sim, llm = self._sim(segs, GrowingASR("明天有哪些会议", "Me you", cps=100))
        b, bc = tr["barge_ins"][0], tr["user_segments"][1]
        self.assertEqual((len(tr["barge_ins"]), b["by"], b["decision"]), (1, "pause", "resume"))
        self.assertAlmostEqual(b["t_detect"] - bc["start"], 0.2, delta=0.04)   # silent as fast as vad-think
        # verdict after 0.4 s of sound + 0.55 s of silence + 0.1 s read; resumed at once
        self.assertAlmostEqual(b["gap"], 0.4 + 0.55 + 0.1 - 0.2, delta=0.07)
        self.assertEqual(b["t_resume"], b["t_decide"])
        self.assertEqual(llm.calls, 1)                                # the backchannel never reaches the model
        self.assertEqual(score.heard_text(tr), self.REPLY)             # every character once, in order
        played = [p for p in tr["pieces"] if p["end"] > p["start"]]
        self.assertAlmostEqual(sum(p["end"] - p["start"] for p in played), 0.2 * len(self.REPLY), delta=0.01)
        self.assertFalse(any(p["start"] < b["t_resume"] and p["end"] > b["t_detect"] + 1e-6 for p in played))
        s, e = int(round(b["t_detect"] * SR)) + 1, int(round(b["t_resume"] * SR)) - 1
        self.assertEqual(float(np.abs(sim.agent_track[s:e]).max()), 0.0)    # the recording is silent too
        self.assertAlmostEqual(float(sim.agent_track.sum()) / 0.05 / SR, 0.2 * len(self.REPLY), delta=0.01)
        tr["final_state"] = {"meetings": {k: {**v, "title": "x"} for k, v in score.SEED.items()}, "reminders": []}
        r = score.score_item(tr, score.load_cases()["B01"])
        self.assertFalse(r["interaction"]["kept_talking"])            # a pause is a stop under the frozen rule
        self.assertTrue(r["task_pass"])

    def test_interruption_pauses_then_cancels(self):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(2.0)},
                {"role": "interrupt", "text": "b", "at": {"after_answer_start": 1.0}, "audio": tone(1.5)}]
        tr, sim, llm = self._sim(segs, GrowingASR("x", "等一下改成四点", cps=20))
        b, it = tr["barge_ins"][0], tr["user_segments"][1]
        self.assertEqual((len(tr["barge_ins"]), b["decision"]), (1, "stop"))
        self.assertAlmostEqual(b["t_detect"] - it["start"], 0.2, delta=0.04)
        self.assertAlmostEqual(b["t_decide"] - it["start"], 0.5, delta=0.04)    # the dur rule's verdict
        first = [p for p in tr["pieces"] if p["resp"] == 0]
        self.assertEqual(sum(max(0.0, p["end"] - max(p["start"], b["t_detect"])) for p in first), 0.0)
        self.assertTrue(b["heard"] and tr["responses"][1]["note"].endswith(b["heard"]))
        self.assertEqual(llm.calls, 2)


class ScriptedLLM:
    """Plays back a fixed list of model turns: ("tool", name, input) or ("text", text)."""
    def __init__(self, turns):
        self.turns, self.calls, self.seen = list(turns), 0, []

    async def turn(self, messages, tools):
        self.seen.append(list(messages))              # a copy: the pipeline keeps appending to its list
        kind, *rest = self.turns[self.calls]
        self.calls += 1
        base = {"stop_reason": "end_turn", "t_first_text": 0.1, "t_first_chunk": 0.2, "t_done": 0.5,
                "usage": {"input_tokens": 0, "output_tokens": 0}}
        if kind == "tool":
            tu = {"id": f"tu{self.calls}", "name": rest[0], "input": rest[1]}
            return {**base, "content": [{"type": "tool_use", **tu}], "text": "", "tool_uses": [tu], "first_chunk": "",
                    "stop_reason": "tool_use"}
        text = rest[0]
        return {**base, "content": [{"type": "text", "text": text}], "text": text, "tool_uses": [],
                "first_chunk": text[: first_chunk_end(text) or len(text)]}


class FakeMCP:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append(name)
        item = type("C", (), {"text": '{"status": "cancelled"}'})()
        return type("R", (), {"content": [item], "is_error": False})()


class TestConfirmGate(unittest.TestCase):
    TURNS = [("tool", "cancel_meeting", {"meeting_id": "M002"}), ("text", "确定要取消明天下午两点的设计评审吗？"),
             ("tool", "cancel_meeting", {"meeting_id": "M002"}), ("text", "已取消。")]

    def _sim(self, arm):
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.5)},
                {"role": "answer", "text": "对，取消吧。", "at": {"after_agent_end": 0.6}, "audio": tone(0.8)}]
        llm, mcp = ScriptedLLM(self.TURNS), FakeMCP()
        m = {"vad": EnergyVAD(), "asr": FakeASR("x"), "tts": fake_tts}
        tr = asyncio.run(Sim({"id": "X", "segments": segs}, arm, m, mcp=mcp, llm=llm, tools=[]).run())
        return tr, llm, mcp

    def test_cancel_waits_for_the_users_answer(self):
        tr, llm, mcp = self._sim("vad-think-confirm")
        self.assertEqual(mcp.calls, ["cancel_meeting"])                         # held once, run once
        self.assertEqual([s["kind"] for s in tr["responses"][0]["steps"] if "tool" in s["kind"]], ["held_tool"])
        run = [s for s in tr["responses"][1]["steps"] if s["kind"] == "tool"]
        answer = next(s for s in tr["user_segments"] if s["role"] == "answer")
        self.assertEqual(len(run), 1)
        self.assertGreater(run[0]["start"], answer["start"])
        held = llm.seen[1][-1]["content"][0]                                     # what the model got back
        self.assertTrue(held["is_error"] and held["content"].startswith("未执行"))

    def test_other_arms_run_it_at_once(self):
        tr, llm, mcp = self._sim("vad-think")
        self.assertEqual([s["kind"] for s in tr["responses"][0]["steps"] if "tool" in s["kind"]], ["tool"])


class TestPersonalVADArm(unittest.TestCase):
    def test_speaker_set_after_first_turn(self):
        # pvad arm: the first utterance's embedding is set once, its compute time after the first turn end
        class SpeakerVAD(EnergyVAD):
            def __init__(self):
                self.set = []

            def set_speaker(self, emb):
                self.set.append(list(emb))
        vad = SpeakerVAD()
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.5)},
                {"role": "answer", "text": "b", "at": {"after_agent_end": 0.6}, "audio": tone(0.8)}]
        m = {"vad": vad, "asr": FakeASR("x"), "tts": fake_tts, "pvad_emb": {"X": [0.5] * 192}, "pvad_secs": 0.27}
        tr = asyncio.run(Sim({"id": "X", "segments": segs}, "vad-think-pvad", m, mcp=None,
                             llm=FakeLLM("好的。"), tools=[]).run())
        ev = [e for e in tr["events"] if e["ev"] == "speaker_set"]
        self.assertEqual((len(ev), len(vad.set)), (1, 1))
        self.assertAlmostEqual(ev[0]["t"], tr["responses"][0]["t_endpoint"] + 0.27, delta=0.04)
        self.assertEqual(len(tr["responses"]), 2)                                 # the second turn is still heard

    def test_pvad_wrapper_streams_10ms_windows(self):
        from audio import PersonalVAD
        v = PersonalVAD()
        x = (0.05 * np.sin(np.arange(16000) / 3)).astype(np.float32)
        ps = [v(x[k * 512:(k + 1) * 512]) for k in range(len(x) // 512)]
        self.assertEqual(len(v.buf), (len(ps) * 512) % 160)                     # leftover below one window
        self.assertTrue(all(0.0 <= p <= 1.0 for p in ps))
        v.set_speaker(np.ones(192))
        self.assertEqual(v.emb.shape, (1, 192))


class TestCombo(unittest.TestCase):
    def test_all_changes_together(self):
        # combo arm: speaker embedding set after the first turn, the cancel waits for the answer, and a short
        # sound over the agent's question pauses it and resumes it (the sound is not the user's verdict)
        class SpeakerVAD(EnergyVAD):
            def set_speaker(self, emb):
                self.emb = emb
        turns = [("tool", "cancel_meeting", {"meeting_id": "M002"}),
                 ("text", "确定要取消明天下午两点的设计评审吗？请说确定或者不要。"),
                 ("tool", "cancel_meeting", {"meeting_id": "M002"}), ("text", "已取消。")]
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.5)},
                {"role": "backchannel", "text": "嗯。", "at": {"after_answer_start": 1.0}, "audio": tone(0.4)},
                {"role": "answer", "text": "对，取消吧。", "at": {"after_agent_end": 0.6}, "audio": tone(0.8)}]
        m = {"vad": SpeakerVAD(), "asr": GrowingASR("x", "Me you", cps=100), "tts": fake_tts,
             "pvad_emb": {"X": [0.1] * 192}, "pvad_secs": 0.27}
        mcp = FakeMCP()
        tr = asyncio.run(Sim({"id": "X", "segments": segs}, "vad-think-combo", m, mcp=mcp,
                             llm=ScriptedLLM(turns), tools=[]).run())
        self.assertEqual(sum(e["ev"] == "speaker_set" for e in tr["events"]), 1)
        self.assertEqual([b["decision"] for b in tr["barge_ins"]], ["resume"])
        self.assertEqual(mcp.calls, ["cancel_meeting"])
        answer = next(s for s in tr["user_segments"] if s["role"] == "answer")
        run = [s for r in tr["responses"] for s in r["steps"] if s["kind"] == "tool"]
        self.assertGreater(run[0]["start"], answer["start"])


class TestBriefConfirm(unittest.TestCase):
    def test_brief_question_is_asked_for(self):
        # combo-brief: the held cancel tells the model to ask briefly; combo keeps the original wording
        class SpeakerVAD(EnergyVAD):
            def set_speaker(self, emb):
                pass
        turns = [("tool", "cancel_meeting", {"meeting_id": "M002"}), ("text", "取消明天下午两点的设计评审吗？"),
                 ("tool", "cancel_meeting", {"meeting_id": "M002"}), ("text", "已取消。")]
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.5)},
                {"role": "answer", "text": "对。", "at": {"after_agent_end": 0.6}, "audio": tone(0.5)}]
        for arm, word in (("vad-think-combo-brief", "很短"), ("vad-think-combo", "复述")):
            llm = ScriptedLLM(turns)
            m = {"vad": SpeakerVAD(), "asr": FakeASR("x"), "tts": fake_tts, "pvad_emb": {"X": [0.1] * 192},
                 "pvad_secs": 0.27}
            asyncio.run(Sim({"id": "X", "segments": segs}, arm, m, mcp=FakeMCP(), llm=llm, tools=[]).run())
            self.assertIn(word, llm.seen[1][-1]["content"][0]["content"])


class TestSpokeFirst(unittest.TestCase):
    def test_reply_started_after_the_user_went_on_is_merged(self):
        # the user goes on at 2.60 s; the reply's first sound is at about 2.70 s; the onset is detected at 2.80 s.
        # combo-merge keeps one turn (reply dropped as unheard); combo splits it into two turns
        class SpeakerVAD(EnergyVAD):
            def set_speaker(self, emb):
                pass
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)},
                {"role": "continuation", "text": "b", "at": {"after_prev_end": 0.8}, "audio": tone(1.5)}]
        for delay in (0.5, 1.5):                       # reply text complete before / after the verdict
            got = {}
            for arm in ("vad-think-combo-merge", "vad-think-combo"):
                m = {"vad": SpeakerVAD(), "asr": GrowingASR("x", "明天上午十点开会", cps=20), "tts": fake_tts,
                     "pvad_emb": {"X": [0.1] * 192}, "pvad_secs": 0.27}
                tr = asyncio.run(Sim({"id": "X", "segments": segs}, arm, m, mcp=None,
                                     llm=FakeLLM("好的，收到。", delay=delay), tools=[]).run())
                cont = tr["user_segments"][1]
                self.assertLess(cont["start"], tr["responses"][0]["first_audio"])    # the user went on first
                got[arm] = tr
            merged, split = got["vad-think-combo-merge"], got["vad-think-combo"]
            self.assertTrue(any(e["ev"] == "user_spoke_first" for e in merged["events"]), delay)
            self.assertAlmostEqual(merged["responses"][-1]["turn_start"], merged["responses"][0]["turn_start"],
                                   delta=1e-6)
            self.assertNotIn("note", merged["responses"][-1])                         # nothing counted as heard
            self.assertGreater(split["responses"][-1]["turn_start"], split["user_segments"][1]["start"] - 0.35)


class TestStreamTTS(unittest.TestCase):
    def test_bounds_match_the_spoken_chunks(self):
        # chunk ends found while the text streams in equal the chunks spoken from the final text
        from llm import new_bounds
        for first_min, colon in ((4, False), (2, True)):
            text, pos, ends = "", 0, []
            for delta in ["好的", "，明天上", "海有小雨，", "最高十八度", "。另外：", "记得带伞"]:
                text += delta
                for e in new_bounds(text, pos, first_min, colon):
                    pos = e
                    ends.append(e)
            first = text[: first_chunk_end(text, first_min, colon) or len(text)]
            spoken = [first] + split_chunks(text[len(first):])
            cum = [sum(len(c) for c in spoken[:i + 1]) for i in range(len(spoken))]
            self.assertEqual(ends + ([len(text)] if pos < len(text) else []), cum)

    def test_later_chunks_start_when_their_text_arrives(self):
        class SpeakerVAD(EnergyVAD):
            def set_speaker(self, emb):
                pass

        class StreamLLM(FakeLLM):
            async def turn(self, messages, tools):
                r = await super().turn(messages, tools)
                r.update(first_chunk="好的，", t_first_chunk=0.2, t_done=3.0,
                         chunk_bounds=[(0.2, 3), (0.6, 11), (3.0, len(self.text))])
                return r
        text = "好的，明天上海有小雨，最高十八度。"
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)}]
        starts = {}
        for arm in ("vad-think-combo-stream", "vad-think-combo"):
            m = {"vad": SpeakerVAD(), "asr": FakeASR("x"), "tts": fake_tts, "pvad_emb": {"X": [0.1] * 192},
                 "pvad_secs": 0.27}
            tr = asyncio.run(Sim({"id": "X", "segments": segs}, arm, m, mcp=None, llm=StreamLLM(text), tools=[]).run())
            ps = sorted((p for p in tr["pieces"] if p["resp"] == 0), key=lambda p: p["start"])
            self.assertEqual([p["text"] for p in ps], ["好的，", "明天上海有小雨，", "最高十八度。"])
            starts[arm] = ps[1]["start"] - tr["responses"][0]["t_endpoint"]
        # chunk 2's text is complete at 0.6 s, not at 3.0 s: it plays right after "好的，" instead of waiting
        self.assertLess(starts["vad-think-combo-stream"], starts["vad-think-combo"] - 1.5)


class TestUnspeakableChunk(unittest.TestCase):
    def test_empty_audio_chunk_does_not_crash(self):
        # the agent's voice returns no audio for a chunk such as a lone "）"; the reply still plays
        tts = lambda text: (np.zeros(0, np.float32), 0.05) if text.strip() == "）" else fake_tts(text)
        segs = [{"role": "request", "text": "a", "at": {"abs": 0.8}, "audio": tone(1.0)}]
        item = {"id": "X", "segments": segs}
        m = {"vad": EnergyVAD(), "asr": FakeASR("x"), "tts": tts}
        tr = asyncio.run(Sim(item, "vad", m, mcp=None, llm=FakeLLM("明天有会。）"), tools=[]).run())
        self.assertEqual(tr["responses"][0]["status"], "done")
        self.assertTrue(any(p["end"] > p["start"] for p in tr["pieces"]))


class TestSayMinutes(unittest.TestCase):
    def test_only_the_minutes_arm_changes_the_prompt(self):
        import hashlib
        from config import ARMS
        from llm import SAY_MINUTES, SYSTEM, system_prompt
        # the prompt every earlier run used, byte for byte
        self.assertEqual(hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()[:12], "e759c7ab9b22")
        self.assertEqual(system_prompt(False), SYSTEM)
        self.assertEqual(system_prompt(True), SYSTEM + "\n" + SAY_MINUTES)
        on = [a for a, c in ARMS.items() if c.get("say_minutes")]
        self.assertEqual(on, ["vad-think-combo-minutes", "vad-think-combo-plus"])
        base = {k: v for k, v in ARMS["vad-think-combo-minutes"].items() if k != "say_minutes"}
        self.assertEqual(base, ARMS["vad-think-combo"])


class TestComboPlus(unittest.TestCase):
    def test_plus_is_combo_with_the_four_follow_ups(self):
        from config import ARMS
        added = {"confirm_brief": True, "spoke_first": True, "stream_tts": True, "say_minutes": True}
        self.assertEqual(ARMS["vad-think-combo-plus"], {**ARMS["vad-think-combo"], **added})
        for arm, key in (("vad-think-combo-brief", "confirm_brief"), ("vad-think-combo-merge", "spoke_first"),
                         ("vad-think-combo-stream", "stream_tts"), ("vad-think-combo-minutes", "say_minutes")):
            self.assertEqual(ARMS[arm], {**ARMS["vad-think-combo"], key: True})   # each tested alone first


class TestScorer(unittest.TestCase):
    def test_self_check(self):
        self.assertTrue(score.self_check())

    def test_expected_meetings(self):
        want = score.expected_meetings({"change": {"M001": {"start_time": "11:00"}}, "remove": ["M002"]})
        self.assertEqual(len(want), 2)
        self.assertIn(("2026-11-17", "11:00", 60, ("张伟", "李娜", "王强")), want)


if __name__ == "__main__":
    unittest.main()
