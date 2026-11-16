"""Addenda A9 to A11 and A13: changes on top of vad-think-combo, each against vad-think-combo (run score.py first, with
--cases eval/confirm_cases.json for the confirm1 and confirm2 folders).

  python -X utf8 eval/compare_followups.py <arm> [<arm> ...]  -> eval/results/followups_vs_combo.md
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tables import PRICE_IN, PRICE_OUT, RES, RUNS, attribute, med, pctl, strict  # noqa: E402
from compare_confirm import cancels  # noqa: E402
from compare_short import first_reply  # noqa: E402

BASE = "vad-think-combo"
CRUNS = ["confirm1", "confirm2"]


def traces(folder, arm):
    f = RES / folder / f"{arm}.jsonl"
    if not f.exists():
        return {}
    return {json.loads(x)["item"]: json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()}


def scores(folder):
    return json.loads((RES / folder / "scores.json").read_text(encoding="utf-8"))["items"]


def question_secs(t):
    """Seconds of agent speech in the response that held a cancel (the confirmation question)."""
    for i, r in enumerate(t["responses"]):
        if any(s["kind"] == "held_tool" for s in r["steps"]):
            ps = [p for p in t["pieces"] if p["resp"] == i and p["end"] > p["start"]]
            return round(sum(p["end"] - p["start"] for p in ps), 2) if ps else None
    return None


def measures(arm):
    sc = {r: scores(r) for r in RUNS}
    tr = {r: traces(r, arm) for r in RUNS}
    xs = [(r, x) for r in RUNS for x in sc[r][arm]]
    lat = [l for _, x in xs if x["cat"] == "task" for l in x.get("latency", [])
           if l["role"] == "request" and l.get("first_audio") is not None]
    gaps, silences, ends = [], [], []
    for r, x in xs:
        if x["cat"] == "task":
            ps = first_reply(tr[r][x["item"]])
            if len(ps) > 1:
                gaps.append(ps[1]["start"] - ps[0]["full_end"])
            if ps:
                silences.append(sum(max(0.0, b["start"] - a["full_end"]) for a, b in zip(ps, ps[1:])))
                req = next(s for s in tr[r][x["item"]]["user_segments"] if s["role"] == "request")
                ends.append(ps[-1]["full_end"] - req["end"])
    fallbacks = sum(resp.get("stream_fallback", 0) for r in RUNS for t in tr[r].values() for resp in t["responses"])
    steps = sum(1 for r in RUNS for t in tr[r].values() for resp in t["responses"] for st in resp["steps"]
                if st["kind"] == "llm" and st["text"].strip())
    bab = [(r, x) for r, x in xs if x["noise"] == "babble"]
    it = [x for _, x in xs if x["cat"] == "interrupt" and x.get("overlap")]
    stops = [x["stop_latency"] for x in it if "stop_latency" in x]
    bc = [(r, x) for r, x in xs if x["cat"] == "backchannel" and x.get("overlap")]
    survived = 0
    for r, x in bc:
        t = tr[r][x["item"]]
        seg = next(s for s in t["user_segments"] if s["role"] == "backchannel")
        b = next((b for b in t["barge_ins"] if seg["start"] - 0.05 <= b["t_detect"] <= seg["end"] + 1.0), None)
        survived += b is None or b.get("decision") == "resume"
    split = talked = 0
    pz = [(r, x) for r, x in xs if x["cat"] == "pause"]
    for r, x in pz:
        t = tr[r][x["item"]]
        cont = [s for s in t["user_segments"] if s["role"] == "continuation"]
        if not cont:
            continue
        c = cont[0]
        split += any(resp["turn_start"] >= c["start"] - 0.35 for resp in t["responses"])
        talked += any(p["end"] > p["start"] and c["start"] <= p["start"] < c["end"] for p in t["pieces"])
    fired = sorted(f"{r} {x['item']}" for r, x in xs
                   if any(e["ev"] == "user_spoke_first" for e in tr[r][x["item"]].get("events", [])))
    q42 = [q for r in RUNS for t in tr[r].values() for q in [question_secs(t)] if q is not None]
    conf = {"n": 0, "ok": 0, "asked": 0, "times": [], "q": []}
    for r in CRUNS:
        ct = traces(r, arm)
        if not ct:
            continue
        csc = {x["item"]: x for x in scores(r)[arm]}
        for iid, t in ct.items():
            segs = {s["role"]: s for s in t["user_segments"]}
            c = cancels(t)
            conf["n"] += 1
            conf["ok"] += bool(csc[iid]["task_pass"])
            conf["asked"] += not any("answer" not in segs or at < segs["answer"]["start"] for at, _ in c)
            if c:
                conf["times"].append(round(c[0][0] - segs["request"]["end"], 2))
            q = question_secs(t)
            if q is not None:
                conf["q"].append(q)
    item = lambda iid, r: next(x for x in sc[r][arm] if x["item"] == iid)
    cost = 0.0
    for folder in (*RUNS, *CRUNS):
        f = RES / folder / f"{arm}.usage.json"
        if f.exists():
            u = json.loads(f.read_text(encoding="utf-8"))
            cost += u["input_tokens"] * PRICE_IN / 1e6 + u["output_tokens"] * PRICE_OUT / 1e6
    return {
        "Strict pass, run1 / run2 (of 42)": " / ".join(str(sum(strict(x) for x in sc[r][arm])) for r in RUNS),
        "Clean tasks: first audio median (s)": med([l["first_audio"] for l in lat]),
        "Clean tasks: first audio p90 (s)": pctl([l["first_audio"] for l in lat], 0.9),
        "Clean tasks: first chunk synthesis median (s)": med([l["tts"] for l in lat]),
        "Clean tasks: gaps over 0.3 s after the first chunk (longest, s)":
            f"{sum(g > 0.3 for g in gaps)} of {len(gaps)} ({round(max(gaps), 2) if gaps else '-'})",
        "Clean tasks: silence inside the first spoken reply step, median / p90 (s)":
            f"{med(silences)} / {pctl(silences, 0.9)}",
        "Clean tasks: end of the first spoken reply step after the request, median (s)": med(ends),
        "Spoken reply steps whose streamed chunk ends did not match (waited for the whole text)": f"{fallbacks} of {steps}",
        "Babble: first turn held to the 20 s cap": f"{sum(any(e['ev'] == 'forced_endpoint' for e in tr[r][x['item']]['events']) for r, x in bab)} of {len(bab)}",
        "Babble: agent cut off mid-reply": f"{sum(bool(tr[r][x['item']]['barge_ins']) for r, x in bab)} of {len(bab)}",
        "Interruptions: stopped; median (max) stop latency (s)": f"{sum(bool(x['interaction'].get('stopped')) for x in it)} of {len(it)}; "
                                                                  f"{med(stops)} ({max(stops) if stops else '-'})",
        "Backchannels: reply survived": f"{survived} of {len(bc)}",
        "Pause items: continuation became its own turn": f"{split} of {len(pz)}",
        "Pause items: agent audio started while the user went on": f"{talked} of {len(pz)}",
        "Pause items: strict pass": f"{sum(strict(x) for _, x in pz)} of {len(pz)}",
        "Replies dropped because the user spoke first (item-runs)": ", ".join(fired) if fired else "none",
        "I05 / T04 strict, run1 / run2": " / ".join("pass" if strict(item("I05", r)) else "fail" for r in RUNS) + "; "
                                        + " / ".join("pass" if strict(item("T04", r)) else "fail" for r in RUNS),
        "Confirmation question length on the 42 items, median (s)": med(q42),
        "Confirmation items: right end state; asked first": f"{conf['ok']} of {conf['n']}; {conf['asked']} of {conf['n']}" if conf["n"] else "-",
        "Confirmation items: question length median (s)": med(conf["q"]) if conf["q"] else "-",
        "Confirmation items: cancel time median (s)": med(conf["times"]) if conf["times"] else "-",
        "Model cost (USD)": round(cost, 3),
    }


def main():
    arms = [BASE, *sys.argv[1:]]
    m = {a: measures(a) for a in arms}
    out = ["# Changes on top of vad-think-combo (generated by eval/compare_followups.py)", "",
           "Rules: eval/PREREGISTRATION.md addenda A9 to A11 and A13. Each arm: run1 + run2 of the 42 items; confirmation items: "
           "confirm1 + confirm2 where the arm ran them.", "",
           "| Measure | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for k in m[BASE]:
        out.append(f"| {k} | " + " | ".join(str(m[a][k]) for a in arms) + " |")
    sc = {r: scores(r) for r in RUNS}
    orc = {}
    for r in RUNS:
        for x in sc[r]["oracle"]:
            orc.setdefault(x["item"], []).append(x)
    for a in arms[1:]:
        out += ["", f"## Failed item-runs of {a} (preregistered order)", "", "| Run | Item | Cause |", "|---|---|---|"]
        for r in RUNS:
            tr = traces(r, a)
            for x in sc[r][a]:
                if not strict(x):
                    out.append(f"| {r} | {x['item']} | {attribute(x, tr[x['item']], orc)} |")
    (RES / "followups_vs_combo.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
