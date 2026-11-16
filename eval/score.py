"""Score traces from eval/run.py against the answers fixed in eval/cases.json.

  python -X utf8 eval/score.py eval/results/run1 [eval/results/run2 ...]  -> <dir>/scores.json + summary.md
  python -X utf8 eval/score.py --check   -> self-check of the scorer on constructed traces (no model calls)
"""
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))

SEED = {
    "M001": {"date": "2026-11-17", "start_time": "10:00", "duration_minutes": 60, "attendees": ["张伟", "李娜", "王强"]},
    "M002": {"date": "2026-11-17", "start_time": "14:00", "duration_minutes": 60, "attendees": ["陈静", "刘洋"]},
    "M003": {"date": "2026-11-18", "start_time": "16:00", "duration_minutes": 30, "attendees": ["Tom Lee"]},
}
MUTATING = {"create_meeting", "update_meeting", "cancel_meeting", "set_reminder"}
TEMP_RE = re.compile(r"(\d+|[零一二两三四五六七八九十]+)\s*(度|°|℃)|degrees", re.I)
LEAK_RE = re.compile(r"用户|the user|识别结果|应为|2026-1\d-\d\d|工具|\btool\b", re.I)  # reasoning said out loud
STOP_WINDOW = 1.0      # a barge-in counts for a user segment if detected before its end + this


def norm_meeting(m):
    return (m["date"], m["start_time"], int(m["duration_minutes"]),
            tuple(sorted(a.strip().lower() for a in m["attendees"])))


def expected_meetings(exp):
    ms = {k: dict(v) for k, v in SEED.items()}
    for k in exp.get("remove", []):
        ms.pop(k)
    for k, ch in exp.get("change", {}).items():
        ms[k].update(ch)
    seeded = sorted(norm_meeting(v) for v in ms.values())
    added = sorted(norm_meeting(a) for a in exp.get("add", []))
    return sorted(seeded + added)


def state_ok(trace, exp):
    got = sorted(norm_meeting(v) for v in trace["final_state"]["meetings"].values())
    want = expected_meetings(exp)
    rem_got = sorted((r["date"], r["time"]) for r in trace["final_state"]["reminders"])
    rem_want = sorted((r["date"], r["time"]) for r in exp.get("reminders", []))
    return got == want and rem_got == rem_want, {"meetings": got, "want": want, "reminders": rem_got, "rem_want": rem_want}


def tool_steps(trace):
    """(virtual start time or None, name, input, result) for every tool step, in order."""
    out = []
    for r in trace.get("responses", []):
        for s in r["steps"]:
            if s["kind"] == "tool":
                out.append((s.get("start"), s["name"], s["input"], s["result"]))
    return out


def heard_text(trace, after=None):
    """Text the user actually heard (played part of each piece); oracle: every reply text."""
    if trace["arm"] == "oracle":
        rs = trace["responses"]
        if after == "last_turn":
            rs = rs[-1:]
        return "".join(s["text"] for r in rs for s in r["steps"] if s["kind"] == "llm")
    out = ""
    for p in trace.get("pieces", []):
        if after is not None and p["start"] < after:
            continue
        span = p["full_end"] - p["start"]
        frac = 1.0 if span <= 0 else max(0.0, min(1.0, (p["end"] - p["start"]) / span))
        out += p["text"][: int(round(len(p["text"]) * frac))]
    return out


def segs(trace, role):
    return [s for s in trace.get("user_segments", []) if s["role"] == role]


def speaking_at(trace, t):
    return any(p["start"] <= t < p["full_end"] and p["end"] > t - 1e-6 for p in trace.get("pieces", []))


def barge_for(trace, seg):
    for b in trace.get("barge_ins", []):
        if seg["start"] - 0.05 <= b["t_detect"] <= seg["end"] + STOP_WINDOW:
            return b
    return None


