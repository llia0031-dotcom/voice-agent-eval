"""Run the voice agent on every item of eval/cases.json.

Arms: vad (Silero VAD, 0.55 s silence ends a turn), smart (VAD 0.2 s + Smart Turn v3.2, 3 s fallback),
vad-think (as vad, with adaptive thinking on), oracle (no audio: the scripted text goes straight to the same Claude + MCP loop; used to separate
listening errors from reasoning errors).

Usage (from the project root; the API key file and the model folder are described under Reproduce in README.md):
  python -X utf8 eval/run.py --arm vad --tag run1 [--items T01,T03] [--save-audio]
Writes eval/results/<tag>/<arm>.jsonl, one trace per item.
"""
import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from config import ARMS, DATA, ROOT, SR, scrub_anthropic_env  # noqa: E402

scrub_anthropic_env()

from mcp import Client, StdioServerParameters  # noqa: E402

from llm import LLM, mcp_tools_to_claude, tool_result_block  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
from build_audio import expand, paths  # noqa: E402


def load_items(cases_file, only=None):
    cases = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    audio_dir, man_path = paths(cases_file)
    man = json.loads(man_path.read_text(encoding="utf-8"))
    items = expand(cases)
    noise = {k: sf.read(audio_dir / v["file"], dtype="float32")[0] for k, v in man["noise"].items()}
    out = []
    for c in items:
        if only and c["id"] not in only:
            continue
        segs = []
        for s, m in zip(c["segments"], man["items"][c["id"]]["segments"]):
            a, sr = sf.read(audio_dir / m["file"], dtype="float32")
            assert sr == SR
            segs.append({**s, "audio": a})
        c = {**c, "segments": segs}
        if c["noise"] != "none":
            snr = cases["noise"][c["noise"]]["snr_db"]
            c["noise_audio"] = noise[c["noise"]] * (man["target_rms"] / 10 ** (snr / 20))
        out.append(c)
    return out


async def run_oracle_item(item, mcp, llm, tools):
    """Text-only control: perfect transcripts and ideal turn-taking, same model, prompt and tools."""
    turns = []
    for s in item["segments"]:
        if s["role"] == "backchannel":
            continue
        if s["role"] == "continuation" and turns:
            turns[-1]["text"] += s["text"]
        else:
            turns.append({"role": s["role"], "text": s["text"]})
    msgs, trace = [], {"item": item["id"], "arm": "oracle", "responses": []}
    last_reply = ""
    for k, turn in enumerate(turns):
        content = []
        if turn["role"] == "interrupt":
            from llm import first_chunk_end
            cut = first_chunk_end(last_reply) or len(last_reply)
            content.append({"type": "text", "text": f"（提示：你上一次回答只播放到“{last_reply[:cut]}”就被用户打断了，"
                                                    f"后面的内容用户没有听到。）"})
        content.append({"type": "text", "text": turn["text"]})
        if msgs and msgs[-1]["role"] == "user":
            msgs[-1] = {"role": "user", "content": list(msgs[-1]["content"]) + content}
        else:
            msgs.append({"role": "user", "content": content})
        resp = {"turn": k, "user_role": turn["role"], "steps": []}
        for _ in range(8):
            r = await llm.turn(msgs, tools)
            resp["steps"].append({"kind": "llm", "text": r["text"], "tool_uses": r["tool_uses"],
                                  "stop_reason": r["stop_reason"], "usage": r["usage"], "dur": r["t_done"]})
            msgs.append({"role": "assistant", "content": r["content"]})
            if not r["tool_uses"]:
                last_reply = r["text"]
                break
            results = []
            for tu in r["tool_uses"]:
                res = await mcp.call_tool(tu["name"], tu["input"])
                block = tool_result_block(tu["id"], res)
                resp["steps"].append({"kind": "tool", "name": tu["name"], "input": tu["input"], "result": block["content"]})
                results.append(block)
            msgs.append({"role": "user", "content": results})
        trace["responses"].append(resp)
    return trace


class Calibrated:
    """Runs a local speech component for real but reports its time from eval/local_timing.json,
    so the virtual clock does not depend on what else the machine is doing. The real wall time is
    kept in .last_wall and written to the trace."""

    def __init__(self, comp, kind, cal):
        self.comp, self.kind, self.cal, self.last_wall = comp, kind, cal, None

    def __call__(self, x):
        out, wall = self.comp(x)
        self.last_wall = round(wall, 4)
        if self.kind == "asr":
            d = self.cal["asr"]["intercept"] + self.cal["asr"]["slope"] * len(x) / SR
        elif self.kind == "tts":
            d = self.cal["tts"]["intercept"] + self.cal["tts"]["slope"] * len(out) / SR
        else:
            d = self.cal["smart_turn"]["seconds"]
        return out, max(0.001, d)


