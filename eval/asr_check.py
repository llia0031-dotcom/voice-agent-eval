"""Recognition check on the exact user speech (no turn-taking involved).

1. Construction check: SenseVoice and Whisper-small on the clean synthetic speech. A segment where both
   recognizers miss the same words points to a synthesis problem in the test item, not the agent.
2. ASR-only baseline: SenseVoice error rate per category and noise condition, plus key-slot hits.
Run: python -X utf8 eval/asr_check.py [--whisper]  -> eval/results/asr_check.json and .md
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx as so

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audio import ASR  # noqa: E402
from config import MODELS, ROOT, SR  # noqa: E402
from run import load_items  # noqa: E402

CJK = re.compile(r"[一-鿿]")


def tokens(text: str) -> list[str]:
    text = text.lower().replace("-", " ")
    out = []
    for w in re.findall(r"[一-鿿]|[a-z0-9']+", text):
        out.append(w)
    return out


def edit_distance(a, b):
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
    return d[len(b)]


def mer(ref: str, hyp: str) -> tuple[int, int]:
    """Mixed error count: Chinese characters and English words are both one token."""
    r, h = tokens(ref), tokens(hyp)
    return edit_distance(r, h), len(r)


def whisper():
    d = MODELS / "sherpa-onnx-whisper-small"
    return so.OfflineRecognizer.from_whisper(encoder=str(d / "small-encoder.int8.onnx"),
                                            decoder=str(d / "small-decoder.int8.onnx"),
                                            tokens=str(d / "small-tokens.txt"), language="", task="transcribe",
                                            num_threads=4)


def run_whisper(rec, audio):
    s = rec.create_stream()
    s.accept_waveform(SR, audio)
    rec.decode_stream(s)
    return s.result.text.strip()


def main():
    use_whisper = "--whisper" in sys.argv
    items = load_items(str(ROOT / "eval" / "cases.json"))
    plain, itn = ASR(use_itn=False), ASR(use_itn=True)
    wh = whisper() if use_whisper else None
    rows = []
    for it in items:
        pad = np.zeros(int(0.3 * SR), np.float32)
        for k, s in enumerate(it["segments"]):
            a = np.concatenate([pad, s["audio"], pad])
            if it.get("noise_audio") is not None:
                a = a + it["noise_audio"][: len(a)]
            hyp, _ = plain(a)
            hyp_itn, _ = itn(a)
            e, n = mer(s["text"], hyp)
            row = {"item": it["id"], "seg": k, "cat": it["cat"], "lang": it["lang"], "noise": it["noise"],
                   "role": s["role"], "ref": s["text"], "sensevoice": hyp, "sensevoice_itn": hyp_itn,
                   "errors": e, "ref_tokens": n}
            if wh is not None and it["noise"] == "none":
                row["whisper"] = run_whisper(wh, a)
                row["whisper_errors"] = mer(s["text"], row["whisper"])[0]
            rows.append(row)
            print(it["id"], k, e, "/", n, hyp_itn, "|", row.get("whisper", ""), flush=True)
    agg = {}
    for r in rows:
        key = f"{r['lang']}|{r['noise']}"
        a = agg.setdefault(key, [0, 0])
        a[0] += r["errors"]
        a[1] += r["ref_tokens"]
    summary = {k: {"errors": v[0], "tokens": v[1], "rate": round(v[0] / max(1, v[1]), 4)} for k, v in sorted(agg.items())}
    out = ROOT / "eval" / "results" / "asr_check.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
