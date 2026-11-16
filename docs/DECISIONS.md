# Design decisions referenced in the code and the report

Only the decisions that the code, `eval/PREREGISTRATION.md` or `eval/EVALUATION.md` cite by number. Each is described in full in those two files where it was used.

## D-V05 Three arms and a text-only control

- `vad`: a turn ends after 0.55 s of silence (the default of the LiveKit Silero plugin).
- `smart`: after 0.2 s of silence, Pipecat's Smart Turn v3.2 judges whether the user has finished; if not, the agent keeps waiting, with a 3 s fallback (Pipecat's defaults). The CPU benchmark on its model card gives 85.79% accuracy for Chinese, low among its languages, so it is worth testing.
- `vad-think`: as `vad`, with the model's adaptive thinking on. With thinking off, the model first says something like 「好的，我查一下」: the first word comes sooner, but it sometimes says its reasoning aloud. With thinking on there is no filler and the first word comes later. That trade-off is a product decision, so it is an arm of its own.
- `oracle`: no audio. The script's text is sent turn by turn to the same model and tools, to separate "heard wrong" from "thought wrong".
- Barge-in is the same in every arm: 0.2 s of continuous speech stops the agent (Pipecat's `start_secs` default).
- Model: `claude-haiku-5-5`, effort low.

## D-V11 A reply that has not started playing is dropped when the user goes on

A real player drops a queued reply when the user starts speaking. The first runs did not: in the few hundred milliseconds between the end of the model's reply and its first sound, a user who went on speaking was talked over. The harness now drops such a reply and keeps the user's turn whole. The items where this had happened in any arm or run (P02, P03, P05, P06, I07) were run again in every arm, by a rule fixed before rerunning ("Changes after the run", item 3).

## D-V15 Backchannels by word count, from existing rules

- Looked at (excerpts in `research/sources/interruption_settings_excerpts.md`):
  - LiveKit Agents: interruption settings `min_words`, `min_duration` (0.5 s), `false_interruption_timeout` and `resume_false_interruption`. Its adaptive interruption model runs only on LiveKit Cloud. Issue 4450 proposed ignoring filler words.
  - Pipecat: `MinWordsUserTurnStartStrategy`, which drops transcripts with too few words while the agent talks.
  - `bnovikov/bargein-classifier` on Hugging Face: English only. VAP-Realtime predicts when the agent should backchannel, the opposite direction.
- Used: Pipecat's word count plus the filler list proposed in issue 4450. Chinese has no spaces, so one character counts as one unit and one English word as one unit. The rule is a few dozen lines (`agent/bargein.py`), because the simulation runs on a virtual clock rather than inside either framework.

## D-V19 The Message Batches API is not used

Every model call is the agent's own reply in a live tool loop: the stream is timed, and each step waits for the previous tool result. Scoring uses fixed rules and calls no model. There is nothing to batch, so all calls use the standard interface.

## D-V20 An acoustic backchannel detector, tried offline

- Looked at (excerpts in `research/sources/backchannel_models_excerpts.md`): MaAI `bc_det` (Kyoto University; code MIT, model CC BY-NC-ND 4.0; Chinese, English and Japanese; listens to both channels; runs on a CPU), Easy Turn (3.45 GB, GPU-timed), X2-Turn (10.5 GB), TurnSense (text only), bargein-classifier (English only), Krisp VIVA (needs a key), LiveKit adaptive interruption (cloud only).
- Chosen: MaAI `bc_det`, in a separate Python environment.
- Rule fixed before any output was seen: feed the saved two-channel recordings frame by frame; a held stretch is a backchannel if the probability reaches 0.45 within 0.8 s of its onset (MaAI's event threshold on its Japanese data). A scored round would follow only if it got more of the 24 backchannel and interruption stretches right than the word-and-duration rule (22).
- Result: 17 and 18 of 24, so no scored round (report section 6.11). The clips are synthetic, so this says nothing about the model on real speech.

## D-V23 Listening only to the main speaker

- Problem: Silero marks 99.6% of four-talker babble frames as speech. Noise suppression (RNNoise, DeepFilterNet) removes non-speech noise, so it cannot help.
- Looked at (excerpts in `research/sources/speaker_vad_excerpts.md`): FireRedChat pVAD (Apache-2.0; Chinese and English; 3.9 MB plus an 89 MB SpeechBrain ECAPA speaker model), personal-vad (no Chinese listed), a speaker-verification gate (rules to write by hand).
- Chosen: FireRedChat pVAD. As in its LiveKit plugin, the speaker embedding of the first utterance is computed and set after that utterance (`eval/pvad_enroll.py`).
- Offline rule fixed before any output was seen: after enrolment, at most 10% of babble frames counted as speech; at least 90% of the user's later speech frames found on clean items; no more false onsets than Silero on clean items. All three held: 0.1% of babble frames, 92.8% of later user frames, and 0 false onsets on clean items for both (on babble, 0 against Silero's 18). So it was run (report section 6.14).

## D-V26 Keeping a turn whole when the user spoke first

The voice-activity onset is confirmed 0.2 s after speech starts. When the user went on just before the agent's first sound, the confirmation came after that sound, so the user's continuation was treated as an interruption and became a new turn. No framework checked handles this race. LiveKit passes the time speech started, not the time it was detected. The arm `vad-think-combo-merge` judges by the time speech started: if the user started before the reply's first sound, the reply counts as unheard and the turn stays whole, as under D-V11 (report section 6.17).

## D-V29 Do spoken confirmations match the tool record?

- Uses evidence-check's script `check_evidence.py` unchanged; `eval/confirm_consistency.py` only collects the confirmations and the records and passes them on.
- Rules fixed before counting:
  - a confirmation is what the agent said after the last successful data-changing tool call of a reply (what the user heard; the full text for the text-only control);
  - record A is that reply's data-changing calls, written as JSON;
  - spoken durations are first written in minutes, because the script does not convert hours; nothing else is changed;
  - consistent means every number stated is in the record; confirmations without a number are counted but not rated.
- Changed after seeing the first count, and reported as such: record A was too narrow, because confirmations also state facts looked up earlier. Record B, every tool call of the conversation so far, was added. The flags left under B were read and given categories written after reading.
- Results: report sections 6.20 and 6.21.
