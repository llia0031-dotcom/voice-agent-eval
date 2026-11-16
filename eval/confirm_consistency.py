"""Do the agent's spoken confirmations match what the tools did? (docs/DECISIONS.md D-V29; no model calls)

For every reply in which a data-changing tool (create_meeting, update_meeting, cancel_meeting, set_reminder) returned
without an error, the words the agent said after the last such call (the part the user heard; the full text for the
text-only control) are checked against a record of tool calls with evidence-check's script, unchanged. A
confirmation is consistent when the script finds every date, time and number it states in the record. Spoken
durations are first written as minutes ("一个小时" -> "60分钟"), because the script does not convert hours to
minutes; nothing else is changed.

Two records are used:
- A, the rule fixed before the first count: only the data-changing calls of that reply;
- B, added after seeing A (D-V29): every tool call of the conversation up to that reply, lookups included, because
  confirmations also state facts the agent looked up earlier (a meeting's old time, its date).
Under B, flags whose only missing numbers are end times (a start time plus a duration in the record) are counted
apart, because the script does no arithmetic.

  python -X utf8 eval/confirm_consistency.py  -> eval/results/confirm_consistency.md and .json
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "eval" / "results"
SCRIPT = ROOT.parent / "evidence-check" / "skills" / "evidence-check" / "scripts" / "check_evidence.py"
sys.path.insert(0, str(SCRIPT.parent))
from check_evidence import numbers_in  # noqa: E402  (the same reader the script uses)

MUTATING = {"create_meeting", "update_meeting", "cancel_meeting", "set_reminder"}
GROUPS = {"42 items (run1 + run2)": ["run1", "run2"], "confirmation items (A6)": ["confirm1", "confirm2"],
          "disfluent and new-voice items (A12)": ["dis1", "dis2"],
          "T07, N06, T09, T14 repeated (A13)": [f"min{i}" for i in range(1, 6)]}
CN = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
WORK = RES / "confirm_check"


def minutes(text):
    """Spoken durations as minutes; everything else untouched."""
    n = lambda s: int(s) if s.isdigit() else CN[s]
    t = re.sub(r"(\d+|[一两二三四五六])个?半小时", lambda m: f"{n(m.group(1)) * 60 + 30}分钟", text)
    t = re.sub(r"半个?小时", "30分钟", t)
    t = re.sub(r"(\d+|[一两二三四五六])个?(?:小时|钟头)", lambda m: f"{n(m.group(1)) * 60}分钟", t)
    t = re.sub(r"\bhalf an hour\b", "30 minutes", t, flags=re.I)
    t = re.sub(r"\b(?:an|one) hour\b", "60 minutes", t, flags=re.I)
    t = re.sub(r"\b(\d+) hours?\b", lambda m: f"{int(m.group(1)) * 60} minutes", t, flags=re.I)
    t = re.sub(r"\btwo hours\b", "120 minutes", t, flags=re.I)
    return t


def heard(t, rid, after_step):
    """What the user heard of reply rid from llm steps after after_step (played part of each piece)."""
    out = ""
    for p in sorted((p for p in t.get("pieces", []) if p["resp"] == rid and p["step"] > after_step),
                    key=lambda p: p["start"]):
        span = p["full_end"] - p["start"]
        frac = 1.0 if span <= 0 else max(0.0, min(1.0, (p["end"] - p["start"]) / span))
        out += p["text"][: int(round(len(p["text"]) * frac))]
    return out.strip()


def end_times(calls):
    """End times implied by a start time and a duration in the record, written as the script writes times."""
    out = set()
    for c in calls:
        inp = c.get("input") or {}
        if isinstance(inp, dict) and inp.get("start_time") and inp.get("duration_minutes"):
            try:
                h, m = map(int, str(inp["start_time"]).split(":"))
            except ValueError:
                continue
            e = h * 60 + m + int(inp["duration_minutes"])
            out.add(f"{(e // 60) % 24}:{e % 60:02d}")
    return out


def confirmations(folder, arm):
    f = RES / folder / f"{arm}.jsonl"
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        seen = []                                   # every tool call so far in this conversation
        for rid, r in enumerate(t.get("responses", [])):
            seen += [{"tool": s["name"], "input": s["input"], "result": s["result"]}
                     for s in r["steps"] if s["kind"] == "tool"]
            llm_seen, last_k, calls = -1, None, []
            for s in r["steps"]:
                if s["kind"] == "llm":
                    llm_seen += 1
                elif s["kind"] == "tool" and s["name"] in MUTATING and not str(s["result"]).startswith('{"error"'):
                    last_k = llm_seen
                    calls.append({"tool": s["name"], "input": s["input"], "result": s["result"]})
            if last_k is None:
                continue
            if arm == "oracle":
                said = "".join(s["text"] for s in [x for x in r["steps"] if x["kind"] == "llm"][last_k + 1:]).strip()
            else:
                said = heard(t, rid, last_k)
            if said:
                out.append({"folder": folder, "arm": arm, "item": t["item"], "resp": rid, "said": said,
                            "record": json.dumps(calls, ensure_ascii=False),
                            "record_all": json.dumps(seen, ensure_ascii=False),
                            "ends": sorted(end_times(seen))})
    return out


def rate(k, n):
    return f"{100 * k / n:.0f}%" if n else "-"


# Categories for B's remaining flags, written after reading them (D-V29): every flag gets exactly one.
CATEGORIES = [
    ("misspoken duration", "the agent said 一个半小时 (90 minutes) for the 30-minute meeting it booked, then corrected "
                           "or contradicted itself"),
    ("cut off", "the user heard only part of the sentence, which ends in the middle of a number"),
    ("count word", "a count such as 一次 or 一场 read by the script as the number 1"),
    ("clock time", "a clock time the script reads without its 上午 or 下午 (10点改到11点; one 下午 for two times; "
                   "4:00 to 4:45 in the afternoon)"),
    ("other", "none of the above"),
]


def category(c):
    m, said = set(c["missing_b"]), c["said"].strip()
    if "90" in m and "一个半小时" in said:
        return "misspoken duration"
    if not re.search(r"[。！？.!?)）]$", said):
        return "cut off"
    if m == {"1"} and re.search(r"一[次场个]", said):
        return "count word"
    if m and all(re.fullmatch(r"\d{1,2}(:\d{2})?", x) for x in m):
        return "clock time"
    return "other"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "sources").mkdir(exist_ok=True)
    rows = []
    for group, folders in GROUPS.items():
        for folder in folders:
            if not (RES / folder).exists():
                continue
            for f in sorted((RES / folder).glob("*.jsonl")):
                for c in confirmations(folder, f.stem):
                    c["group"] = group
                    rows.append(c)
    claims = []
    for i, c in enumerate(rows):
        c["id"], c["checked_text"] = f"c{i:04d}", minutes(c["said"])
        c["has_numbers"] = bool(numbers_in(c["checked_text"]))
        for tag, key in (("a", "record"), ("b", "record_all")):
            name = f"c{i:04d}{tag}.txt"
            (WORK / "sources" / name).write_text(c[key], encoding="utf-8")
            claims.append({"id": c["id"] + tag, "text": c["checked_text"],
                           "evidence": [{"source": name, "quote": c[key]}]})
    (WORK / "claims.json").write_text(json.dumps({"claims": claims}, ensure_ascii=False, indent=1), encoding="utf-8")
    run = subprocess.run([sys.executable, "-I", "-X", "utf8", str(SCRIPT), str(WORK / "claims.json"), "--sources",
                          str(WORK / "sources"), "--format", "json", "--lang", "zh"], capture_output=True, text=True,
                         encoding="utf-8")
    by_id = {r["id"]: r for r in json.loads(run.stdout)["claims"]}
    for c in rows:
        r, rb = by_id[c["id"] + "a"], by_id[c["id"] + "b"]
        c["status"], c["missing"] = r["status"], r["missing_numbers"]
        c["status_b"], c["missing_b"] = rb["status"], rb["missing_numbers"]
        c["end_time_only"] = (c["status_b"] != "supported" and bool(c["missing_b"])
                              and set(c["missing_b"]) <= set(c["ends"]))
        flagged = c["has_numbers"] and c["status_b"] != "supported" and not c["end_time_only"]
        c["category"] = category(c) if flagged else None
    (RES / "confirm_consistency.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    out = ["# Spoken confirmations against the tool record (generated by eval/confirm_consistency.py)", "",
           "Rules: docs/DECISIONS.md D-V29. Checker: evidence-check `check_evidence.py`, unchanged. Consistent: every "
           "date, time and number the agent said after its last data-changing tool call of a reply is in the record. "
           "A: the record is that reply's data-changing calls (the rule fixed first). B: every tool call of the "
           "conversation so far (changed after seeing A). Under B, 'end time only' are flags whose only missing "
           "numbers are end times implied by a start time and a duration in the record. Confirmations without any "
           "number are counted but not rated.", ""]
    for group in GROUPS:
        g = [c for c in rows if c["group"] == group]
        if not g:
            continue
        out += [f"## {group}", "",
                "| Arm | Confirmations | With a number | A: consistent | A: rate | B: consistent | B: end time only | "
                "B: other flags | B: rate |", "|---|---|---|---|---|---|---|---|---|"]
        arms = sorted({c["arm"] for c in g}, key=lambda a: (a == "oracle", a))
        tot = [0, 0, 0, 0, 0]
        for a in arms:
            ga = [c for c in g if c["arm"] == a]
            num = [c for c in ga if c["has_numbers"]]
            ok = sum(c["status"] == "supported" for c in num)
            okb = sum(c["status_b"] == "supported" for c in num)
            endb = sum(c["end_time_only"] for c in num)
            tot = [tot[0] + len(ga), tot[1] + len(num), tot[2] + ok, tot[3] + okb, tot[4] + endb]
            out.append(f"| {a} | {len(ga)} | {len(num)} | {ok} | {rate(ok, len(num))} | {okb} | {endb} | "
                       f"{len(num) - okb - endb} | {rate(okb, len(num))} |")
        out.append(f"| all | {tot[0]} | {tot[1]} | {tot[2]} | {rate(tot[2], tot[1])} | {tot[3]} | {tot[4]} | "
                   f"{tot[1] - tot[3] - tot[4]} | {rate(tot[3], tot[1])} |")
        bad = [c for c in g if c["category"]]
        num = [c for c in g if c["has_numbers"]]
        cut = sum(c["category"] == "cut off" for c in bad)
        real = sum(c["category"] in ("misspoken duration", "other") for c in bad)
        out += ["", f"After reading every flag: {len(num) - cut} confirmations rated (the {cut} cut off mid-number are "
                f"not rated), {real} where the agent said something the tools did not do, "
                f"{len(num) - cut - real} consistent ({rate(len(num) - cut - real, len(num) - cut)}). "
                "'Other' flags would count as real until read; there are "
                f"{sum(c['category'] == 'other' for c in bad)}."]
        if bad:
            out += ["", "B: the other flags by category (categories written after reading them):", "",
                    "| Category | Meaning | Flags | Items |", "|---|---|---|---|"]
            for key, meaning in CATEGORIES:
                cs = [c for c in bad if c["category"] == key]
                if cs:
                    out.append(f"| {key} | {meaning} | {len(cs)} | {', '.join(sorted({c['item'] for c in cs}))} |")
            out += ["", "B: the other flags, one by one:", "",
                    "| Run | Arm | Item | Category | What the agent said (checked form) | Numbers not in the record |",
                    "|---|---|---|---|---|---|"]
            for c in bad:
                out.append(f"| {c['folder']} | {c['arm']} | {c['item']} | {c['category']} | {c['checked_text']} | "
                           f"{', '.join(c['missing_b']) or c['status_b']} |")
        out.append("")
    (RES / "confirm_consistency.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:30]))


if __name__ == "__main__":
    main()
