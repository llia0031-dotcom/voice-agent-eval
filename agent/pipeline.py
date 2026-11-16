"""Cascaded voice agent (VAD -> ASR -> Claude with MCP tools -> TTS) run against a scripted user.

Time model. A virtual clock moves through the microphone signal in 32 ms frames. Listening work
(VAD, Smart Turn) runs frame by frame. When the agent decides the user has finished, each step of
the reply (ASR, each Claude request, each tool call, each TTS chunk) really runs on this machine and
its measured wall-clock time is added to the virtual clock. Between steps the clock catches up frame
by frame, so a user who starts talking again before or during the reply is heard at the right time.
The microphone holds only the user's voice plus noise: echo cancellation is assumed to be perfect.
"""
import re
import time

import numpy as np

from bargein import content_units
from config import ARMS, FRAME, MAX_TURN_SECS, SR, START_SECS, VAD_OFF, VAD_ON
from llm import first_chunk_end, tool_result_block


def split_chunks(text: str) -> list[str]:
    """Cut text into speakable chunks at punctuation (same rule as the first chunk)."""
    out = []
    while text.strip():
        k = first_chunk_end(text) or len(text)
        out.append(text[:k])
        text = text[k:]
    return out

T_MAX = 80.0
FDUR = FRAME / SR
PRE_ROLL = 0.3          # audio kept before the detected speech onset when a turn is sent to ASR
IDLE_END = 2.5          # stop the simulation this long after everything has gone quiet
ANCHOR_TIMEOUT = 10.0   # a reactive user segment plays anyway if the agent never speaks
# confirm arm: what the model gets instead of running a tool that needs the user's spoken approval
CONFIRM_FIRST = ("未执行：这个操作会删除数据，必须先得到用户确认。请用一句话向用户复述要取消的会议（日期、时间、名称），"
                 "问用户是否确认，然后等用户回答。用户在下一句话里明确同意后，再调用这个工具。")
# confirm_brief: the same, asking for a brief and direct question (Bixby's guidance for confirmation moments)
CONFIRM_BRIEF = ("未执行：这个操作会删除数据，必须先得到用户确认。请只用一句很短的话问用户是否确认，只说会议的日期、"
                 "时间和名称，不要念参会人，比如“取消明天下午两点的设计评审吗？”。然后等用户回答。"
                 "用户在下一句话里明确同意后，再调用这个工具。")


class Cancelled(Exception):
    pass


