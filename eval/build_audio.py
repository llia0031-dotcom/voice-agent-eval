"""Synthesize the simulated users' speech and the noise tracks for eval/cases.json.

Output (outside the synced folder): <DATA>/audio/<item>/seg<k>.wav, <DATA>/audio/noise_<kind>.wav,
and eval/audio_manifest.json (durations and sha256 of every file) in the project.
Run from the project root: python eval/build_audio.py
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from audio import UserTTS, trim  # noqa: E402
from config import DATA, ROOT, SR  # noqa: E402

TARGET_RMS = 0.05
NOISE_SECS = 80


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def expand(cases):
    """Resolve copy_of items and give every item its speaker id."""
    by_id = {c["id"]: c for c in cases["items"]}
    out = []
    zh, en = cases["speakers"]["zh"], cases["speakers"]["en"]
    k_zh = k_en = 0
    for c in cases["items"]:
        if "copy_of" in c:
            src = by_id[c["copy_of"]]
            c = {**src, "id": c["id"], "cat": c["cat"], "noise": c["noise"], "copy_of": c["copy_of"]}
        else:
            c = dict(c)
            c.setdefault("noise", "none")
            if c["lang"] == "en":
                c["speaker"] = en[k_en % len(en)]
                k_en += 1
            else:
                c["speaker"] = zh[k_zh % len(zh)]
                k_zh += 1
        out.append(c)
    for c in out:   # noisy copies use the same voice as their source
        if "copy_of" in c:
            c["speaker"] = next(x["speaker"] for x in out if x["id"] == c["copy_of"])
    return out


def pink_noise(n, seed=7):
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(spec))
    f[0] = 1
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return (x / rms(x)).astype(np.float32)


def babble(tts, lines, sids, n):
    tracks = []
    for j, sid in enumerate(sids):
        parts = []
        for k in range(len(lines)):
            a = trim(tts(lines[(k + j) % len(lines)], sid=sid))
            parts += [a, np.zeros(int(0.3 * SR), np.float32)]
        t = np.concatenate(parts)
        t = t / rms(t)
        t = np.roll(np.tile(t, int(np.ceil(n / len(t)))), int(j * 1.7 * SR))[:n]
        tracks.append(t)
    x = np.sum(tracks, axis=0)
    return (x / rms(x)).astype(np.float32)


def paths(cases_file: str):
    """Audio folder and manifest for a cases file (cases.json keeps the original names)."""
    stem = Path(cases_file).stem
    if stem == "cases":
        return DATA / "audio", ROOT / "eval" / "audio_manifest.json"
    return DATA / f"audio_{stem}", ROOT / "eval" / f"{stem}.audio.json"


def main():
    cases_file = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "eval" / "cases.json")
    cases = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    items = expand(cases)
    out, man_path = paths(cases_file)
    out.mkdir(parents=True, exist_ok=True)
    tts = UserTTS()
    manifest = {"sample_rate": SR, "target_rms": TARGET_RMS, "items": {}, "noise": {}}
    n = NOISE_SECS * SR
    noise_files = {"pink": pink_noise(n), "babble": babble(tts, cases["babble_lines"], [33, 52, 70, 95], n)}
    for kind, x in noise_files.items():
        p = out / f"noise_{kind}.wav"
        sf.write(p, x, SR, subtype="FLOAT")
        manifest["noise"][kind] = {"file": p.name, "sha256": sha(p)}
    cache = {}
    for c in items:
        d = out / c["id"]
        d.mkdir(exist_ok=True)
        segs = []
        for k, s in enumerate(c["segments"]):
            key = (s["text"], c["speaker"])
            if key not in cache:
                a = trim(tts(s["text"], sid=c["speaker"]))
                cache[key] = (a / rms(a) * TARGET_RMS).astype(np.float32)
            p = d / f"seg{k}.wav"
            sf.write(p, cache[key], SR, subtype="FLOAT")
            segs.append({"file": f"{c['id']}/seg{k}.wav", "dur": round(len(cache[key]) / SR, 3), "sha256": sha(p)})
        manifest["items"][c["id"]] = {"speaker": c["speaker"], "noise": c["noise"], "segments": segs}
        print(c["id"], c["speaker"], [s["dur"] for s in segs])
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")


if __name__ == "__main__":
    main()