def load_models(arm):
    from audio import ASR, AgentTTS, SileroVAD, SmartTurn
    cal = json.loads((ROOT / "eval" / "local_timing.json").read_text(encoding="utf-8"))
    m = {"vad": SileroVAD(), "asr": Calibrated(ASR(use_itn=True), "asr", cal),
         "tts": Calibrated(AgentTTS(), "tts", cal)}
    if arm == "smart":
        m["smart"] = Calibrated(SmartTurn(), "smart", cal)
    if ARMS[arm].get("pvad"):
        from audio import PersonalVAD
        enroll = json.loads((ROOT / "eval" / "pvad_enroll.json").read_text(encoding="utf-8"))
        m["vad"], m["pvad_emb"], m["pvad_secs"] = PersonalVAD(), enroll["items"], enroll["seconds_per_embedding_median"]
    if ARMS[arm].get("hold_lang"):
        for lang in ("zh", "en"):
            m[f"asr_{lang}"] = Calibrated(ASR(use_itn=True, language=lang), "asr", cal)
            m[f"asr_{lang}"](np.zeros(SR, np.float32))
    # warm-up so the first item does not pay start-up costs
    m["tts"]("你好。")
    m["asr"](np.zeros(SR, np.float32))
    if "smart" in m:
        m["smart"](np.zeros(SR, np.float32))
    return m


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(ARMS))
    ap.add_argument("--tag", required=True)
    ap.add_argument("--items", default="")
    ap.add_argument("--save-audio", action="store_true")
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.json"))
    a = ap.parse_args()
    only = set(a.items.split(",")) if a.items else None
    items = load_items(a.cases, only)
    out_dir = ROOT / "eval" / "results" / a.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{a.arm}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(line)["item"] for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    models = None if a.arm == "oracle" else load_models(a.arm)
    llm = LLM(thinking=ARMS[a.arm]["thinking"], first_chunk_min=ARMS[a.arm].get("first_chunk_min", 4),
              first_chunk_colon=ARMS[a.arm].get("first_chunk_colon", False),
              say_minutes=ARMS[a.arm].get("say_minutes", False))
    server = StdioServerParameters(command=sys.executable,
                                   args=["-I", "-X", "utf8", str(ROOT / "agent" / "mock_tools_server.py")])
    async with Client(server) as mcp:
        tools = mcp_tools_to_claude((await mcp.list_tools()).tools)
        for item in items:
            if item["id"] in done:
                continue
            await mcp.call_tool("admin_reset", {})
            t0 = time.perf_counter()
            try:
                if a.arm == "oracle":
                    trace = await run_oracle_item(item, mcp, llm, tools)
                else:
                    from pipeline import Sim
                    sim = Sim(item, a.arm, models, mcp, llm, tools)
                    trace = await sim.run()
                    if a.save_audio:
                        n = int(trace["t_end"] * SR)
                        st = np.stack([sim.mic[:n], sim.agent_track[:n]], axis=1)
                        p = DATA / "runs" / a.tag / a.arm
                        p.mkdir(parents=True, exist_ok=True)
                        sf.write(p / f"{item['id']}.wav", np.clip(st, -1, 1), SR, subtype="PCM_16")
            except Exception as e:  # keep going; the scorer reports harness errors
                trace = {"item": item["id"], "arm": a.arm, "error": f"{type(e).__name__}: {e}",
                         "traceback": traceback.format_exc()}
            state = json.loads((await mcp.call_tool("admin_state", {})).content[0].text)
            trace["final_state"] = {"meetings": state["meetings"], "reminders": state["reminders"]}
            trace["tool_log"] = state["log"]
            trace["wall_secs"] = round(time.perf_counter() - t0, 2)
            trace["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - trace["wall_secs"]))
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(trace, ensure_ascii=False) + "\n")
            print(item["id"], a.arm, "error" if "error" in trace else "ok", trace["wall_secs"], "s", flush=True)
    print("usage", json.dumps(llm.usage))
    up = out_dir / f"{a.arm}.usage.json"
    prev = json.loads(up.read_text(encoding="utf-8")) if up.exists() else {}
    total = {k: prev.get(k, 0) + v for k, v in llm.usage.items()}
    up.write_text(json.dumps(total), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