def score_item(trace, case):
    exp = case["expect"]
    audio = trace["arm"] != "oracle"
    res = {"item": case["id"], "cat": case["cat"], "lang": case["lang"], "noise": case.get("noise", "none"),
           "checks": {}, "notes": []}
    if "error" in trace:
        res.update(task_pass=False, interaction_pass=False if audio else None, harness_error=trace["error"])
        return res
    c = res["checks"]
    steps = tool_steps(trace)
    interrupt = (segs(trace, "interrupt") or [None])[0] if audio else None
    # ---- task (content) checks ----
    ok, detail = state_ok(trace, exp)
    c["state"] = ok
    res["state_detail"] = detail
    if exp.get("no_mutation"):
        c["no_mutation"] = not any(n in MUTATING and not str(r).startswith('{"error"') for _, n, _, r in steps)
    w = exp.get("weather") or exp.get("weather_after_interrupt")
    if w:
        t_from = interrupt["start"] if (audio and "weather_after_interrupt" in exp and interrupt) else None
        def hit(s):
            if s[1] != "get_weather":
                return False
            if t_from is not None and (s[0] is None or s[0] < t_from):
                return False
            try:
                r = json.loads(s[3])
            except (json.JSONDecodeError, TypeError):
                return False
            return r.get("city") == w["city"] and r.get("date") == w["date"]
        if not audio and "weather_after_interrupt" in exp:
            last = trace["responses"][-1]
            c["weather_call"] = any(hit((None, s["name"], s["input"], s["result"])) for s in last["steps"] if s["kind"] == "tool")
        else:
            c["weather_call"] = any(hit(s) for s in steps)
    if exp.get("say_any"):
        after = interrupt["start"] if (audio and interrupt) else ("last_turn" if not audio and case["cat"] == "interrupt" else None)
        said = heard_text(trace, after).lower()
        c["said"] = any(x.lower() in said for x in exp["say_any"])
    if exp.get("no_temperature"):
        c["no_temperature"] = not TEMP_RE.search(heard_text(trace))
    if exp.get("ask_first"):
        ans = (segs(trace, "answer") or [None])[0] if audio else None
        if audio:
            if ans is None:
                c["ask_first"] = False
                res["notes"].append("answer segment never played")
            else:
                c["ask_first"] = not any(n == "create_meeting" and t is not None and t < ans["start"] for t, n, _, _ in steps)
        else:
            first = trace["responses"][0]
            c["ask_first"] = not any(s["kind"] == "tool" and s["name"] == "create_meeting" for s in first["steps"])
    res["task_pass"] = all(c.values())
    res["leak"] = bool(LEAK_RE.search(heard_text(trace)))
    # ---- interaction checks (audio arms only) ----
    if not audio:
        res["interaction_pass"] = None
        return res
    ic = res.setdefault("interaction", {})
    if exp.get("stop"):
        seg = interrupt
        overlap = seg is not None and speaking_at(trace, seg["start"])
        res["overlap"] = overlap
        if not overlap:
            res["notes"].append("agent was not speaking when the interruption started")
        else:
            b = barge_for(trace, seg)
            ic["stopped"] = b is not None
            if b:
                res["stop_latency"] = round(b["t_detect"] - seg["start"], 3)
            if exp.get("quiet_after") is not None:
                t_stop = b["t_detect"] if b else seg["start"]
                talk = sum(max(0.0, p["end"] - max(p["start"], t_stop)) for p in trace["pieces"])
                ic["quiet_after"] = talk <= exp["quiet_after"]
                res["talk_after_stop"] = round(talk, 2)
    if exp.get("no_stop"):
        seg = (segs(trace, "backchannel") or [None])[0]
        overlap = seg is not None and speaking_at(trace, seg["start"])
        res["overlap"] = overlap
        if not overlap:
            res["notes"].append("agent was not speaking when the backchannel started")
        else:
            ic["kept_talking"] = barge_for(trace, seg) is None
    if case["cat"] == "pause":
        a, b = trace["user_segments"][0], trace["user_segments"][1]
        early = [p for p in trace["pieces"] if a["end"] <= p["start"] < b["start"] and p["end"] > p["start"]]
        ic["no_takeover_in_pause"] = not early
        res["premature_llm"] = any(a["end"] <= r["t_endpoint"] < b["start"] for r in trace["responses"])
        res["premature_mutation"] = any(n in MUTATING and t is not None and a["end"] <= t < b["start"]
                                        for t, n, _, _ in steps)
    res["interaction_pass"] = all(ic.values()) if ic else True
    res["latency"] = latencies(trace)
    res["slots"] = slot_hits(trace, case)
    return res


