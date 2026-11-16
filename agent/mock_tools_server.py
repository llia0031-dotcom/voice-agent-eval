"""Fake office tools served over MCP (stdio): weather, calendar, reminders.

All data is invented and deterministic. Tools whose names start with ``admin_`` are for the
eval harness only (reset and read the state); the agent never sees them.
Run: python mock_tools_server.py
"""
import copy
import json
import re

from mcp.server.mcpserver import MCPServer

TODAY = "2026-11-16"  # Monday; the agent's system prompt uses the same date

CITY_ALIASES = {
    "北京": ["beijing", "北京市"], "上海": ["shanghai", "上海市"], "杭州": ["hangzhou"],
    "深圳": ["shenzhen"], "广州": ["guangzhou"], "成都": ["chengdu"],
    "新加坡": ["singapore"], "伦敦": ["london"],
}
WEATHER = {  # city -> date -> (condition, high °C, low °C)
    "北京": {"2026-11-16": ("晴", 9, -1), "2026-11-17": ("多云", 7, -2), "2026-11-18": ("晴", 10, 0)},
    "上海": {"2026-11-16": ("多云", 16, 10), "2026-11-17": ("小雨", 18, 12), "2026-11-18": ("阴", 15, 11)},
    "杭州": {"2026-11-16": ("小雨", 15, 9), "2026-11-17": ("阴", 17, 10), "2026-11-18": ("中雨", 13, 8)},
    "深圳": {"2026-11-16": ("晴", 27, 19), "2026-11-17": ("多云", 26, 20), "2026-11-18": ("雷阵雨", 24, 19)},
    "广州": {"2026-11-16": ("晴", 26, 17), "2026-11-17": ("晴", 25, 16), "2026-11-18": ("多云", 23, 16)},
    "成都": {"2026-11-16": ("阴", 14, 9), "2026-11-17": ("小雨", 12, 8), "2026-11-18": ("阴", 13, 8)},
    "新加坡": {"2026-11-16": ("雷阵雨", 31, 25), "2026-11-17": ("雷阵雨", 30, 25), "2026-11-18": ("多云", 32, 26)},
    "伦敦": {"2026-11-16": ("阴", 11, 6), "2026-11-17": ("小雨", 10, 5), "2026-11-18": ("多云", 12, 7)},
}
SEED_MEETINGS = {
    "M001": {"title": "周会", "date": "2026-11-17", "start_time": "10:00", "duration_minutes": 60,
             "attendees": ["张伟", "李娜", "王强"]},
    "M002": {"title": "设计评审", "date": "2026-11-17", "start_time": "14:00", "duration_minutes": 60,
             "attendees": ["陈静", "刘洋"]},
    "M003": {"title": "1:1 with Tom", "date": "2026-11-18", "start_time": "16:00", "duration_minutes": 30,
             "attendees": ["Tom Lee"]},
}

STATE = {}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _reset():
    STATE.clear()
    STATE.update({"meetings": copy.deepcopy(SEED_MEETINGS), "reminders": [], "next_id": 4, "log": []})


def _log(name, args, result):
    STATE["log"].append({"tool": name, "args": args, "result": result})
    return result


def _city(name: str):
    n = name.strip().lower().replace(" ", "")
    for city, aliases in CITY_ALIASES.items():
        if n == city or n in aliases or n.rstrip("市") == city:
            return city
    return None


def _check_date(d):
    return None if DATE_RE.match(d or "") else f"date must be YYYY-MM-DD, got {d!r}"


def _check_time(t):
    return None if TIME_RE.match(t or "") else f"time must be HH:MM (24h), got {t!r}"


_reset()
server = MCPServer("office-tools")


@server.tool(description="Get the weather forecast for one city and one date. Data exists for "
             "2026-11-16 to 2026-11-18 only.")
def get_weather(city: str, date: str) -> str:
    args = {"city": city, "date": date}
    err = _check_date(date)
    c = _city(city)
    if err:
        return json.dumps(_log("get_weather", args, {"error": err}), ensure_ascii=False)
    if not c:
        return json.dumps(_log("get_weather", args, {"error": f"no forecast for city {city!r}"}), ensure_ascii=False)
    if date not in WEATHER[c]:
        return json.dumps(_log("get_weather", args, {"error": f"no forecast for {date}"}), ensure_ascii=False)
    cond, hi, lo = WEATHER[c][date]
    return json.dumps(_log("get_weather", args, {"city": c, "date": date, "condition": cond,
                                                  "high_c": hi, "low_c": lo}), ensure_ascii=False)


