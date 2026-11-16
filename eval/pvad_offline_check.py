"""Offline check for the noise item (no model calls): does FireRedChat pVAD hear only the user where Silero hears
the background talkers too?

  python -X utf8 eval/pvad_offline_check.py  -> eval/results/pvad_offline_check.md (needs eval/pvad_enroll.json)

Rule, fixed before any output was seen (also in docs/DECISIONS.md D-V23):
- Each item's microphone is rebuilt with its user segments placed where vad-think put them in run1 and in run2
  (noise from t=0, scaled as in the runs), up to the end of that run's trace.
- Silero and pVAD run on the same 32 ms frames with the pipeline's hysteresis (on at 0.5, off below 0.35).
- pVAD uses a zero speaker embedding until 0.55 s after the first user segment ends (when a turn end would come in
  quiet), then the item's embedding from eval/pvad_enroll.py (the plugin updates it after the first utterance).
- A frame is user speech if the user-only signal has an RMS of at least 0.005 in it.
- Pass, all three needed for a scored run: after the embedding is set, at most 10% of babble-only frames marked as
  speech; at least 90% of the user's frames caught in later segments of clean items; no more false onsets than
  Silero on clean items (an onset = 0.2 s of speech state starting while the user is silent and more than 0.3 s
  after a user segment). If pVAD catches under 90% of first-segment frames with the zero embedding, the scored arm
  keeps Silero until the embedding is set.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))
from config import FRAME, START_SECS, VAD_OFF, VAD_ON  # noqa: E402
from audio import PersonalVAD, SileroVAD  # noqa: E402
from mic_rebuild import SR, load, mic  # noqa: E402

FDUR = FRAME / SR
RES = ROOT / "eval" / "results"
ENROLL_AFTER = 0.55


def states(probs):
    out, on = [], False
    for p in probs:
        on = True if p >= VAD_ON else False if p < VAD_OFF else on
        out.append(on)
    return np.array(out)


def onsets(state, user, quiet_after):
    """Frame indices where the speech state has run START_SECS while the user is silent."""
    need, run, found = int(round(START_SECS / FDUR)), 0, []
    for k, on in enumerate(state):
        run = run + 1 if on else 0
        if run == need and not user[k - need + 1:k + 1].any() and quiet_after[k]:
            found.append(k)
    return found


def main():
    cases, man, noise = load()
    emb = json.loads((ROOT / "eval" / "pvad_enroll.json").read_text(encoding="utf-8"))["items"]
    cat = {c["id"]: c for c in cases["items"]}
    sil, pv = SileroVAD(), PersonalVAD()
    rows = []
    for run in ["run1", "run2"]:
        for line in (RES / run / "vad-think.jsonl").read_text(encoding="utf-8").splitlines():
            t = json.loads(line)
            iid = t["item"]
            segs = sorted(t["user_segments"], key=lambda s: s["i"])
            m, u = mic(cases, man, noise, iid, [s["start"] for s in segs], t["t_end"])
            nf = len(m) // FRAME
            fr = lambda x, k: x[k * FRAME:(k + 1) * FRAME]
            user = np.array([np.sqrt(np.mean(fr(u, k) ** 2)) >= 0.005 for k in range(nf)])
            t_enroll = segs[0]["end"] + ENROLL_AFTER
            sil.reset(); pv.reset()
            ps, pp = [], []
            for k in range(nf):
                if not pv.emb.any() and (k + 1) * FDUR >= t_enroll:
                    pv.set_speaker(emb[iid])
                ps.append(sil(fr(m, k)))
                pp.append(pv(fr(m, k)))
            ss, sp = states(ps), states(pp)
            tt = (np.arange(nf) + 1) * FDUR
            first = np.zeros(nf, bool)
            first[int(segs[0]["start"] / FDUR): int(np.ceil(segs[0]["end"] / FDUR))] = True
            after = tt >= t_enroll
            ends = [s["end"] for s in segs]
            quiet_after = np.array([all(not (e <= x <= e + 0.3) for e in ends) for x in tt])
            noise_kind = man["items"][iid]["noise"]
            rows.append({
                "run": run, "item": iid, "noise": noise_kind,
                "first_user": int((user & first).sum()),
                "first_sil": int((user & first & ss).sum()), "first_pv": int((user & first & sp).sum()),
                "later_user": int((user & ~first & after).sum()),
                "later_sil": int((user & ~first & after & ss).sum()), "later_pv": int((user & ~first & after & sp).sum()),
                "quiet_after": int((~user & after).sum()),
                "quiet_after_sil": int((~user & after & ss).sum()), "quiet_after_pv": int((~user & after & sp).sum()),
                "quiet_before": int((~user & ~after).sum()),
                "quiet_before_sil": int((~user & ~after & ss).sum()), "quiet_before_pv": int((~user & ~after & sp).sum()),
                "onsets_sil": len(onsets(ss, user, quiet_after)),
                "onsets_pv": len([k for k in onsets(sp, user, quiet_after) if after[k]]),
                "onsets_sil_after": len([k for k in onsets(ss, user, quiet_after) if after[k]]),
            })
        print(run, "done", flush=True)

    def pct(rs, a, b):
        num, den = sum(r[a] for r in rs), sum(r[b] for r in rs)
        return f"{100 * num / den:.1f}% ({num}/{den})" if den else "-"
    groups = [("clean", lambda r: r["noise"] == "none"), ("pink", lambda r: r["noise"] == "pink"),
              ("babble", lambda r: r["noise"] == "babble")]
    out = ["# FireRedChat pVAD against Silero on rebuilt microphones, offline check "
           "(generated by eval/pvad_offline_check.py)", "",
           "Segments placed as in the vad-think runs (run1 + run2, 84 item-runs). Frames of 32 ms, hysteresis 0.5 / 0.35. "
           f"pVAD gets the item's speaker embedding {ENROLL_AFTER} s after the first user segment ends (zeros before). "
           "User frame: user-only RMS of at least 0.005. No model calls; not a scored run.", "",
           "| Items | Item-runs | User frames caught, first segment: Silero | pVAD (zero embedding) | "
           "User frames caught, later segments: Silero | pVAD | Non-user frames marked speech, after the embedding: "
           "Silero | pVAD | Before the embedding: Silero | pVAD | False onsets after the embedding: Silero | pVAD |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, f in groups:
        rs = [r for r in rows if f(r)]
        out.append(f"| {name} | {len(rs)} | {pct(rs, 'first_sil', 'first_user')} | {pct(rs, 'first_pv', 'first_user')} | "
                   f"{pct(rs, 'later_sil', 'later_user')} | {pct(rs, 'later_pv', 'later_user')} | "
                   f"{pct(rs, 'quiet_after_sil', 'quiet_after')} | {pct(rs, 'quiet_after_pv', 'quiet_after')} | "
                   f"{pct(rs, 'quiet_before_sil', 'quiet_before')} | {pct(rs, 'quiet_before_pv', 'quiet_before')} | "
                   f"{sum(r['onsets_sil_after'] for r in rs)} | {sum(r['onsets_pv'] for r in rs)} |")
    clean = [r for r in rows if r["noise"] == "none"]
    bab = [r for r in rows if r["noise"] == "babble"]
    fa = sum(r["quiet_after_pv"] for r in bab) / max(1, sum(r["quiet_after"] for r in bab))
    rec = sum(r["later_pv"] for r in clean) / max(1, sum(r["later_user"] for r in clean))
    ons = (sum(r["onsets_pv"] for r in clean), sum(r["onsets_sil_after"] for r in clean))
    first = sum(r["first_pv"] for r in clean) / max(1, sum(r["first_user"] for r in clean))
    out += ["", "Pass rules fixed before the check:", "",
            f"- Babble-only frames marked as speech after the embedding at most 10%: {100 * fa:.1f}% -> "
            + ("met" if fa <= 0.10 else "not met"),
            f"- Later-segment user frames caught on clean items at least 90%: {100 * rec:.1f}% -> "
            + ("met" if rec >= 0.90 else "not met"),
            f"- False onsets on clean items after the embedding no more than Silero: pVAD {ons[0]}, Silero {ons[1]} -> "
            + ("met" if ons[0] <= ons[1] else "not met"),
            f"- First-segment user frames caught with the zero embedding (clean items): {100 * first:.1f}% -> "
            + ("pVAD from the start" if first >= 0.90 else "Silero until the embedding is set"), ""]
    out += ["## Per item-run", "", "| Run | Item | Noise | First seg. caught Silero / pVAD | Later caught Silero / pVAD | "
            "Non-user after, marked Silero / pVAD | False onsets after Silero / pVAD |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['run']} | {r['item']} | {r['noise']} | {r['first_sil']}/{r['first_pv']} of {r['first_user']} | "
                   f"{r['later_sil']}/{r['later_pv']} of {r['later_user']} | "
                   f"{r['quiet_after_sil']}/{r['quiet_after_pv']} of {r['quiet_after']} | "
                   f"{r['onsets_sil_after']}/{r['onsets_pv']} |")
    (RES / "pvad_offline_check.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (RES / "pvad_offline_check.json").write_text(json.dumps(rows), encoding="utf-8")
    print("\n".join(out[:16]))


if __name__ == "__main__":
    main()
