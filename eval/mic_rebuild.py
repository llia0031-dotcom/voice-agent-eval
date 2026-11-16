"""Rebuild the microphone signal of an item as eval/run.py and agent/pipeline.py make it: the noise track from t=0
(scaled to the item's SNR) plus each user segment at a given start time. numpy and soundfile only, so it runs in
both Python environments (voice-eval-env and maai-env)."""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from config import DATA  # noqa: E402  (PORTFOLIO_LOCAL/voice-eval-data)

SR = 16000


def load(stem="cases"):
    """Cases, audio manifest and noise tracks of eval/<stem>.json, from the folders eval/build_audio.py writes."""
    cases = json.loads((ROOT / "eval" / f"{stem}.json").read_text(encoding="utf-8"))
    man_path = ROOT / "eval" / ("audio_manifest.json" if stem == "cases" else f"{stem}.audio.json")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    man["_dir"] = DATA / ("audio" if stem == "cases" else f"audio_{stem}")
    noise = {k: sf.read(man["_dir"] / v["file"], dtype="float32")[0] for k, v in man["noise"].items()}
    return cases, man, noise


def segments(man, item):
    return [sf.read(man["_dir"] / m["file"], dtype="float32")[0] for m in man["items"][item]["segments"]]


def noise_track(cases, man, noise, item, n):
    kind = man["items"][item]["noise"]
    if kind == "none":
        return np.zeros(n, np.float32)
    nz = noise[kind] * (man["target_rms"] / 10 ** (cases["noise"][kind]["snr_db"] / 20))
    return np.tile(nz, int(np.ceil(n / len(nz))))[:n].astype(np.float32)


def mic(cases, man, noise, item, starts, secs):
    """(mic, user-only signal) of length secs, user segment k placed at starts[k]."""
    n = int(secs * SR)
    user = np.zeros(n, np.float32)
    for a, st in zip(segments(man, item), starts):
        s = int(round(st * SR))
        e = min(n, s + len(a))
        if s < n:
            user[s:e] += a[: e - s]
    return noise_track(cases, man, noise, item, n) + user, user
