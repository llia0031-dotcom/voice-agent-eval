"""Claude call with streaming and timing, plus the bridge from MCP tools to Claude tool definitions."""
import asyncio
import json
import time

import anthropic

from config import LLM_EFFORT, LLM_MAX_TOKENS, LLM_MODEL, load_api_key

SYSTEM = """你是一个语音助手，用户用语音和你说话，你看到的是语音识别的文字，可能有错字或同音字。
现在是 2026 年 11 月 16 日星期一上午 9:00（北京时间）。今天 = 2026-11-16，明天 = 2026-11-17，后天 = 2026-11-18。
通讯录：张伟、李娜、王强、刘洋、陈静、Tom Lee、Emma Smith。识别出的人名和通讯录里的读音相近时，用通讯录里的写法。

规则：
- 回答的语言跟用户最近一句话的语言一致：用户说英文，你就全部用英文回答（English only）；用户说中文，就用中文。
- 你的回答会被读出来：用口语，一般一两句话，不用列表、表情或特殊符号。不要解释你怎么理解识别结果，也不要把思考过程说出来。
- 需要信息时调用工具，只说工具返回的内容，不编数字。
- 要做的事信息不全时（比如没说时间），先问清楚再做。
- 新建会议没说时长就用 30 分钟。修改已有的会议用 update_meeting，不要另建一个；需要会议编号时先用 list_meetings 查。
- 被用户打断时，按用户新说的话处理。
- 调用工具前可以先说一句很短的话（十个字以内，比如“好的，我查一下”），也可以不说。
- 没有工具能做用户要的事时，直接说做不到，不要猜。不要在回答里写任何 XML 标签。"""

# Added to the rules only for arms with say_minutes (PREREGISTRATION addendum A13). Said after 「开个」, the
# phrase 「半小时」 became 「开一个半小时的会」, which a listener hears as 90 minutes.
SAY_MINUTES = "- 说会议时长时，照工具参数里的分钟数说成“N分钟”（比如“30分钟”“90分钟”），不要说“半小时”“一个半小时”这类说法，免得听错。"


def system_prompt(say_minutes: bool = False) -> str:
    return SYSTEM + "\n" + SAY_MINUTES if say_minutes else SYSTEM


CHUNK_END = set("。！？!?；;，,、\n")


def first_chunk_end(text: str, min_chars: int = 4, colon: bool = False) -> int | None:
    """Index just after the first punctuation that closes a speakable chunk of at least min_chars.
    colon=True also closes a chunk at a full-width colon, or at an ASCII colon followed by a space (not 10:00)."""
    for i, ch in enumerate(text):
        spaced = i + 1 < len(text) and text[i + 1].isspace()
        closes = ch in CHUNK_END or (ch == "." and spaced) or (colon and (ch == "：" or (ch == ":" and spaced)))
        if closes and len(text[: i + 1].strip()) >= min_chars:
            return i + 1
    return None


def new_bounds(text: str, pos: int, first_min: int = 4, colon: bool = False) -> list[int]:
    """End indexes of the chunks that text completes beyond pos: the first chunk by the first-chunk rule, later
    ones by the rule split_chunks uses (pipeline.py), so they match the chunks spoken from the final text."""
    out = []
    while True:
        k = first_chunk_end(text, first_min, colon) if pos == 0 else first_chunk_end(text[pos:])
        if not k:
            return out
        pos += k
        out.append(pos)


def mcp_tools_to_claude(tools) -> list[dict]:
    out = []
    for t in tools:
        if t.name.startswith("admin_"):
            continue
        out.append({"name": t.name, "description": t.description or "", "input_schema": t.input_schema})
    return out


class LLM:
    def __init__(self, thinking: str = "disabled", first_chunk_min: int = 4, first_chunk_colon: bool = False,
                 say_minutes: bool = False):
        self.thinking = thinking
        self.system = system_prompt(say_minutes)
        self.first_chunk_min, self.first_chunk_colon = first_chunk_min, first_chunk_colon   # rule for the first chunk only
        # The SDK's own retries would hide waiting time inside a measured call, so they are off;
        # turn() retries itself and times only the attempt that succeeds.
        self.client = anthropic.AsyncAnthropic(api_key=load_api_key(), base_url="https://api.anthropic.com",
                                               max_retries=0, timeout=60.0)
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "retries": 0}

    async def turn(self, messages: list, tools: list) -> dict:
        """One streamed request, retried on rate limits and transient errors. Timings are from the start
        of the successful attempt; time spent waiting to retry is reported separately."""
        waited = 0.0
        for attempt in range(10):
            try:
                r = await self._attempt(messages, tools)
                r["retry_wait"] = round(waited, 2)
                r["attempts"] = attempt + 1
                return r
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
                delay = min(60.0, 5.0 * 2 ** attempt)
                ra = getattr(getattr(e, "response", None), "headers", {}) or {}
                if ra.get("retry-after"):
                    try:
                        delay = max(delay, float(ra["retry-after"]))
                    except ValueError:
                        pass
                self.usage["retries"] += 1
                waited += delay
                await asyncio.sleep(delay)
        raise RuntimeError("model call failed after 10 attempts")

    async def _attempt(self, messages: list, tools: list) -> dict:
        t0 = time.perf_counter()
        first_text = None
        chunk = None
        text = ""
        bounds, pos = [], 0         # (seconds, end index) of every chunk as soon as its text is complete
        async with self.client.messages.stream(
            model=LLM_MODEL, max_tokens=LLM_MAX_TOKENS, system=self.system, tools=tools, messages=messages,
            thinking={"type": self.thinking}, output_config={"effort": LLM_EFFORT},
        ) as stream:
            async for ev in stream:
                if ev.type == "text":
                    if first_text is None:
                        first_text = time.perf_counter() - t0
                    text += ev.text
                    if chunk is None:
                        k = first_chunk_end(text, self.first_chunk_min, self.first_chunk_colon)
                        if k:
                            chunk = (time.perf_counter() - t0, text[:k])
                    for e in new_bounds(text, pos, self.first_chunk_min, self.first_chunk_colon):
                        pos = e
                        bounds.append((round(time.perf_counter() - t0, 4), e))
            msg = await stream.get_final_message()
        done = time.perf_counter() - t0
        u = msg.usage
        self.usage["input_tokens"] += u.input_tokens
        self.usage["output_tokens"] += u.output_tokens
        self.usage["calls"] += 1
        full_text = "".join(b.text for b in msg.content if b.type == "text")
        if full_text.strip() and chunk is None:
            chunk = (done, full_text)
        tool_uses = [{"id": b.id, "name": b.name, "input": b.input} for b in msg.content if b.type == "tool_use"]
        return {
            "content": [b.model_dump(exclude_none=True) for b in msg.content],
            "text": full_text, "tool_uses": tool_uses, "stop_reason": msg.stop_reason,
            "t_first_text": first_text, "t_first_chunk": chunk[0] if chunk else None,
            "first_chunk": chunk[1] if chunk else "", "t_done": done,
            "chunk_bounds": bounds + ([(round(done, 4), len(full_text))] if full_text and pos < len(full_text) else []),
            "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
        }


def tool_result_block(tool_use_id: str, result) -> dict:
    texts = [getattr(c, "text", "") for c in result.content]
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": "\n".join(texts),
            **({"is_error": True} if result.is_error else {})}


def dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False)