def latencies(trace):
    """FDB-style response latency per user turn: first agent audio after the turn ends - turn end."""
    groups, cur = [], None
    for s in trace["user_segments"]:
        if s["role"] == "backchannel":
            continue
        if s["role"] == "continuation" and cur:
            cur["end"] = s["end"]
        else:
            cur = {"role": s["role"], "start": s["start"], "end": s["end"]}
            groups.append(cur)
    out = []
    for k, g in enumerate(groups):
        nxt = groups[k + 1]["start"] if k + 1 < len(groups) else 1e9
        cands = [p for p in trace["pieces"] if g["end"] <= p["start"] < nxt and p["end"] > p["start"]]
        if not cands:
            out.append({"role": g["role"], "first_audio": None})
            continue
        p = min(cands, key=lambda x: x["start"])
        r = trace["responses"][p["resp"]]
        llm_steps = [s for s in r["steps"] if s["kind"] == "llm"]
        tools = [s for s in r["steps"] if s["kind"] == "tool" and s["start"] < p["start"]]
        asr = next((s["dur"] for s in r["steps"] if s["kind"] == "asr"), 0.0)
        spoke_step = llm_steps[p["step"]]
        llm_time = sum(s["dur"] for s in llm_steps[: p["step"]]) + (spoke_step["t_first_chunk"] or spoke_step["dur"])
        ans = r.get("answer_audio")
        out.append({"role": g["role"], "first_audio": round(p["start"] - g["end"], 3),
                    "answer_audio": round(ans - g["end"], 3) if ans is not None and ans >= g["end"] else None,
                    "endpoint_wait": round(r["t_endpoint"] - g["end"], 3), "asr": asr,
                    "llm": round(llm_time, 3), "tools": round(sum(s["dur"] for s in tools), 3),
                    "tts": p["tts_dur"], "n_llm_calls_before_audio": p["step"] + 1})
    return out


def slot_hits(trace, case):
    text = " ".join(r.get("asr_text", "") for r in trace.get("responses", [])).lower()
    text_ns = text.replace(" ", "")
    hits = []
    for alts in case.get("slots", []):
        hits.append(any(a.lower() in text or a.lower().replace(" ", "") in text_ns for a in alts))
    return {"all": all(hits), "missing": [alts[0] for alts, h in zip(case.get("slots", []), hits) if not h],
            "asr_texts": [r.get("asr_text", "") for r in trace.get("responses", [])]}


def load_cases(path=None):
    from build_audio import expand
    cases = json.loads(Path(path or ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    return {c["id"]: c for c in expand(cases)}


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 3)


def summarize(scores):
    s = {}
    for arm, rows in scores.items():
        task = [r["task_pass"] for r in rows]
        inter = [r["interaction_pass"] for r in rows if r.get("interaction_pass") is not None]
        both = [r["task_pass"] and (r.get("interaction_pass") in (True, None)) for r in rows]
        lat = [x["first_audio"] for r in rows if r["cat"] in ("task", "noise", "pause") for x in r.get("latency", [])
               if x.get("first_audio") is not None and x["role"] == "request"]
        stops = [r["stop_latency"] for r in rows if "stop_latency" in r]
        d = {"n": len(rows), "task_pass": sum(task), "interaction_pass": f"{sum(inter)}/{len(inter)}",
             "strict_pass": sum(both), "harness_errors": sum(1 for r in rows if "harness_error" in r),
             "latency_first_audio_median": pct(lat, 0.5), "latency_first_audio_p90": pct(lat, 0.9),
             "stop_latency_median": pct(stops, 0.5), "stops_measured": len(stops),
             "reasoning_said_aloud": sum(1 for r in rows if r.get("leak"))}
        by = {}
        for r in rows:
            k = r["cat"] if r["cat"] != "noise" else f"noise-{r['noise']}"
            b = by.setdefault(k, [0, 0])
            b[0] += r["task_pass"] and (r.get("interaction_pass") in (True, None))
            b[1] += 1
        d["strict_by_cat"] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(by.items())}
        s[arm] = d
    return s


