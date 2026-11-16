"""Calibrate the time of the local speech components, so results do not depend on machine load.

Each input is timed 5 times and the fastest run is kept (the run least disturbed by other programs);
a straight line is fitted: ASR seconds vs. input audio seconds, TTS seconds vs. output audio seconds,
and a constant for Smart Turn. Writes eval/local_timing.json, which run.py uses for the virtual clock.
Run: python -X utf8 eval/calibrate.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from audio import ASR, AgentTTS, SmartTurn  # noqa: E402
from config import DATA, ROOT, SR  # noqa: E402

REPEATS = 5
TTS_TEXTS = [
    "好的，", "好的，我查一下。", "已经帮你约好了，", "明天上海小雨，", "气温在8到13度之间，", "出门记得带伞。",
    "已经帮你安排好了，后天11月18日上午10点，", "和陈静、刘洋的会议，时长30分钟。", "Sure,", "Done.",
    "I've set up a 30-minute call with Tom Lee tomorrow,", "at 5 PM.", "What time would you like the call?",
    "明天有两个会议：上午10点的周会和下午2点的设计评审。",
]


def fastest(fn, *args):
    best, out = None, None
    for _ in range(REPEATS):
        t = time.perf_counter()
        out = fn(*args)
        d = time.perf_counter() - t
        best = d if best is None else min(best, d)
    return best, out


def fit(x, y):
    a1, a0 = np.polyfit(np.asarray(x, float), np.asarray(y, float), 1)
    return {"intercept": round(float(a0), 4), "slope": round(float(a1), 4)}


def main():
    asr, tts, st = ASR(use_itn=True), AgentTTS(), SmartTurn()
    tts("你好。")
    asr(np.zeros(SR, np.float32))
    man = json.loads((ROOT / "eval" / "audio_manifest.json").read_text(encoding="utf-8"))
    ax, ay = [], []
    pad = np.zeros(int(0.3 * SR), np.float32)
    for item in list(man["items"].values())[:24]:
        for s in item["segments"]:
            a = np.concatenate([pad, sf.read(DATA / "audio" / s["file"], dtype="float32")[0], pad])
            d, _ = fastest(asr, a)
            ax.append(len(a) / SR)
            ay.append(d)
    tx, ty = [], []
    for text in TTS_TEXTS:
        d, (audio, _) = fastest(tts, text)
        tx.append(len(audio) / SR)
        ty.append(d)
    sd = [fastest(st, np.random.default_rng(k).standard_normal(SR * (2 + k)).astype(np.float32) * 0.05)[0]
          for k in range(5)]
    out = {"method": f"fastest of {REPEATS} runs per input, linear fit", "measured_at": time.strftime("%Y-%m-%d %H:%M"),
           "asr": {**fit(ax, ay), "n": len(ax), "x": "input audio seconds"},
           "tts": {**fit(tx, ty), "n": len(tx), "x": "output audio seconds"},
           "smart_turn": {"seconds": round(float(np.median(sd)), 4)},
           "points": {"asr": list(zip(map(lambda v: round(v, 3), ax), map(lambda v: round(v, 4), ay))),
                      "tts": list(zip(map(lambda v: round(v, 3), tx), map(lambda v: round(v, 4), ty)))}}
    (ROOT / "eval" / "local_timing.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "points"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
