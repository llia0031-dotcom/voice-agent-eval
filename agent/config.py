"""Paths, model settings and the API key loader shared by the agent and the eval scripts."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Models, Python environments and generated audio live outside the project folder, in PORTFOLIO_LOCAL
# (default: a folder named portfolio-local in the home directory).
LOCAL = Path(os.environ.get("PORTFOLIO_LOCAL") or Path.home() / "portfolio-local")
MODELS = LOCAL / "voice-models"
DATA = LOCAL / "voice-eval-data"          # generated audio lives here, outside the synced folder

SR = 16000                                # every pipeline signal is 16 kHz mono float32
FRAME = 512                               # Silero VAD window: 32 ms

LLM_MODEL = "claude-haiku-5-5"
LLM_EFFORT = "low"
LLM_MAX_TOKENS = 1024

# Turn-taking settings for the two arms (see docs/DECISIONS.md D-V05).
VAD_ON = 0.5            # speech probability above this = speech
VAD_OFF = 0.35          # below this = silence; in between keeps the previous state
START_SECS = 0.2        # this much continuous speech starts a user turn or a barge-in
ARMS = {
    "vad":       {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "disabled"},
    "smart":     {"endpoint_silence": 0.2,  "smart_turn": True, "smart_turn_fallback": 3.0, "thinking": "disabled"},
    "vad-think": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive"},
    # as vad-think, but speech heard while the agent talks stops it only after 2 non-backchannel units
    # (agent/bargein.py; PREREGISTRATION addendum A1)
    "vad-think-words": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                        "barge_min_units": 2, "barge_check_every": 0.16},
    # as vad-think-words, but the held speech is read in the language of the user's last turn (zh or en)
    # instead of auto-detect (PREREGISTRATION addendum A2)
    "vad-think-words-lang": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                             "barge_min_units": 2, "barge_check_every": 0.16, "hold_lang": True},
    # as vad-think-words, but the held speech must also have lasted 0.5 s (LiveKit's default min_duration)
    # (PREREGISTRATION addendum A3)
    "vad-think-words-dur": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                            "barge_min_units": 2, "barge_check_every": 0.16, "barge_min_speech": 0.5},
    # as vad-think, the agent goes silent at 0.2 s of speech, but by pausing: the held speech is then judged by
    # the vad-think-words-dur rule; a real interruption cancels the reply, anything else resumes it from where
    # it stopped (LiveKit resume_false_interruption) as soon as the verdict is in (PREREGISTRATION addendum A4)
    "vad-think-pause": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                        "barge_min_units": 2, "barge_check_every": 0.16, "barge_min_speech": 0.5,
                        "pause": True, "pause_resume_after": 0.0},
    # as vad-think, but the first speech chunk of each reply step may be as short as 2 characters ("好的，") and
    # may also end at a colon; later chunks unchanged (PREREGISTRATION addendum A5)
    "vad-think-short": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                        "first_chunk_min": 2, "first_chunk_colon": True},
    # as vad-think, but cancel_meeting runs only in the turn after the user has heard a confirmation question
    # (per-tool approval as in OpenAI Agents SDK needs_approval / LangChain interrupt_on; PREREGISTRATION addendum A6)
    "vad-think-confirm": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive",
                          "confirm_tools": ["cancel_meeting"]},
    # as vad-think, but every listening decision uses FireRedChat pVAD instead of Silero: speech of any speaker
    # until the first turn ends, then only the speaker of that first utterance (PREREGISTRATION addendum A7)
    "vad-think-pvad": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True},
    # the four changes that helped, together: pVAD (A7), short first chunk (A5), confirm before cancelling (A6),
    # pause then cancel or resume with the A3 verdict (A4) (PREREGISTRATION addendum A8)
    "vad-think-combo": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                        "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                        "barge_min_units": 2, "barge_check_every": 0.16, "barge_min_speech": 0.5,
                        "pause": True, "pause_resume_after": 0.0},
    # as vad-think-combo, but the held cancel asks for a brief, direct question (PREREGISTRATION addendum A9)
    "vad-think-combo-brief": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                              "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                              "confirm_brief": True, "barge_min_units": 2, "barge_check_every": 0.16,
                              "barge_min_speech": 0.5, "pause": True, "pause_resume_after": 0.0},
    # as vad-think-combo, but a reply the user started talking over before its first sound is dropped as unheard
    # and the two halves stay one turn (PREREGISTRATION addendum A10)
    "vad-think-combo-merge": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                              "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                              "spoke_first": True, "barge_min_units": 2, "barge_check_every": 0.16,
                              "barge_min_speech": 0.5, "pause": True, "pause_resume_after": 0.0},
    # as vad-think-combo, but each later speech chunk is synthesized as soon as its text has streamed in, not after
    # the whole reply text (PREREGISTRATION addendum A11)
    "vad-think-combo-stream": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                               "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                               "stream_tts": True, "barge_min_units": 2, "barge_check_every": 0.16,
                               "barge_min_speech": 0.5, "pause": True, "pause_resume_after": 0.0},
    # as vad-think-combo, but the system prompt asks for meeting durations in minutes (PREREGISTRATION addendum A13)
    "vad-think-combo-minutes": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                                "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                                "say_minutes": True, "barge_min_units": 2, "barge_check_every": 0.16,
                                "barge_min_speech": 0.5, "pause": True, "pause_resume_after": 0.0},
    # vad-think-combo with the four follow-ups together: brief confirmation (A9), spoke-first merge (A10), streamed
    # synthesis of later chunks (A11) and durations in minutes (A13) (PREREGISTRATION addendum A14)
    "vad-think-combo-plus": {"endpoint_silence": 0.55, "smart_turn": False, "thinking": "adaptive", "pvad": True,
                             "first_chunk_min": 2, "first_chunk_colon": True, "confirm_tools": ["cancel_meeting"],
                             "confirm_brief": True, "spoke_first": True, "stream_tts": True, "say_minutes": True,
                             "barge_min_units": 2, "barge_check_every": 0.16, "barge_min_speech": 0.5,
                             "pause": True, "pause_resume_after": 0.0},
    "oracle":    {"thinking": "disabled"},   # text only, no audio
}
MAX_TURN_SECS = 20.0    # forced end of a user turn that never goes silent


def load_api_key() -> str:
    """Read ANTHROPIC_API_KEY from the .env file named by VOICE_EVAL_ENV_FILE (default ./.env).

    The process environment's own ANTHROPIC_* values are never used.
    """
    path = Path(os.environ.get("VOICE_EVAL_ENV_FILE", ROOT / ".env"))
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"ANTHROPIC_API_KEY not found in {path}")


def scrub_anthropic_env() -> None:
    """Drop inherited ANTHROPIC_* variables so the SDK cannot pick them up."""
    for k in list(os.environ):
        if k.startswith("ANTHROPIC_"):
            del os.environ[k]