@server.tool(description="List the user's meetings on one date (YYYY-MM-DD).")
def list_meetings(date: str) -> str:
    args = {"date": date}
    err = _check_date(date)
    if err:
        return json.dumps(_log("list_meetings", args, {"error": err}), ensure_ascii=False)
    items = [{"meeting_id": k, **v} for k, v in sorted(STATE["meetings"].items(),
             key=lambda kv: (kv[1]["date"], kv[1]["start_time"])) if v["date"] == date]
    return json.dumps(_log("list_meetings", args, {"meetings": items}), ensure_ascii=False)


@server.tool(description="Create a meeting. date YYYY-MM-DD, start_time HH:MM (24h), attendees are names.")
def create_meeting(title: str, date: str, start_time: str, duration_minutes: int, attendees: list[str]) -> str:
    args = {"title": title, "date": date, "start_time": start_time,
            "duration_minutes": duration_minutes, "attendees": attendees}
    err = _check_date(date) or _check_time(start_time)
    if err:
        return json.dumps(_log("create_meeting", args, {"error": err}), ensure_ascii=False)
    mid = f"M{STATE['next_id']:03d}"
    STATE["next_id"] += 1
    STATE["meetings"][mid] = {"title": title, "date": date, "start_time": start_time,
                              "duration_minutes": int(duration_minutes), "attendees": list(attendees)}
    return json.dumps(_log("create_meeting", args, {"status": "created", "meeting_id": mid}), ensure_ascii=False)


@server.tool(description="Change fields of an existing meeting. Pass only the fields to change.")
def update_meeting(meeting_id: str, title: str | None = None, date: str | None = None,
                   start_time: str | None = None, duration_minutes: int | None = None,
                   attendees: list[str] | None = None) -> str:
    args = {k: v for k, v in {"meeting_id": meeting_id, "title": title, "date": date, "start_time": start_time,
            "duration_minutes": duration_minutes, "attendees": attendees}.items() if v is not None}
    m = STATE["meetings"].get(meeting_id)
    if not m:
        return json.dumps(_log("update_meeting", args, {"error": f"no meeting {meeting_id!r}"}), ensure_ascii=False)
    err = (date and _check_date(date)) or (start_time and _check_time(start_time))
    if err:
        return json.dumps(_log("update_meeting", args, {"error": err}), ensure_ascii=False)
    for k in ("title", "date", "start_time", "duration_minutes", "attendees"):
        if args.get(k) is not None:
            m[k] = args[k]
    return json.dumps(_log("update_meeting", args, {"status": "updated", "meeting_id": meeting_id}), ensure_ascii=False)


@server.tool(description="Cancel (delete) an existing meeting.")
def cancel_meeting(meeting_id: str) -> str:
    args = {"meeting_id": meeting_id}
    if meeting_id not in STATE["meetings"]:
        return json.dumps(_log("cancel_meeting", args, {"error": f"no meeting {meeting_id!r}"}), ensure_ascii=False)
    del STATE["meetings"][meeting_id]
    return json.dumps(_log("cancel_meeting", args, {"status": "cancelled", "meeting_id": meeting_id}), ensure_ascii=False)


@server.tool(description="Set a reminder. date YYYY-MM-DD, time HH:MM (24h).")
def set_reminder(text: str, date: str, time: str) -> str:
    args = {"text": text, "date": date, "time": time}
    err = _check_date(date) or _check_time(time)
    if err:
        return json.dumps(_log("set_reminder", args, {"error": err}), ensure_ascii=False)
    STATE["reminders"].append({"text": text, "date": date, "time": time})
    return json.dumps(_log("set_reminder", args, {"status": "set"}), ensure_ascii=False)


@server.tool(description="Harness only: reset all data to the seed state.")
def admin_reset() -> str:
    _reset()
    return "ok"


@server.tool(description="Harness only: return the full state and the call log.")
def admin_state() -> str:
    return json.dumps(STATE, ensure_ascii=False)


if __name__ == "__main__":
    server.run("stdio")
