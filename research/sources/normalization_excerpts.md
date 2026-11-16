# Making the model's text speakable, and saying values exactly: saved excerpts (fetched 2026-11-15)

Short quotes only, copied from the pages on 2026-11-15. Used for PREREGISTRATION addendum A13.

## ElevenLabs Agents, prompting guide, https://elevenlabs.io/docs/eleven-agents/best-practices/prompting-guide

Section "Text normalization":

> Text-to-speech models, especially faster ones, are best at generating speech from alphabetical text.

> To address this, we normalize non-alphabetical text into words before it reaches the TTS model

Section "Normalization strategies" (setting `text_normalisation_type`):

> `system_prompt` (default): Adds instructions to the system prompt telling the LLM to write out numbers and symbols as words

> `elevenlabs`: Uses our TTS normalizer to normalize text after LLM generation, before it reaches the TTS model.

Listed trade-offs: for `system_prompt`, "No additional latency" and "LLMs may occasionally fail to normalize correctly"; for `elevenlabs`, "More reliable than LLM-based normalization" and "Adds minor latency".

## LiveKit Agents, pipeline nodes and hooks, https://docs.livekit.io/agents/logic/nodes.md

Section "Overview":

> Modify LLM output before sending it to TTS to customize pronunciation.

Section "TTS node":

> The `tts_node` synthesizes audio from text segments, converting the LLM output into speech.

Signature shown: `async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings)`.

## OpenAI, prompting realtime models, https://developers.openai.com/api/docs/guides/voice-prompting.md

Section "Capture exact entities", "Confirm exact identifiers before tool calls":

> For numeric identifiers, read the value back digit by digit.

Section "Normalize spoken numbers carefully":

> If multiple interpretations are plausible, ask the user to clarify before using the value.

## What none of them covers

None of the three pages discusses a duration that is already written in words but can be heard two ways, as 「开一个半小时的会」 can (one half-hour meeting, or a meeting of an hour and a half). The normalizers turn digits and symbols into words; this phrase has neither.