class Sim:
    def __init__(self, item, arm, m, mcp, llm, tools, oracle=False):
        self.item, self.arm, self.cfg = item, arm, ARMS[arm]
        self.m, self.mcp, self.llm, self.tools = m, mcp, llm, tools
        m["vad"].reset()                           # no state carried over from the previous item
        n = int(T_MAX * SR)
        self.mic = np.zeros(n, np.float32)
        if item.get("noise_audio") is not None:
            nz = item["noise_audio"]
            reps = int(np.ceil(n / len(nz)))
            self.mic += np.tile(nz, reps)[:n]
        self.agent_track = np.zeros(n, np.float32)
        self.segs = item["segments"]               # each has "audio", "text", "at", "role"
        self.placed = [None] * len(self.segs)      # (start, end) per user segment
        self.f = 0
        self.t = 0.0
        self.speech = False
        self.speech_run = 0.0
        self.silence_run = 0.0
        self.onset_fired = False
        self.in_turn = False
        self.turn_start = None
        self.computing = False
        self.smart_checked = False
        self.pieces = []                           # agent speech: dict(start, end, text, resp)
        self.history = []
        self.pending_note = None                   # what the user heard before interrupting
        self.trace = {"item": item["id"], "arm": arm, "turns": [], "responses": [], "barge_ins": [],
                      "smart_checks": [], "cancels": [], "user_segments": [], "events": [], "held": []}
        self.cancel_reason = None
        self.hold = None                           # words arm: user speech heard while the agent talks, not yet judged
        self.pause = None                          # pause arm: the reply paused at that speech, waiting for the verdict
        self.confirm_waiting = False               # confirm arm: a held tool call's question has been put to the user
        self.enroll_at = None                      # pvad arm: when the first utterance's speaker embedding is ready
        self.unheard = False                       # spoke-first rule: the reply being cancelled counts as never heard
        self._place_ready()

    # ---------- scripted user ----------
    def _put_user(self, i, start):
        a = self.segs[i]["audio"]
        s = int(round(start * SR))
        e = min(len(self.mic), s + len(a))
        self.mic[s:e] += a[: e - s]
        self.placed[i] = (start, start + len(a) / SR)
        seg = self.segs[i]
        self.trace["user_segments"].append({"i": i, "role": seg["role"], "text": seg["text"],
                                            "start": round(start, 3), "end": round(start + len(a) / SR, 3),
                                            "anchor": seg.get("_anchor_note", "")})

    def _place_ready(self):
        for i, seg in enumerate(self.segs):
            if self.placed[i] is not None:
                continue
            if i > 0 and self.placed[i - 1] is None:
                return
            at = seg["at"]
            prev_end = self.placed[i - 1][1] if i > 0 else 0.0
            if "abs" in at:
                self._put_user(i, at["abs"])
            elif "after_prev_end" in at:
                self._put_user(i, prev_end + at["after_prev_end"])
            elif "after_answer_start" in at:
                # anchor: start of the agent's answer (its reply after the last tool call), not a short
                # preamble such as "好的，我查一下" spoken while tools run
                starts = [p["start"] for p in self.pieces if p["final"] and p["start"] >= prev_end - 1e-6]
                if starts:
                    self._put_user(i, min(starts) + at["after_answer_start"])
                elif self.t > prev_end + ANCHOR_TIMEOUT:
                    seg["_anchor_note"] = "agent gave no answer; played after timeout"
                    self._put_user(i, self.t + at["after_answer_start"])
                else:
                    return
            elif "after_agent_end" in at:
                after = [p for p in self.pieces if p["start"] >= prev_end - 1e-6]
                busy = (self.computing or self.in_turn or self.hold is not None or self.pause is not None
                        or any(p["end"] > self.t for p in self.pieces))
                if after and not busy:
                    self._put_user(i, max(max(p["end"] for p in after), self.t) + at["after_agent_end"])
                elif not after and not busy and self.t > prev_end + ANCHOR_TIMEOUT:
                    seg["_anchor_note"] = "agent never spoke; played after timeout"
                    self._put_user(i, self.t + at["after_agent_end"])
                else:
                    return
            else:
                raise ValueError(at)

    # ---------- agent speech ----------
    def _speaking(self, t):
        return any(p["start"] <= t < p["end"] for p in self.pieces)

    def _stop_speech(self, t):
        heard = []
        for p in self.pieces:
            if p["end"] <= t:
                continue
            if p["start"] < t:
                frac = (t - p["start"]) / max(1e-6, p["full_end"] - p["start"])
                heard.append(p["text"][: int(len(p["text"]) * frac)])
                p["end"] = t
                p["cut"] = True
            else:
                p["end"] = p["start"]      # never played
                p["cut"] = True
        return heard

    def _heard_text(self, resp_id, step=None):
        out = ""
        for p in self.pieces:
            played = min(p["end"], self.t) - p["start"]          # only what has played by now
            if p["resp"] == resp_id and played > 0 and (step is None or p["step"] == step):
                frac = played / max(1e-6, p["full_end"] - p["start"])
                out += p["text"][: int(round(len(p["text"]) * frac))]
        return out

    # ---------- listening loop ----------
    def _frame(self):
        if self.enroll_at is not None and self.t + 1e-9 >= self.enroll_at:
            self.m["vad"].set_speaker(self.m["pvad_emb"][self.item["id"]])   # from now on: this speaker only
            self.trace["events"].append({"t": round(self.t, 3), "ev": "speaker_set"})
            self.enroll_at = float("inf")              # set once
        x = self.mic[self.f * FRAME:(self.f + 1) * FRAME]
        p = self.m["vad"](x)
        if p >= VAD_ON:
            self.speech = True
        elif p < VAD_OFF:
            self.speech = False
        self.f += 1
        self.t = self.f * FDUR
        if self.speech:
            self.speech_run += FDUR
            self.silence_run = 0.0
        else:
            self.silence_run += FDUR
            self.speech_run = 0.0
            self.onset_fired = False
            self.smart_checked = False if self.silence_run <= FDUR + 1e-9 else self.smart_checked

    def advance(self, t_target, allow_endpoint):
        """Process frames up to t_target. Returns ('onset', t) or ('endpoint', t) or None."""
        while self.t + 1e-9 < t_target and self.t < T_MAX - FDUR:
            if allow_endpoint and self._quiet():
                return None
            self._frame()
            self._place_ready()
            if self.speech and not self.onset_fired and self.speech_run >= START_SECS - 1e-9:
                self.onset_fired = True
                onset = self.t - self.speech_run
                if self.hold is not None:
                    pass                                   # the held utterance goes on after a short gap
                elif self.cfg.get("barge_min_units") and (self.pause is not None or self._agent_talking()):
                    if self.cfg.get("pause"):
                        if self.pause is None:
                            self._pause(onset)             # stop the sound now, judge the words while paused
                        else:
                            self.pause["resume_at"] = None  # new speech while paused: wait for its verdict
                    self.hold = {"onset": onset, "next_check": self.t, "due": None, "checks": [],
                                 "speech": self.speech_run, "f": self.f}
                else:
                    ev = self._user_onset(onset)
                    if ev:
                        return ev
            if self.hold is not None:
                ev = self._hold_step()
                if ev:
                    return ev
            if (self.pause is not None and self.hold is None and self.pause["resume_at"] is not None
                    and self.t + 1e-9 >= self.pause["resume_at"]):
                self._resume()
            if allow_endpoint and self.in_turn and not self.computing:
                ep = self._endpoint_check()
                if ep is not None:
                    return ("endpoint", ep)
        return None

    def _user_onset(self, onset, by=None):
        """React to user speech that counts: stop the agent, cancel or resume a reply, or start a turn."""
        if self._speaking(self.t):
            rid = next((p["resp"] for p in self.pieces if p["start"] <= self.t < p["end"]), None)
            if self._spoke_first(rid, onset):
                self._stop_speech(self.t)
                return self._merge_resumed(rid, onset)
            heard = self._stop_speech(self.t)
            b = {"t_detect": round(self.t, 3), "onset_vad": round(onset, 3), "heard": "".join(heard)}
            if by:
                b.update(by)
            self.trace["barge_ins"].append(b)
            self.cancel_reason = "barge_in"
            self.pending_note = self.pending_note_for_barge()
            self._start_turn(onset, keep=False)
            return ("onset", self.t)
        if self.computing:
            heard = self._heard_text(len(self.trace["responses"]) - 1)
            if by and heard:
                # the agent spoke and went quiet while the words were being judged: the user is cutting in
                self.cancel_reason = "barge_in"
                self.pending_note = heard
                self._start_turn(onset, keep=False)
                return ("onset", self.t)
            self.cancel_reason = "user_resumed"
            self._start_turn(onset, keep=True)
            return ("onset", self.t)
        pend = [p for p in self.pieces if p["start"] >= self.t and p["end"] > p["start"]]
        if pend:
            # the reply is ready but has not started to play: drop it, as a real player would
            self._cancel_pending(pend[0]["resp"], onset)
            return ("onset", self.t)
        if not self.in_turn:
            self._start_turn(onset, keep=False)
            self.trace["events"].append({"t": round(self.t, 3), "ev": "turn_start", "onset": round(onset, 3)})
        return None

    # ---------- words arm: judge speech heard while the agent talks ----------
    def _agent_talking(self):
        """Playing now, or between two chunks of a reply that has already started to play."""
        if self._speaking(self.t):
            return True
        pend = [p for p in self.pieces if p["start"] >= self.t and p["end"] > p["start"]]
        return bool(pend) and bool(self._heard_text(pend[0]["resp"]))

    def _hold_step(self):
        """One ASR worker re-reads the held speech every barge_check_every seconds (like interim results of a
        streaming recognizer). A result counts once its compute time has passed on the virtual clock."""
        h = self.hold
        if h["f"] != self.f:                       # voiced time of the held stretch (dur arm)
            h["f"] = self.f
            h["speech"] += FDUR if self.speech else 0.0
        long_enough = h["speech"] + 1e-9 >= self.cfg.get("barge_min_speech", 0.0)
        if h["due"] is not None and self.t + 1e-9 >= h["due"]["t"]:
            c, h["due"] = h["due"], None
            h["checks"].append(c)
            if c["units"] >= self.cfg["barge_min_units"] and long_enough:
                return self._hold_release(c, stop=True)
            if c["final"]:
                return self._hold_release(c, stop=False)
        elif h["checks"] and h["checks"][-1]["units"] >= self.cfg["barge_min_units"] and long_enough:
            return self._hold_release(h["checks"][-1], stop=True)   # the words came first, now the duration
        if h["due"] is None:
            final = ((not self.speech and self.silence_run >= self.cfg["endpoint_silence"] - 1e-9)
                     or self.t - h["onset"] > MAX_TURN_SECS)
            if final or self.t + 1e-9 >= h["next_check"]:
                audio = self.mic[max(0, int((h["onset"] - PRE_ROLL) * SR)): int(self.t * SR)]
                lang = self._turn_language() if self.cfg.get("hold_lang") else None
                text, d = self.m[f"asr_{lang}" if lang else "asr"](audio)
                h["due"] = {"t_start": round(self.t, 3), "t": self.t + d, "text": text,
                            "units": content_units(text), "final": final, "lang": lang or "auto"}
                h["next_check"] = self.t + self.cfg["barge_check_every"]
        return None

    def _turn_language(self):
        """zh if the user's last transcript has a Chinese character, en if it has Latin letters, else None."""
        for r in reversed(self.trace["responses"]):
            text = r.get("asr_text") or ""
            if re.search(r"[\u4e00-\u9fff]", text):
                return "zh"
            if re.search(r"[A-Za-z]", text):
                return "en"
        return None

    def _hold_release(self, c, stop):
        h, self.hold = self.hold, None
        self.trace["held"].append({"onset": round(h["onset"], 3), "t_decide": round(self.t, 3), "text": c["text"],
                                   "units": c["units"], "decision": "stop" if stop else "ignore",
                                   "speech": round(h["speech"], 3),
                                   "lang": c.get("lang", "auto"),
                                   "checks": [{"t": x["t_start"], "text": x["text"], "units": x["units"]}
                                              for x in h["checks"]]})
        if self.pause is not None:
            self.pause["record"].update(decision="stop" if stop else "resume", t_decide=round(self.t, 3),
                                        text=c["text"])
            if stop:
                return self._pause_confirm(h["onset"])
            self.pause["resume_at"] = self.t + self.cfg.get("pause_resume_after", 0.0)
            if self.t + 1e-9 >= self.pause["resume_at"]:
                self._resume()
            return None
        if not stop:
            return None                         # backchannel: dropped, never reaches the model
        return self._user_onset(h["onset"], by={"by": "words", "text": c["text"]})

    # ---------- pause arm: pause at once, then cancel or resume (LiveKit resume_false_interruption) ----------
    def _put_agent(self, a, st, sign=1.0):
        s = int(st * SR)
        e = min(len(self.agent_track), s + len(a))
        if s < len(self.agent_track):
            self.agent_track[s:e] += sign * a[: e - s]

    def _pause(self, onset):
        """Silence the agent now. The unplayed rest of the reply waits in a queue, in order."""
        t, keep, queue, heard = self.t, [], [], ""
        for p in self.pieces:
            if p["end"] <= t or p["end"] <= p["start"]:
                keep.append(p)
                continue
            a = p["_audio"]
            self._put_agent(a, p["start"], -1.0)
            if p["start"] < t:                           # playing now: split at the pause
                n = min(len(a), int(round((t - p["start"]) * SR)))
                k = int(round(len(p["text"]) * n / max(1, len(a))))
                head = dict(p, text=p["text"][:k], end=t, full_end=t, paused=True, _audio=a[:n])
                self._put_agent(head["_audio"], head["start"])
                keep.append(head)
                heard += head["text"]
                queue.append(dict(p, text=p["text"][k:], _audio=a[n:], _ready=t, _first=False, resumed_rest=True))
            else:
                queue.append(p)
        self.pieces = keep
        rec = {"t_detect": round(t, 3), "onset_vad": round(onset, 3), "heard": heard, "by": "pause"}
        self.trace["barge_ins"].append(rec)
        self.pause = {"t": t, "onset": onset, "queue": queue, "resume_at": None, "record": rec}

    def _resume(self):
        """The speech was not an interruption: play the queued rest of the reply from where it stopped."""
        pz, self.pause = self.pause, None
        cursor = self.t
        for q in pz["queue"]:
            a = q["_audio"]
            st = max(cursor, q["_ready"])
            q.update(start=st, end=st + len(a) / SR, full_end=st + len(a) / SR)
            self._put_agent(a, st)
            self.pieces.append(q)
            cursor = q["end"]
            r = self.trace["responses"][q["resp"]]
            if r["first_audio"] is None:
                r["first_audio"] = round(st, 3)
            if q["_first"] and q["final"]:
                r["answer_audio"] = round(st, 3)
        pz["record"].update(t_resume=round(self.t, 3), gap=round(self.t - pz["t"], 3))

    def _pause_confirm(self, onset):
        """Real interruption while paused: the queued rest never plays; react as to any barge-in."""
        pz, self.pause = self.pause, None
        for q in pz["queue"]:
            q.update(start=self.t, end=self.t, full_end=self.t, cut=True)
            self.pieces.append(q)
        rid = pz["queue"][0]["resp"] if pz["queue"] else None
        if self._spoke_first(rid, onset):
            return self._merge_resumed(rid, onset)
        self.cancel_reason = "barge_in"
        self.pending_note = self.pending_note_for_barge()
        self._start_turn(onset, keep=False)
        return ("onset", self.t)

    def _spoke_first(self, rid, onset):
        """spoke_first arms: the user's speech began before this reply's first sound (it was detected later)."""
        if not self.cfg.get("spoke_first") or rid is None:
            return False
        first = self.trace["responses"][rid].get("first_audio")
        return first is not None and onset < first

    def _merge_resumed(self, rid, onset):
        """The user went on before the reply began: drop it as unheard and keep listening to the same turn,
        as when a reply is cancelled before playback (D-V11)."""
        r = self.trace["responses"][rid]
        self.trace["events"].append({"t": round(self.t, 3), "ev": "user_spoke_first", "resp": rid, "onset": round(onset, 3)})
        if self.computing and rid == len(self.trace["responses"]) - 1:
            self.cancel_reason, self.unheard = "user_resumed", True
            self._start_turn(onset, keep=True)
            return ("onset", self.t)
        r["status"] = "cancelled:user_spoke_first"
        r["cancel_t"] = round(self.t, 3)
        if any(s["kind"] == "held_tool" for s in r["steps"]):
            self.confirm_waiting = False                         # its question was not heard either
        self.trace["cancels"].append({"resp": rid, "t": round(self.t, 3), "why": "user_spoke_first"})
        if not any(s["kind"] == "tool" for s in r["steps"]):
            self.history = self.history[: r["history_before"]]   # nothing done: hear the whole turn again
        else:
            self.pending_note = ""                               # tools ran, the reply was not heard
        self.in_turn = True
        self.turn_start = r["turn_start"]
        return ("onset", self.t)

    def _cancel_pending(self, rid, onset):
        r = self.trace["responses"][rid]
        heard = self._heard_text(rid)
        for p in self.pieces:
            if p["resp"] == rid and p["start"] >= self.t:
                p["end"] = p["start"]
                p["cut"] = True
        r["status"] = "cancelled:user_resumed_before_playback"
        if not heard and any(s["kind"] == "held_tool" for s in r["steps"]):
            self.confirm_waiting = False                  # the question was never heard
        r["cancel_t"] = round(self.t, 3)
        self.trace["cancels"].append({"resp": rid, "t": round(self.t, 3), "why": "user_resumed_before_playback"})
        if heard:                       # part of the reply was already heard: the user is cutting in
            self.pending_note = heard
            self._start_turn(onset, keep=False)
            return
        if not any(s["kind"] == "tool" for s in r["steps"]):
            self.history = self.history[: r["history_before"]]   # nothing said or done: hear the whole turn again
        else:
            self.pending_note = ""      # tools ran, nothing was heard
        self.in_turn = True
        self.turn_start = r["turn_start"]

    def pending_note_for_barge(self):
        resp_ids = [p["resp"] for p in self.pieces if p.get("cut")]
        return self._heard_text(resp_ids[-1]) if resp_ids else ""

    def _start_turn(self, onset, keep):
        if keep and self.in_turn is False and self.turn_start is not None:
            self.in_turn = True          # the user resumed: same turn continues
            return
        self.in_turn = True
        self.turn_start = onset

    def _endpoint_check(self):
        if self.t - self.turn_start > MAX_TURN_SECS:
            self.trace["events"].append({"t": round(self.t, 3), "ev": "forced_endpoint"})
            return self.t
        if self.speech:
            return None
        if not self.cfg.get("smart_turn"):
            return self.t if self.silence_run >= self.cfg["endpoint_silence"] - 1e-9 else None
        if self.silence_run >= self.cfg["smart_turn_fallback"] - 1e-9:
            self.trace["smart_checks"].append({"t": round(self.t, 3), "fallback": True})
            return self.t
        if self.silence_run >= self.cfg["endpoint_silence"] - 1e-9 and not self.smart_checked:
            self.smart_checked = True
            a = self.mic[max(0, int((self.turn_start - PRE_ROLL) * SR)): int(self.t * SR)]
            prob, d = self.m["smart"](a)
            self.trace["smart_checks"].append({"t": round(self.t, 3), "p": round(prob, 3), "dur": round(d, 4),
                                               "wall": getattr(self.m["smart"], "last_wall", None)})
            if prob > 0.5:
                return self.t + d
        return None

    # ---------- replying ----------
    async def _respond(self, t_ep):
        self.in_turn = False
        self.computing = True
        self.cancel_reason = None
        rid = len(self.trace["responses"])
        if self.cfg.get("pvad") and self.enroll_at is None:
            # as the FireRedChat plugin: after the first utterance, its speaker embedding is computed (in parallel)
            self.enroll_at = t_ep + self.m["pvad_secs"]
        resp = {"id": rid, "t_endpoint": round(t_ep, 3), "turn_start": round(self.turn_start, 3), "steps": [],
                "first_audio": None, "answer_audio": None, "status": "running"}
        self.trace["responses"].append(resp)
        cursor = t_ep
        resp["history_before"] = len(self.history)
        msgs = list(self.history)
        gated = set(self.cfg.get("confirm_tools", ()))
        confirm_open, held_here = self.confirm_waiting, False   # open only for the turn after the question
        try:
            audio = self.mic[max(0, int((self.turn_start - PRE_ROLL) * SR)): int(t_ep * SR)]
            text, d = self.m["asr"](audio)
            resp["steps"].append({"kind": "asr", "start": round(cursor, 3), "dur": round(d, 4), "text": text,
                                  "wall": getattr(self.m["asr"], "last_wall", None)})
            resp["asr_text"] = text
            cursor += d
            self._catch_up(cursor)
            content = []
            if self.pending_note == "":
                content.append({"type": "text", "text": "（提示：你上一次的回答还没播放出来，用户就接着说了，用户没有听到。）"})
                resp["note"] = ""
            elif self.pending_note is not None:
                content.append({"type": "text", "text": f"（提示：你上一次回答只播放到“{self.pending_note}”就被用户打断了，"
                                                        f"后面的内容用户没有听到。）"})
                resp["note"] = self.pending_note
            content.append({"type": "text", "text": text or "（没有识别出文字）"})
            if msgs and msgs[-1]["role"] == "user":
                msgs[-1] = {"role": "user", "content": list(msgs[-1]["content"]) + content}
            else:
                msgs.append({"role": "user", "content": content})
            last_end = max([p["end"] for p in self.pieces if p["end"] > p["start"]] + [0.0])
            for step in range(8):
                t_req = cursor
                r = await self.llm.turn(msgs, self.tools)
                resp["steps"].append({"kind": "llm", "start": round(t_req, 3), "dur": round(r["t_done"], 4),
                                      "t_first_text": r["t_first_text"], "t_first_chunk": r["t_first_chunk"],
                                      "text": r["text"], "tool_uses": r["tool_uses"], "stop_reason": r["stop_reason"],
                                      "usage": r["usage"], "attempts": r.get("attempts", 1)})
                if r["text"].strip():
                    last_end = self._schedule_speech(resp, r, t_req, last_end, final=not r["tool_uses"], step=step)
                cursor = t_req + r["t_done"]
                self._catch_up(cursor)
                if not r["tool_uses"]:
                    msgs.append({"role": "assistant", "content": r["content"]})
                    break
                msgs.append({"role": "assistant", "content": r["content"]})
                results = []
                for tu in r["tool_uses"]:
                    if tu["name"] in gated and not confirm_open:
                        held_here = True
                        resp["steps"].append({"kind": "held_tool", "start": round(cursor, 3), "dur": 0.0,
                                              "name": tu["name"], "input": tu["input"]})
                        results.append({"type": "tool_result", "tool_use_id": tu["id"], "is_error": True,
                                        "content": CONFIRM_BRIEF if self.cfg.get("confirm_brief") else CONFIRM_FIRST})
                        continue
                    if tu["name"] in gated:
                        self.confirm_waiting = False
                    t0 = time.perf_counter()
                    res = await self.mcp.call_tool(tu["name"], tu["input"])
                    dt = time.perf_counter() - t0
                    block = tool_result_block(tu["id"], res)
                    resp["steps"].append({"kind": "tool", "start": round(cursor, 3), "dur": round(dt, 4),
                                          "name": tu["name"], "input": tu["input"], "result": block["content"]})
                    cursor += dt
                    results.append(block)
                msgs.append({"role": "user", "content": results})
                self._catch_up(cursor)
            resp["status"] = "done"
            self.history = msgs
            self.pending_note = None
            if gated:
                self.confirm_waiting = held_here
        except Cancelled:
            # At a cancel point msgs always ends with a user message (the turn, or tool results).
            resp["status"] = f"cancelled:{self.cancel_reason}"
            resp["cancel_t"] = round(self.t, 3)
            self.trace["cancels"].append({"resp": rid, "t": round(self.t, 3), "why": self.cancel_reason})
            for p in self.pieces:                       # pieces that had not started never play
                if p["resp"] == rid and p["start"] >= self.t:
                    p["end"] = p["start"]
            heard = "" if self.unheard else self._heard_text(rid, step=len([s for s in resp["steps"] if s["kind"] == "llm"]) - 1)
            self.unheard = False
            tools_ran = any(s["kind"] == "tool" for s in resp["steps"])
            if heard:
                msgs.append({"role": "assistant", "content": [{"type": "text", "text": heard}]})
                self.history = msgs
            elif tools_ran:
                self.history = msgs                     # tools already changed the data; keep that record
            # else: nothing was said or done; the turn is heard again in full later
            if self.cancel_reason == "user_resumed" and not heard:
                self.pending_note = None
            if held_here:
                self.confirm_waiting = bool(heard)        # the gate opens only if the question was heard
        finally:
            self.computing = False

    def _catch_up(self, t):
        ev = self.advance(t, allow_endpoint=False)
        if ev and ev[0] == "onset":
            raise Cancelled()

    def _schedule_speech(self, resp, r, t_req, last_end, final, step):
        if self.cfg.get("pause"):                      # a pause may have moved this reply's earlier chunks later
            last_end = max([last_end] + [p["end"] for p in self.pieces if p["resp"] == resp["id"]])
        chunk = r["first_chunk"] or r["text"]
        rest = r["text"][len(chunk):] if r["text"].startswith(chunk) else ""
        a1, d1 = self.m["tts"](chunk)
        walls = [getattr(self.m["tts"], "last_wall", None)]
        ready = t_req + r["t_first_chunk"] + d1
        readies = [ready]
        start1 = max(ready, last_end)
        pieces = [(chunk, a1, start1, d1)]
        end = start1 + len(a1) / SR
        # the rest is synthesized chunk by chunk by one TTS worker once the text is complete; stream_tts arms
        # start each chunk as soon as its own text has streamed in (as Pipecat and LiveKit feed their TTS)
        rest_chunks = split_chunks(rest)
        avail = [t_req + r["t_done"]] * len(rest_chunks)
        if self.cfg.get("stream_tts"):
            b = r.get("chunk_bounds") or []
            ends = [len(chunk)]
            for c in rest_chunks:
                ends.append(ends[-1] + len(c))
            if [e for _, e in b] == ends:
                avail = [t_req + t for t, _ in b[1:]]
            else:
                resp.setdefault("stream_fallback", 0)
                resp["stream_fallback"] += 1               # bounds do not match the final text: wait for it all
        if not self.cfg.get("stream_tts"):
            ready = max(ready, t_req + r["t_done"])
        for text, av in zip(rest_chunks, avail):
            a, d = self.m["tts"](text)
            walls.append(getattr(self.m["tts"], "last_wall", None))
            ready = max(ready, av) + d
            readies.append(ready)
            st = max(end, ready)
            pieces.append((text, a, st, d))
            end = st + len(a) / SR
        for i, ((text, a, st, d), w) in enumerate(zip(pieces, walls)):
            p = {"resp": resp["id"], "step": step, "text": text, "start": st, "end": st + len(a) / SR,
                 "full_end": st + len(a) / SR, "tts_dur": round(d, 4), "tts_wall": w, "final": final,
                 "_audio": a, "_ready": readies[i], "_first": i == 0}
            if self.pause is not None:
                self.pause["queue"].append(p)          # paused: plays after the queue, if the reply resumes
                continue
            self.pieces.append(p)
            self._put_agent(a, st)
        if self.pause is not None:
            return end
        if resp["first_audio"] is None:
            resp["first_audio"] = round(start1, 3)
        if final:
            resp["answer_audio"] = round(start1, 3)
        return end

    def _quiet(self):
        all_placed = all(p is not None for p in self.placed)
        last_user = max([p[1] for p in self.placed if p] + [0.0])
        last_agent = max([p["end"] for p in self.pieces] + [0.0])
        return (all_placed and not self.in_turn and not self.computing and self.hold is None
                and self.pause is None and self.t > max(last_user, last_agent) + IDLE_END)

    async def run(self):
        while self.t < T_MAX - FDUR:
            ev = self.advance(T_MAX, allow_endpoint=True) if not self._quiet() else None
            if ev is None:
                break
            if ev[0] == "endpoint":
                await self._respond(ev[1])
            if self._quiet():
                break
        if self.pause is not None:                     # still paused at the end: the rest never played
            for q in self.pause["queue"]:
                q.update(start=self.t, end=self.t, full_end=self.t, cut=True)
                self.pieces.append(q)
            self.pause["record"]["unresolved"] = True
        # whatever was still playing at the end is recorded as played in full
        for p in self.pieces:
            p.setdefault("cut", False)
        self.trace["pieces"] = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()
                                 if not k.startswith("_")} for p in self.pieces]
        self.trace["t_end"] = round(self.t, 3)
        return self.trace
