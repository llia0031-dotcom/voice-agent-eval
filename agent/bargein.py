"""Barge-in by words: while the agent is talking, the user's speech stops it only once the transcript holds
enough words that are not backchannels ("嗯", "好的", "Okay").

Same idea as Pipecat's MinWordsUserTurnStartStrategy and LiveKit's interruption min_words, plus a list of
backchannel words that do not count (the filler-word proposal in livekit/agents issue 4450). Chinese has no
spaces, so one Chinese character counts as one unit and one English word counts as one unit.

A transcript is cut into phrases at punctuation. A phrase made only of backchannel words counts 0; any other
phrase counts all its units. The list and MIN_UNITS are fixed in eval/PREREGISTRATION.md (addendum A1).
"""
import re

MIN_UNITS = 2

BACKCHANNEL_ZH = [
    "嗯", "恩", "摁", "唔", "哦", "噢", "喔", "啊", "呃", "额", "诶", "欸", "哎", "好", "对", "是", "行",
    "嗯哼", "好的", "好滴", "好嘞", "好吧", "对的", "是的", "是啊", "没错", "明白", "明白了", "了解", "知道",
    "知道了", "收到", "懂了",
]
BACKCHANNEL_EN = [
    "ok", "okay", "okey", "k", "mm", "mhm", "mmhmm", "mm-hmm", "hmm", "hm", "uh-huh", "uh", "huh", "um",
    "yeah", "yep", "yup", "yes", "right", "sure", "alright", "cool", "nice", "great", "i see", "got it", "gotcha",
]

_UNIT = re.compile(r"[a-z0-9]+(?:['’-][a-z0-9]+)*|[^\W\d_a-z]")
_SPLIT = re.compile(r"[^\w\s'’-]+")       # punctuation (any script) ends a phrase


def units(text: str) -> list[str]:
    return _UNIT.findall(text.lower())


def _tokens():
    out = []
    for w in BACKCHANNEL_ZH + BACKCHANNEL_EN:
        out.append(tuple(units(w)))
    return sorted(set(out), key=len, reverse=True)


TOKENS = _tokens()


def is_backchannel_phrase(us: list[str]) -> bool:
    """True if the units are made only of backchannel words (longest match first)."""
    i = 0
    while i < len(us):
        for tok in TOKENS:
            if tuple(us[i:i + len(tok)]) == tok:
                i += len(tok)
                break
        else:
            return False
    return True


def content_units(text: str) -> int:
    """Units in the transcript that are not backchannel words."""
    n = 0
    for phrase in _SPLIT.split(text.lower()):
        us = units(phrase)
        if us and not is_backchannel_phrase(us):
            n += len(us)
    return n
