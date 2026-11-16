"""Readable timeline of every item-run, for reading failures: python -X utf8 eval/stories.py -> results/stories.md"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "eval" / "results"
SEED = {
    "M001": {"date": "2026-11-17", "start_time": "10:00", "duration_minutes": 60, "attendees": ["张伟", "李娜", "王强"]},
    "M002": {"date": "2026-11-17", "start_time": "14:00", "duration_minutes": 60, "attendees": ["陈静", "刘洋"]},
    "M003": {"date": "2026-11-18", "start_time": "16:00", "duration_minutes": 30, "attendees": ["Tom Lee"]},
}


def story(t):
    if "error" in t:
        return [f"  HARNESS ERROR: {t['error']}"]
    if t["arm"] == "oracle":
        lines = []
        for r in t["responses"]:
            for s in r["steps"]:
                if s["kind"] == "llm":
                    if s["text"].strip():
                        lines.append(f"  agent: {s['text']}")
                else:
                    lines.append(f"  tool {s['name']}({json.dumps(s['input'], ensure_ascii=False)}) -> {s['result'][:90]}")
        return lines
    ev = []
    for s in t["user_segments"]:
        ev.append((s["start"], f"USER {s['role']} {s['start']:.2f}-{s['end']:.2f}: {s['text']}"))
    for r in t["responses"]:
        ev.append((r["t_endpoint"], f"turn end detected {r['t_endpoint']:.2f} (turn from {r['turn_start']:.2f}) ASR: {r.get('asr_text')!r}"
                   + (f" [told: cut off after {r['note']!r}]" if r.get("note") is not None else "") + f" -> {r['status']}"))
        for s in r["steps"]:
            if s["kind"] == "tool":
                ev.append((s["start"], f"  tool {s['start']:.2f} {s['name']}({json.dumps(s['input'], ensure_ascii=False)}) -> {s['result'][:80]}"))
            elif s["kind"] == "held_tool":
                ev.append((s["start"], f"  tool {s['start']:.2f} {s['name']}({json.dumps(s['input'], ensure_ascii=False)}) HELD: asks the user first"))
    for p in t["pieces"]:
        if p["end"] > p["start"]:
            cut = " [CUT]" if p.get("cut") and p["end"] < p["full_end"] - 1e-6 else ""
            cut += " [PAUSED HERE]" if p.get("paused") else " [RESUMED]" if p.get("resumed_rest") else ""
            ev.append((p["start"], f"  agent {p['start']:.2f}-{p['end']:.2f}{cut}: {p['text']}"))
    for b in t["barge_ins"]:
        if b.get("by") == "pause":
            ev.append((b["t_detect"], f"  PAUSED at {b['t_detect']:.2f} -> {b.get('decision', 'unresolved')}"
                                      + (f" at {b['t_decide']:.2f}" if "t_decide" in b else "")
                                      + (f", resumed after {b['gap']:.2f} s of silence" if "gap" in b else "")))
            continue
        ev.append((b["t_detect"], f"  BARGE-IN detected {b['t_detect']:.2f}"))
    for h in t.get("held", []):
        ev.append((h["t_decide"], f"  HELD speech from {h['onset']:.2f}: last read {h['text']!r} ({h['units']} units, "
                                  f"{len(h['checks'])} reads, recognizer {h.get('lang', 'auto')}"
                                  + (f", voiced {h['speech']:.2f} s" if t["arm"].endswith("-dur") or t["arm"] in ("vad-think-pause", "vad-think-combo", "vad-think-combo-brief", "vad-think-combo-merge", "vad-think-combo-stream", "vad-think-combo-minutes", "vad-think-combo-plus") else "")
                                  + f") -> {h['decision']} at {h['t_decide']:.2f}"))
    for e in t.get("events", []):
        if e["ev"] == "forced_endpoint":
            ev.append((e["t"], f"  forced turn end at {e['t']:.2f} (20 s cap)"))
    return [x for _, x in sorted(ev, key=lambda z: z[0])]


def main():
    out = ["# Item timelines", ""]
    for run in ["run1", "run2"]:
        for arm in ["vad", "smart", "vad-think", "vad-think-words", "vad-think-words-lang", "vad-think-words-dur", "vad-think-pause", "vad-think-short", "vad-think-confirm", "vad-think-pvad", "vad-think-combo", "vad-think-combo-brief", "vad-think-combo-merge", "vad-think-combo-stream", "vad-think-combo-minutes", "vad-think-combo-plus", "oracle"]:
            f = RES / run / f"{arm}.jsonl"
            if not f.exists():
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                t = json.loads(line)
                out.append(f"## {t['item']} / {arm} / {run}")
                out += story(t)
                ms = t["final_state"]["meetings"]
                new = {k: v for k, v in ms.items() if k not in SEED or
                       any(v.get(f) != SEED[k][f] for f in ("date", "start_time", "duration_minutes", "attendees"))}
                out.append(f"  final: new or changed meetings {json.dumps(new, ensure_ascii=False)}; "
                           f"seed kept {[k for k in ('M001', 'M002', 'M003') if k in t['final_state']['meetings']]}; "
                           f"reminders {json.dumps(t['final_state']['reminders'], ensure_ascii=False)}")
                out.append("")
    (RES / "stories.md").write_text("\n".join(out), encoding="utf-8")
    print(len(out), "lines")


if __name__ == "__main__":
    main()
