# Voice agent evaluation

How does a cascaded voice agent (voice activity detection → speech recognition → an LLM with tools → speech synthesis) behave when a person pauses mid-sentence, interrupts it, says "嗯" while it talks, or talks with other people in the background, and does it do the task right? This repository measures that on 42 scripted Chinese, English and code-switched conversations, then tests fixes one at a time against the same items.

**Live demo:** [jason-d-e.github.io/voice-agent-eval](https://jason-d-e.github.io/voice-agent-eval/) (Chinese; [English](https://jason-d-e.github.io/voice-agent-eval/en.html)). Listen to the recordings, see each conversation's timeline, and compare the first round with the fixes. All user voices are synthetic.

## What it found

From [`eval/EVALUATION.md`](eval/EVALUATION.md), two runs of every arm:

- **Listening, not the model, is what breaks the experience.** With perfect transcripts and turn-taking the same model, prompt and tools pass 41 of 42 items in both runs. With audio, about 30 pass.
- **Background talk ran the conversation.** Silero VAD marked 99.6% of four-talker babble frames as speech, so every babble turn waited for the 20 s cap and was later cut off mid-reply. A voice-activity model that follows the first speaker (FireRedChat pVAD) ended every babble turn when the user stopped, with a first-audio median of 4.56 s instead of 20.4 s (section 6.14).
- **A fast stop and a kept reply are both possible.** Pausing at once and deciding afterwards kept the 0.26 s stop on interruptions and resumed the reply after 6 of 8 backchannels (section 6.10). Waiting for words before stopping talked through more backchannels, but made every real stop later (sections 6.7 to 6.9).
- **"Wait, don't cancel" only works if the agent asks first.** In every arm the meeting was cancelled before the user could object. A spoken confirmation fixed it in both runs; a brief question cut the cost from 11 s to 8.5 s per cancel (sections 6.13 and 6.16).
- **The fixes work together.** With all four changes, no babble turn was held or cut, every interruption stopped within 0.36 s, every reply survived its backchannel and "wait" stopped the cancellation (section 6.15). Four later follow-ups added on top kept their gains, except streamed synthesis: the silences left come from synthesis time, not from waiting for text (section 6.22).
- **Disfluent speech hurts through recognition, not reasoning.** From text, the model handled every repetition, correction and restart. From audio, the failures came from a filler written as a character, such as 「呃」 heard as 「鄂」, which changed the request's meaning (section 6.19).
- **What the agent says about a change matches what it did, with one repeated slip.** 605 of 628 rated confirmations were consistent (96%). The other 23 were all one slip: a half-hour meeting booked correctly, then announced as 「一个半小时」 before a correction (section 6.20). One rule in the system prompt, asking for durations in minutes, removed it: none of 104 item-runs had it afterwards (section 6.21).

## How it was evaluated

- Items, answers and scoring rules were fixed before each run in [`eval/PREREGISTRATION.md`](eval/PREREGISTRATION.md). Every follow-up has its own addendum with written expectations, file fingerprints and a run log. Expectations that did not hold are reported as such.
- Every arm ran twice over all items. Model: `claude-haiku-5-5`, effort low.
- User speech is synthetic (Kokoro), checked by reading it back with two recognizers. Speech steps run on one CPU, and their time is taken from a calibration so that the virtual clock does not depend on machine load.
- Offline tests (`tests/test_offline.py`) cover the timing model and every follow-up rule without model calls.

## Place in the portfolio

This project is the **interaction** case in a small portfolio built around one idea: an AI system should show its evidence. The other cases cover answering from documents, judging and generating. They share two things:

- **The method.** A plan, items and answers are written before anything runs, each change is retested against the same items, and changes in a score are explained.
- **One checking component, [evidence-check](https://github.com/Jason-d-e/evidence-check)** (MIT). Here it checks the agent's spoken confirmations, such as "已设置提醒：明天上午9点", against the record of the tool calls behind them ([`eval/confirm_consistency.py`](eval/confirm_consistency.py), report section 6.20).

## Reproduce

Commands for each section are in section 11 of the report. Models, Python environments and generated audio live outside the repository, in the folder named by `PORTFOLIO_LOCAL` (default: `portfolio-local` in your home directory): models in `voice-models/`, audio in `voice-eval-data/`. Model calls need an API key in a `.env` file named by `VOICE_EVAL_ENV_FILE`. The offline tests and all scoring and comparison scripts make no model calls.

- **Python packages:** `requirements.txt` (Python 3.12). The two scripts that need PyTorch, `eval/pvad_enroll.py` and `eval/bcdet_offline_check.py`, run in a second environment with `maai` 0.2.27, `speechbrain` 1.1.2, `torch` and `torchaudio`.
- **User speech:** `python -X utf8 eval/build_audio.py` writes it; `eval/audio_manifest.json` holds the fingerprints it should match.
- **Models** (not included; each keeps its own licence):

| Model | Used for | Where to get it | Licence |
|---|---|---|---|
| Silero VAD (`silero_vad.onnx`) | voice activity | sherpa-onnx releases, asr-models | MIT |
| SenseVoice-Small int8, 2024-07-17 | speech recognition | sherpa-onnx releases, asr-models | FunASR Model Open Source License 1.1 |
| Smart Turn v3.2, CPU (`smart-turn-v3.2-cpu.onnx`) | end of turn, `smart` arm | huggingface.co/pipecat-ai/smart-turn-v3 | BSD-2-Clause |
| Kokoro multi-lang v1.1 | the users' voices | sherpa-onnx releases, tts-models | Apache-2.0 |
| MeloTTS zh_en | the agent's voice | sherpa-onnx releases, tts-models | MIT |
| Whisper small | read-back check of the items only | sherpa-onnx releases, asr-models | MIT |
| FireRedChat pVAD, with the SpeechBrain ECAPA speaker model shipped beside it | the arms that listen to one speaker | huggingface.co/FireRedTeam/FireRedChat-pvad (Hugging Face cache in `voice-models/hf`) | Apache-2.0 |
| MaAI `bc_det`, Chinese and English, with the Mimi encoder | the offline check of section 6.11 only | downloaded by the `maai` package | model CC BY-NC-ND 4.0, Mimi CC BY 4.0; only results are reported here |

## Layout

```
agent/      the agent: listening, recognition, model calls, synthesis, the simulated timeline
eval/       items, audio building, runs, scoring, comparisons, preregistration and report
eval/results/  run records and generated tables (records of stopped or replaced runs, which the preregistration
               names under results/aborted/, are not included)
tests/      offline tests
research/sources/  short excerpts of the documentation and code the design decisions rely on, each with its source
docs/DECISIONS.md  the design decisions cited by number in the code and the report
```

## Licence

MIT, see `LICENSE`. The models listed above are not part of this repository and keep their own licences.