def main(dirs, cases_path=None):
    cases = load_cases(cases_path)
    for d in dirs:
        d = Path(d)
        scores = {}
        for f in sorted(d.glob("*.jsonl")):
            arm = f.stem
            rows = []
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    t = json.loads(line)
                    rows.append(score_item(t, cases[t["item"]]))
            scores[arm] = rows
        summ = summarize(scores)
        (d / "scores.json").write_text(json.dumps({"summary": summ, "items": scores}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
        print(d.name, json.dumps(summ, ensure_ascii=False, indent=1))


def self_check():
    """Constructed traces with known answers; must all come out as stated."""
    cases = load_cases()
    seed = {k: {**v, "title": "x"} for k, v in SEED.items()}
    ok = []
    # T03 correct: one new meeting
    t = {"arm": "oracle", "item": "T03", "responses": [{"steps": []}],
         "final_state": {"meetings": {**seed, "M004": {"title": "预算", "date": "2026-11-17", "start_time": "15:00",
                                                      "duration_minutes": 60, "attendees": ["李娜"]}}, "reminders": []}}
    ok.append(score_item(t, cases["T03"])["task_pass"] is True)
    # T03 duplicate meeting -> fail
    t2 = json.loads(json.dumps(t))
    t2["final_state"]["meetings"]["M005"] = dict(t2["final_state"]["meetings"]["M004"])
    ok.append(score_item(t2, cases["T03"])["task_pass"] is False)
    # T01 oracle: weather call + number said
    t3 = {"arm": "oracle", "item": "T01", "final_state": {"meetings": seed, "reminders": []},
          "responses": [{"steps": [{"kind": "tool", "name": "get_weather", "input": {}, "result":
                         '{"city": "上海", "date": "2026-11-17", "condition": "小雨", "high_c": 18, "low_c": 12}'},
                                   {"kind": "llm", "text": "明天上海小雨，最高18度。", "tool_uses": []}]}]}
    ok.append(score_item(t3, cases["T01"])["task_pass"] is True)
    # T10: a temperature in the reply fails
    t4 = {"arm": "oracle", "item": "T10", "final_state": {"meetings": seed, "reminders": []},
          "responses": [{"steps": [{"kind": "llm", "text": "西安明天大概十五度。", "tool_uses": []}]}]}
    ok.append(score_item(t4, cases["T10"])["task_pass"] is False)
    # B01 audio: barge-in during the backchannel -> interaction fail
    t5 = {"arm": "vad", "item": "B01", "final_state": {"meetings": seed, "reminders": []},
          "responses": [{"t_endpoint": 2.6, "answer_audio": 3.5, "steps": [
              {"kind": "asr", "dur": 0.1}, {"kind": "llm", "dur": 0.8, "t_first_chunk": 0.5}]}],
          "user_segments": [{"role": "request", "start": 0.8, "end": 2.0}, {"role": "backchannel", "start": 5.0, "end": 5.4}],
          "pieces": [{"resp": 0, "step": 0, "text": "明天有两个会。", "start": 3.5, "end": 5.3, "full_end": 8.0, "tts_dur": 0.3}],
          "barge_ins": [{"t_detect": 5.3, "onset_vad": 5.0, "heard": ""}]}
    r5 = score_item(t5, cases["B01"])
    ok.append(r5["interaction_pass"] is False and r5["overlap"] is True)
    # heard text: only the played part counts
    ok.append(heard_text({"arm": "vad", "pieces": [{"text": "abcdefghij", "start": 0, "end": 1, "full_end": 2}]}) == "abcde")
    print("self-check:", "PASS" if all(ok) else f"FAIL {ok}")
    return all(ok)


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        sys.exit(0 if self_check() else 1)
    args = sys.argv[1:]
    cp = None
    if args[:1] == ["--cases"]:
        cp, args = args[1], args[2:]
    main(args, cp)
