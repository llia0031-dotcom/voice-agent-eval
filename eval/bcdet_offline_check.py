"""Offline check for a fifth round (no model calls): does MaAI's acoustic backchannel detector (bc_det) tell the
backchannels from the interruptions in recordings saved by earlier runs?

Runs in its own environment (<portfolio-local>/maai-env, see docs/DECISIONS.md D-V20):

  HF_HOME=<portfolio-local>/voice-models/hf  <maai-env python> -X utf8 eval/bcdet_offline_check.py
  -> eval/results/bcdet_offline_check.md and eval/results/bcdet_offline_check.json
  add --render to rebuild the .md from the saved .json without running the detector again

Rule, fixed before any output was seen:
- Recordings: the saved stereo files of vad-think-pause and vad-think-words-dur, run1 and run2
  (channel 1 = the user's microphone, channel 2 = the agent's voice). Each file is streamed through the realtime
  two-channel model (Mimi ONNX encoder, 12.5 Hz, 80 ms chunks) from its start, so the model has the whole
  conversation as context, as it would live.
- Stretches: every stretch of user speech the earlier arm held while the agent talked (vad-think-pause: each pause;
  vad-think-words-dur: each held stretch), starting at its voice-activity onset.
- Model language: `ch` for Chinese and mixed items, `en` for English items. The other language's score is reported
  too, for reference only.
- Verdict: backchannel if the user's p_bc_det reaches 0.45 at any frame within 0.8 s of the onset. 0.45 is the
  event-level threshold MaAI reports for its Japanese development set (readme/bc_det.md); nothing here is fitted
  to these items. The maximum within 0.5 s is reported as well.
- Worth a scored fifth round only if, on the 12 backchannel and interruption items, the verdict is right on more
  stretches than the A3 word-and-duration rule (6 of 8 backchannels and 16 of 16 interruptions: 22 of 24 per arm
  and run pair). Babble is reported, not scored: it is not the user, so neither answer is right by role.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from maai import Maai, MaaiInput

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "eval" / "results"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from config import DATA as LOCAL_DATA  # noqa: E402

DATA = LOCAL_DATA / "runs"
SR, CHUNK = 16000, 1280                        # 80 ms at 16 kHz = one 12.5 Hz frame
THRESHOLD, WINDOW, EARLY = 0.45, 0.8, 0.5
ARMS = ["vad-think-pause", "vad-think-words-dur"]
RUNS = ["run1", "run2"]


def item_lang():
    cases = {c["id"]: c for c in json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))["items"]}
    return {i: c.get("lang") or cases[c["copy_of"]]["lang"] for i, c in cases.items()}


def stretches(arm, trace):
    if arm == "vad-think-pause":
        return [b["onset_vad"] for b in trace["barge_ins"] if b.get("by") == "pause"]
    return [h["onset"] for h in trace.get("held", [])]


def role_at(trace, onset):
    s = next((s for s in trace["user_segments"] if s["start"] - 0.35 <= onset <= s["end"]), None)
    return (s["role"], s["start"]) if s else ("noise", None)


def make(lang):
    return Maai(mode="bc_det", lang=lang, audio_ch1=MaaiInput.Chunk(), audio_ch2=MaaiInput.Chunk(),
                frame_rate=12.5, model_type="normal-ver2", use_mimi_onnx=True, mimi_onnx_precision="fp32",
                device="cpu")


def scores(maai, wav):
    """p_bc_det of the user (channel 1) at the end of each 80 ms chunk, streamed from the start of the file."""
    maai.reset_runtime_state()
    x1, x2 = wav[:, 0].astype(np.float32), wav[:, 1].astype(np.float32)
    out, t0 = [], time.perf_counter()
    for k in range(len(x1) // CHUNK):
        maai.process(x1[k * CHUNK:(k + 1) * CHUNK], x2[k * CHUNK:(k + 1) * CHUNK])
        while not maai.result_dict_queue.empty():
            r = maai.result_dict_queue.get_nowait()
            out.append(((k + 1) * CHUNK / SR, float(r["p_bc_det"][0])))
    return out, time.perf_counter() - t0, len(x1) / SR


def peak(ps, onset, span):
    v = [p for t, p in ps if onset <= t <= onset + span]
    return max(v) if v else None


def main():
    if "--render" in sys.argv:
        saved = json.loads((RES / "bcdet_offline_check.json").read_text(encoding="utf-8"))
        return render(saved["rows"], saved["cpu_secs"], saved["audio_secs"])
    langs = item_lang()
    models = {"ch": make("ch"), "en": make("en")}
    rows, cpu, audio = [], 0.0, 0.0
    for arm in ARMS:
        for run in RUNS:
            traces = [json.loads(x) for x in (RES / run / f"{arm}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
            for t in traces:
                onsets = stretches(arm, t)
                if not onsets:
                    continue
                wav, sr = sf.read(DATA / run / arm / f"{t['item']}.wav", dtype="float32")
                assert sr == SR and wav.ndim == 2
                per = {}
                for name, m in models.items():
                    per[name], c, a = scores(m, wav)
                    cpu, audio = cpu + c, audio + a
                lang = "en" if langs[t["item"]] == "en" else "ch"
                for onset in onsets:
                    role, seg_start = role_at(t, onset)
                    p = peak(per[lang], onset, WINDOW)
                    rows.append({"arm": arm, "run": run, "item": t["item"], "role": role, "onset": round(onset, 3),
                                 "model": lang, "max_0.8": p, "max_0.5": peak(per[lang], onset, EARLY),
                                 "other_max_0.8": peak(per["en" if lang == "ch" else "ch"], onset, WINDOW),
                                 "verdict": None if p is None else ("backchannel" if p >= THRESHOLD else "interruption")})
            print(arm, run, "done", flush=True)
    (RES / "bcdet_offline_check.json").write_text(json.dumps({"cpu_secs": round(cpu, 1), "audio_secs": round(audio, 1),
                                                          "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    render(rows, cpu, audio)


def render(rows, cpu, audio):
    def right(sub):
        bc = [r for r in sub if r["role"] == "backchannel"]
        it = [r for r in sub if r["role"] == "interrupt"]
        nb = sum(r["verdict"] == "backchannel" for r in bc)
        ni = sum(r["verdict"] == "interruption" for r in it)
        return nb, len(bc), ni, len(it)
    out = ["# MaAI backchannel detector on saved recordings, offline check (generated by eval/bcdet_offline_check.py)", "",
           f"Two-channel bc_det, Mimi ONNX encoder, 12.5 Hz, CPU. Verdict: backchannel if the user's p_bc_det reaches "
           f"{THRESHOLD} within {WINDOW} s of the onset (MaAI's event-level threshold for Japanese; not fitted here). "
           "No model calls; not a scored run.", "",
           f"Processing time: {cpu:.1f} s for {audio:.1f} s of audio (each file passed once per language model): "
           f"{cpu / audio:.2f} s per second of audio.", "",
           "## Summary (run1 + run2)", "",
           "| Arm the recordings come from | Backchannels called backchannel | Interruptions called interruption | "
           "Right | A3 word-and-duration rule |", "|---|---|---|---|---|"]
    for arm in ARMS:
        nb, b, ni, i = right([r for r in rows if r["arm"] == arm])
        out.append(f"| {arm} | {nb} of {b} | {ni} of {i} | {nb + ni} of {b + i} | 22 of 24 |")
    score = lambda iid: [r["max_0.8"] for r in rows if r["item"] == iid and r["max_0.8"] is not None]
    hi = max((r for r in rows if r["role"] == "interrupt"), key=lambda r: r["max_0.8"])
    out += ["", f"Highest score on an interruption: {hi['max_0.8']:.3f} ({hi['item']}). Scores on the backchannels, "
            "lowest to highest over the four recordings: "
            + "; ".join(f"{iid} {min(score(iid)):.3f}-{max(score(iid)):.3f}" for iid in ["B01", "B02", "B03", "B04"])
            + ".", ""]
    for arm in ARMS:
        for run in RUNS:
            sub = [r for r in rows if r["arm"] == arm and r["run"] == run]
            nb, b, ni, i = right(sub)
            out += [f"## {arm}, {run}", "",
                    f"Backchannels called backchannel: {nb} of {b}; interruptions called interruption: {ni} of {i}; "
                    f"right: {nb + ni} of {b + i} (A3 rule on the same items: 11 of 12).", "",
                    "| Item | Role | Model | Max within 0.8 s | Max within 0.5 s | Other model, max within 0.8 s | Verdict |",
                    "|---|---|---|---|---|---|---|"]
            for r in sub:
                f = lambda v: "" if v is None else f"{v:.3f}"
                out.append(f"| {r['item']} | {r['role']} | {r['model']} | {f(r['max_0.8'])} | {f(r['max_0.5'])} | "
                           f"{f(r['other_max_0.8'])} | {r['verdict'] or 'no frame'} |")
            out.append("")
    (RES / "bcdet_offline_check.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
