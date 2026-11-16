# Voice agent evaluation v1: plan fixed before the run

Written 13 November 2026, 01:25 MYT, before any arm ran on the 42 test items. Four separate smoke items (`smoke_cases.json`, not part of the set, not scored) were used to debug the harness; what they changed is listed at the end. After the run, nothing in the items, answers, audio or scoring rules below changes. Any later fix to the scorer is listed under "Changes after the run" with its reason, and the stored traces are re-scored with no new model calls.

## What is tested

A cascaded voice agent that runs on one laptop CPU (Intel i9-14900HX), except for the language model:

1. **Listening**: Silero VAD (sherpa-onnx release), 32 ms frames, speech above 0.5, silence below 0.35. 0.2 s of continuous speech starts a user turn, or a barge-in while the agent is talking (Pipecat's `start_secs` default).
2. **Recognition**: SenseVoice-Small int8 (2024-07-17), inverse text normalization on.
3. **Model**: `claude-haiku-5-5`, effort `low`, streamed, with six tools served by a local MCP server (`get_weather`, `list_meetings`, `create_meeting`, `update_meeting`, `cancel_meeting`, `set_reminder`). All data is invented and fixed. Today is 2026-11-16.
4. **Speech**: MeloTTS zh_en, a different voice from the simulated users. The first chunk ends at the first punctuation mark (comma included) of at least 4 characters.

**Time model.** A virtual clock moves through the microphone signal frame by frame. When the agent decides the user has finished, each step (recognition, each model request, each tool call, each speech chunk) really runs, and its measured wall-clock time is added to the clock. Network time to the model API is included. Between steps the clock catches up frame by frame, so a user who goes on talking is heard at the right moment: before the agent speaks, the reply is cancelled and the turn continues; while it speaks, the agent stops (barge-in). Assumptions: echo cancellation is perfect (the microphone holds only the user and the noise); the agent stops at the frame where the barge-in is detected; the text after the first chunk is synthesized chunk by chunk by one worker.

## Test set (`cases.json`, 42 items)

| Category | Items | Languages (zh / en / mixed) | What happens |
|---|---|---|---|
| task | 16 | 10 / 3 / 3 | One request (two for T09, where the agent must ask for the time first). Weather, create, change, cancel, reminder; T10 asks for a city with no data |
| pause | 6 | 4 / 1 / 1 | The user stops mid-request for 1.2 to 2.0 s, then goes on |
| interrupt | 8 | 5 / 1 / 2 | The user cuts in 0.8 to 1.5 s after the agent starts its answer: a correction (I01, I02, I04, I06, I07), "stop" (I03, I08), or "don't cancel" (I05) |
| backchannel | 4 | 3 / 1 / 0 | The user says 嗯 / 嗯嗯 / 好的 / Okay 1.0 to 1.5 s into the answer; the agent should keep talking |
| noise | 8 | 5 / 1 / 2 | Copies of 8 task items: pink noise at 5 dB SNR (N01–N04) or 4-talker babble at 15 dB SNR (N05–N08) |

The simulated users are Kokoro v1.1 voices (Chinese ids 3, 18, 47, 61, 88; English ids 0, 2); every segment is trimmed and set to the same loudness. The interruption and backchannel moments are relative to the start of the agent's answer (its reply after the last tool call), so they land on the answer in every arm. Each item's answer is fixed in its `expect` field.

**Construction check** (`asr_check.py`, before any agent run). SenseVoice and Whisper-small transcribed the clean synthetic speech. Where both missed a key word with a different sound, the synthesis was taken to be wrong and the item was rewritten: the English contact "Anna" was heard as "Ho" / "Honour" and became "Emma"; English words missing from the synthesis lexicon (What's, Wong, minutes, a.m., p.m.) were rephrased. Misses that are homophones (李娜 as 李那, 西安 as 夕安, 周会 as 周回, 上午十点 as 上五十点) or a Chinese speaker's rendering of an English name (Tom as 汤, Emma as M) were kept: they are recognition problems the agent meets in real use, and the agent has a contact list.

## Arms

| Arm | Turn end | Thinking | Audio |
|---|---|---|---|
| `vad` | 0.55 s of silence (LiveKit's Silero default) | off | yes |
| `smart` | 0.2 s of silence, then Smart Turn v3.2 (CPU) must say "complete" (p > 0.5); otherwise wait, with a 3 s silence fallback (Pipecat defaults) | off | yes |
| `vad-think` | as `vad` | adaptive | yes |
| `oracle` | the scripted text, turn by turn; an interruption arrives as the next turn with the same "you were cut off after …" note, cut at the first chunk | off | no |

Same model, effort, system prompt and tools in every arm. `oracle` separates listening errors from reasoning errors. Each arm runs twice over all 42 items (`run1`, `run2`).

## What is measured (rules in `score.py`)

1. **Task pass**: final mock-server state equals the expected state (meetings compared on date, start, duration and attendees; reminders on date and time), and where stated: the right `get_weather` call (after the interruption for I02 and I06), the key fact actually heard by the user, no temperature for T10, no `create_meeting` before the user's second turn for T09, no change for no-change items.
2. **Interaction pass** (audio arms): interrupt items, the agent stops within the interruption (+1 s), and for I03 and I08 says no more than 3 s afterwards; backchannel items, the agent does not stop; pause items, no agent audio plays inside the pause. An interruption or backchannel that starts while the agent is silent is reported as "no overlap" and is not scored for that check.
3. **Strict pass** = task pass and interaction pass.
4. **Response latency** (Full-Duplex-Bench v1.5, Eq. 2): first agent audio after the user's turn ends minus the end of the user's speech. Also: answer audio (after the last tool call), and the parts (turn-end wait, recognition, model, tools, first speech chunk). Reported for task, pause and noise items.
5. **Stop latency** (Full-Duplex-Bench v1.5, Eq. 1): barge-in detection time minus the start of the user's interruption.
6. **Pause handling**: premature model request (a turn end detected inside the pause) and premature takeover (agent audio inside the pause, the turn-over idea of Full-Duplex-Bench v1).
7. **Recognition**: mixed error rate (each Chinese character and each English word is one token) on the exact user segments, by language and noise; key-word hits in the transcripts the agent actually received.
8. **Reasoning said aloud**: heard text that matches `用户|the user|识别结果|应为|2026-1x-xx|工具|tool`.
9. **Repeat runs**: per-item agreement of strict pass between run1 and run2; latency medians per run.
10. Cost (tokens), per arm.

**Negative-case attribution.** Every failed item-run gets one cause, by these rules in order, and then each trace is read: HARNESS (program error); COMMITTED (a change ran before the interruption could stop it); BARGE-IN (stopped on a backchannel, or did not stop); NOISE-VAD (babble kept the turn open until the 20 s cap); ENDPOINT (a pause item where the early turn end led to the failure); ASR (a key word missing from the transcripts while the oracle passed the item in at least one run); MODEL (the oracle fails the item too, or every key word was in the transcript); OTHER.

## Expectations, written down before the run

1. `vad`: a premature model request in all 6 pause items (every pause is longer than 0.55 s). Most are cancelled before the agent speaks, because a reply takes about 1.5 s or more; audible takeover in at most 2 of 6. Pause items mostly still pass the task, because the whole turn is heard again.
2. `smart`: fewer premature requests in pauses than `vad`, but a higher median response latency, because on the smoke items Smart Turn often judged complete Chinese questions as unfinished and waited for the 3 s fallback (its published CPU benchmark gives Chinese 85.8% accuracy, English 94.3%).
3. `vad-think`: higher first-audio latency than `vad` (no short preamble while tools run) and fewer cases of reasoning said aloud.
4. Backchannels: the agent stops on at least 3 of 4 in every audio arm (barge-in needs only 0.2 s of speech).
5. Babble at 15 dB: Silero marked 99.6% of pure-babble frames as speech (measured before the run), so N05–N08 will run to the 20 s cap and their first-audio latency will exceed 15 s. Pink noise at 5 dB: Silero marked 0% of pure-noise frames as speech; recognition errors rise a little and task pass stays close to the clean copies.
6. Stop latency around 0.2 to 0.35 s.
7. On clean task items the oracle passes at least 90%; most audio-arm task failures there trace to recognition of names, numbers and code-switched words.
8. I05 fails in every arm: the cancellation runs before the user can say "don't cancel", and there is no undo tool.

With two runs per arm, a difference of one or two items between arms is treated as noise. Expectations that do not hold are reported as not holding.

## Run

From the project root, with `VOICE_EVAL_ENV_FILE` naming a `.env` file that holds the API key, one arm at a time (no parallel runs, so timings are not disturbed):

```
python -I -X utf8 eval/run.py --arm <vad|smart|vad-think|oracle> --tag run1 --save-audio
python -I -X utf8 eval/run.py --arm <vad|smart|vad-think|oracle> --tag run2
python -I -X utf8 eval/score.py eval/results/run1 eval/results/run2
```

Expected cost about 0.3 USD in total (smoke items used about 4,600 input tokens per item; Haiku 5.5 is 0.10 / 0.50 USD per million input / output tokens). The budget for model calls is 2 USD.

## Harness changes made on the smoke items (before freezing)

- The VAD state is reset at the start of every item (it carried over and started a false turn at time 0).
- A reply after a barge-in was queued behind the cancelled speech; only audio that actually plays now delays the next reply.
- The rest of a reply is synthesized chunk by chunk instead of in one block.
- System prompt: the preamble rule is now in Chinese and limited to about ten characters, the reply language must follow the user's latest turn, and the agent must not explain how it read the transcript. Before this the agent spoke English preambles to Chinese users and answered an English user in Chinese.
- `vad-think` was added after the smoke items showed that, with thinking off, the agent sometimes says its reasoning aloud, and with thinking on it gives no early preamble.
- Interruptions and backchannels are timed from the start of the answer instead of the first audio.

## Frozen files (sha256, first 12 characters)

| File | sha256 |
|---|---|
| `eval/cases.json` | `5d1f2cebefd5` |
| `eval/audio_manifest.json` (hashes of every audio file) | `bc354b79de4a` |
| `agent/config.py` | `7c3e1b041589` |
| `agent/mock_tools_server.py` | `9eca36c0e114` |
| `agent/audio.py` | `a8f35899f0cb` |
| `agent/llm.py` | `d0a92cf8aa4f` |
| `agent/pipeline.py` | `1560efc97a37` |
| `eval/run.py` | `3d44b92a4a99` |
| `eval/score.py` | `ea31e3afadff` |
| `eval/build_audio.py` | `c9d125cf0725` |
| `eval/asr_check.py` | `e5477371107b` |
| `voice-models/silero_vad.onnx` | `9e2449e10874` |
| `voice-models/smart-turn-v3.2-cpu.onnx` | `2bb026316b14` |
| `voice-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx` | `c71f0ce00bec` |
| `voice-models/kokoro-multi-lang-v1_1/model.onnx` | `99db0bc8fd0c` |
| `voice-models/vits-melo-tts-zh_en/model.onnx` | `bf30582eb1b0` |

## Changes after the run

1. **Rate-limit retries (01:29 MYT, after 16 items of the first `vad` run).** Six of those items failed with HTTP 429: the account's limit of 500,000 input tokens per minute is shared with another evaluation that was running on the same key and the same machine. The SDK's own two retries were also hiding waiting time inside measured calls. The client now has SDK retries off; `llm.py` retries up to 10 times with backoff, times only the attempt that succeeds, and records the number of attempts in each trace. `run.py` records each item's start time. The partial run is kept in `results/aborted/run1-ratelimit/` and is not scored; all arms then started again from the first item. Items, answers, audio, prompts, arms and scoring rules did not change. New hashes: `agent/llm.py` `3e92c2aa2056`, `agent/pipeline.py` `482ea0940d01`, `eval/run.py` `290a99b11741`.
2. **Local component times from a calibration (01:50 MYT, after 19 items of the restarted `vad` run).** From about 01:30 the machine was fully loaded by other programs (CPU at 100%). Recognition and speech synthesis then took 3 to 10 times longer than on the smoke runs (for example a first speech chunk of 4.3 s), which would have measured the machine's load, not the pipeline, and would also have changed when the agent starts talking in pause and interruption items. The speech components still run for real (their transcripts and audio are used), but the time they add to the virtual clock now comes from `eval/local_timing.json`: a straight-line fit of the wall times recorded by the smoke runs (01:08–01:29 MYT, 4 threads): recognition 0.0014 s + 0.0564 s per second of input audio, synthesis 0.0353 s + 0.3936 s per second of output audio, Smart Turn 0.0249 s per check. Model calls, tool calls and network time are still measured live. Every trace also keeps the real wall time of each speech step (`wall`, `tts_wall`). A fastest-of-5 calibration taken at 01:43 under full load gave recognition 0.2075 s + 0.0781 s per second, synthesis 0.6522 s per second and Smart Turn 0.2984 s (`eval/local_timing_loaded.json`); the report gives the latency difference this would make. The stopped run is kept in `results/aborted/run1-cpu-load/` and is not scored; all arms started again from the first item. Items, answers, audio, prompts, arms and scoring rules did not change. New hashes: `eval/run.py` `c208ebcc565c`, `agent/pipeline.py` `7c074acb4849`, `eval/local_timing.json` `eb79e0e9527a`, `eval/calibrate.py` `9c5375e10e86`.
3. **A reply waiting to play is dropped when the user goes on (02:40 MYT, after both runs).** Reading the timelines showed a harness gap: when the model had finished but the first speech chunk had not started yet (a window of a few hundred milliseconds), a user who started talking in that window was not heard as a cancel, and the agent then talked over the user without being stopped. A real player drops a queued reply when the user starts speaking. A scan of every trace found this in 11 item-runs, all in five items: P02, P03, P05, P06 and I07. The harness now drops the queued reply (and, if nothing was said or done, hears the whole turn again, as for a reply cancelled while computing); `_heard_text` counts only audio played by the current time. Rule for the rerun, fixed before rerunning: every item where the gap occurred at least once (P02, P03, P05, P06, I07) runs again in all three audio arms and both runs; their earlier records are kept in `results/aborted/before-playback-fix/`. No other item-run had the gap, so the other records stand. Items, answers, prompts and scoring rules did not change. A new offline test covers the case (11 tests). New hash: `agent/pipeline.py` `c04c2028f768`.
4. **Edits for publication (2026-11-16; the first two before addendum A14, the third after it).** None changes what runs or how it is scored.
   - The run section above named the path of the key file, which lies in another local folder. It now says only that `VOICE_EVAL_ENV_FILE` names a `.env` file holding the key.
   - Four files had the local folder for models, Python environments and audio written into them: `agent/config.py`, `eval/mic_rebuild.py`, `eval/pvad_enroll.py` and `eval/bcdet_offline_check.py`. They now read it from `PORTFOLIO_LOCAL` (default: a folder named `portfolio-local` in the home directory). On this machine the paths resolve to the same folders as before, and the offline tests pass. Only these four files changed, so the hashes given for them in earlier addenda no longer match; no other hash changed.
   - After A14 ran, the usage note at the top of `eval/run.py` pointed to a file outside this repository for where the key file lives. It now points to the Reproduce section of `README.md`. Only that comment changed; the hash of `eval/run.py` is now `5156ccfd9bc3` (A14: `4a81df459412`).
5. **Wording edits for publication (2026-11-17).** Nothing that runs or is scored changed. The run logs above now say what happened to a run without saying why it stopped, the budget line and one comment of change 4 were reworded, and the self-check of `eval/score.py` now calls its traces "constructed" (two comments; new hash `8c05927151c1`, A14: `ea31e3afadff`).

## Addendum A1: barge-in by words (written 2026-11-13, before any run of this arm)

**Question.** In run1 and run2 every backchannel ("嗯", "嗯嗯", "好的", "Okay") stopped the agent: 24 of 24 across the three audio arms. Does a rule that waits for words stop those false stops, and what does it cost on real interruptions?

**Arm `vad-think-words`.** Same as `vad-think` in every way (model, prompt, adaptive thinking, 0.55 s endpoint, items, audio, calibrated timing), except for user speech that starts while the agent is talking (playing, or between two chunks of a reply that has started to play):
- The agent keeps talking. SenseVoice reads the held speech (from 0.3 s before its onset) at once, then every 0.16 s, one read at a time; each read counts only after its calibrated compute time.
- The agent stops as soon as a read holds at least 2 units that are not backchannel words. One Chinese character is one unit; one English word is one unit. The transcript is cut into phrases at punctuation; a phrase made only of listed words counts 0, any other phrase counts all its units (`agent/bargein.py`).
- When the user has been silent for 0.55 s (or after 20 s), a last read decides: 2 or more units start a turn as usual; fewer, and the speech is dropped and never reaches the model.
- Speech that starts while the agent is silent is handled exactly as in `vad-think`.

The rule follows Pipecat's `MinWordsUserTurnStartStrategy` and LiveKit's interruption `min_words`, with a backchannel list as proposed in livekit/agents issue 4450 (see `docs/DECISIONS.md` D-V15).

**Backchannel list (fixed; not changed after the run).**
Chinese: 嗯 恩 摁 唔 哦 噢 喔 啊 呃 额 诶 欸 哎 好 对 是 行 嗯哼 好的 好滴 好嘞 好吧 对的 是的 是啊 没错 明白 明白了 了解 知道 知道了 收到 懂了.
English: ok okay okey k mm mhm mmhmm mm-hmm hmm hm uh-huh uh huh um yeah yep yup yes right sure alright cool nice great "i see" "got it" gotcha.

**Run.** Two runs of all 42 items, written to `results/run1/vad-think-words.jsonl` and `results/run2/vad-think-words.jsonl`. The comparison is with `vad-think` run1 and run2, which are not run again. `score.py` and the attribution rules are unchanged.

**What is compared.** Backchannels where the agent kept talking (of 8); interruptions stopped (of 16), stop latency median and maximum, and `quiet_after`; stops during babble noise (of 8); strict pass per run and per category; first-audio latency on clean task items.

**Expectations, written down before the run.**
1. Backchannels: from 0 of 8 kept talking to at least 5 of 8. Some may still stop if the recognizer turns the backchannel into other words (in phase 1 one "嗯嗯" was read as Japanese); the list is not changed for that.
2. All 16 interruptions still stop; the median stop latency rises from 0.26 s (`vad-think`, both runs) to between 0.45 and 0.8 s.
3. Babble: about as many stops as before (8 of 8), because background speech gives words.
4. Strict pass per run: 2 to 4 more than `vad-think` (30 and 31), from the backchannel items; other categories within ±2, which is model randomness at this size.
5. A one-word command ("停", "No") would not stop the agent. No item tests this, so these runs cannot show it.

**Cost.** About 5 to 10 US cents for both runs.

**Files (sha256, first 12 characters) at the start of this arm.** `agent/bargein.py` `7b8870bceeba`, `agent/pipeline.py` `d4ae35b7b355` (adds the hold logic; the other arms' path is moved into `_user_onset` without a change in behaviour, and the 11 earlier offline tests still pass), `agent/config.py` `5a3f8b33286a`, `eval/run.py` `c208ebcc565c`, `eval/score.py` `ea31e3afadff`, `eval/cases.json` `5d1f2cebefd5`, `eval/audio_manifest.json` `bc354b79de4a`, `tests/test_offline.py` `db906e31979b` (14 tests pass).

**A1 run log.** Run1 14:00–14:05 and run2 14:05–14:10 MYT on 2026-11-13, 0 harness errors, 0 rate-limit retries; no file listed above was changed after the run. Results: `EVALUATION.md` section 6.7 and `results/words_vs_base.md`.

## Addendum A2: read held speech in the conversation's language (written 2026-11-13, before any run of this arm)

**Question.** In A1 the misses came from the recognizer's language guess: 嗯 was read as "Me you" / "Ma you", 嗯嗯 and babble as Japanese kana, two units each. The product only speaks Chinese and English. If the held speech is read with the recognizer fixed to the language of the user's last turn, do those backchannels stop counting as words?

**Arm `vad-think-words-lang`.** Same as `vad-think-words` in every way, except which recognizer reads the held speech: SenseVoice with `language` fixed to `zh` if the transcript of the user's last turn has a Chinese character, `en` if it has only Latin letters, and auto-detect if there is no such transcript. The same model file, the same calibrated time per read, the same word rule and list (A1). The transcript of a turn that is sent to the model is still read with auto-detect, as in every other arm.

Checked before the run, on one second of digital silence only (no test audio): auto-detect returns "그.", `zh` returns "没。", `en` returns "Yeah.". So the fixed recognizers also invent a word on silence; the run will show whether that matters.

**Run.** Two runs of all 42 items: `results/run1/vad-think-words-lang.jsonl`, `results/run2/vad-think-words-lang.jsonl`. Compared with `vad-think-words` and `vad-think` (not run again). Scoring and attribution unchanged.

**Expectations, written down before the run.**
1. Backchannels: at least 6 of 8 kept talking (B03 and B04 as in A1, and at least one of B01 and B02 in both runs).
2. All 16 interruptions still stop; median stop latency within 0.1 s of A1 (0.41 s).
3. Babble: still cut in at least 6 of 8 item-runs, because the babble is Chinese speech and will be read as Chinese characters.
4. Strict pass per run: at least 33 (A1) and at most 35.
5. English items read with `en`: B04 still kept talking; I06 stops within 1.0 s.

**Cost.** About 6 to 7 US cents for both runs.

**Files (sha256, first 12 characters) at the start of this arm.** `agent/audio.py` `f532ae9bf9f4` (the recognizer takes a `language` argument, default auto as before), `agent/pipeline.py` `1acc0a5719a0`, `agent/config.py` `48c517eb2b3b`, `eval/run.py` `f91503defcdd`, `agent/bargein.py` `7b8870bceeba`, `eval/score.py` `ea31e3afadff`, `tests/test_offline.py` `9dfca4037eff` (15 tests pass).

**A2 run log and one change after the run.** Run1 21:55–22:05 and run2 22:05–22:11 MYT on 2026-11-13. The API account was busy with other jobs: 12 and 18 rate-limit retries, which are not counted in any timing. One harness error: in run1, T09 crashed while synthesizing the agent's reply, because one speech chunk held only a symbol the agent's voice cannot say, and MeloTTS returned no audio with a sample rate of 0 (division by zero when resampling). The same could have happened in any arm; it had not happened before. Fix (22:12): `AgentTTS` returns an empty clip for such a chunk, and an offline test covers it (16 tests pass; `agent/audio.py` now `14b9a69e1f2e`, `tests/test_offline.py` `6df639aa7d94`). Following the rule used for change 3, the one affected item-run (T09, run1, this arm) was run again; the crashed record is kept in `results/aborted/run1-tts-empty/`. No other file changed. Results: `EVALUATION.md` section 6.8 and `results/lang_vs_base.md`.

## Addendum A3: a minimum duration as well as words (written 2026-11-13, before any run of this arm)

**Question.** A1 and A2 showed that the recognizer writes two syllables for 嗯 in any language, so the transcript alone cannot tell a hum from a short command. LiveKit checks two things before an interruption counts: the speech has lasted at least `min_duration` (default 0.5 s) and the transcript has at least `min_words`. Does adding LiveKit's default duration to the A1 word rule let the agent talk through 嗯, and what does it cost?

**Arm `vad-think-words-dur`.** Same as `vad-think-words` (A1: auto-detect, the same word rule and list), plus: the agent stops only when a read has at least 2 units **and** the held stretch has at least 0.5 s of voiced frames (voice activity, counted from the onset, gaps not counted). If the words come first, the stop waits for the duration; at the last read (0.55 s of silence), a stretch with less than 0.5 s of speech is dropped whatever it says. 0.5 s is LiveKit's documented default (`research/sources/interruption_settings_excerpts.md`), not a value fitted to these items.

**What is already known about these items.** From the earlier runs, the clips last 0.41 s (嗯, B01), 0.61 s (嗯嗯, B02), 0.70 s (好的, B03) and 0.56 s (Okay, B04), including the silence at their edges; the interruptions last 1.30–2.21 s. In A1, 嗯 was read as "Me you" / "Ma you" and 嗯嗯 as "ねな".

**Run.** Two runs of all 42 items: `results/run1/vad-think-words-dur.jsonl`, `results/run2/vad-think-words-dur.jsonl`. Compared with `vad-think-words` and `vad-think` (not run again). Scoring and attribution unchanged.

**Expectations, written down before the run.**
1. Backchannels: at least 6 of 8 kept talking (B03 and B04 as in A1, plus B01 in both runs because 嗯 is shorter than 0.5 s). B02 may still stop: its clip is 0.61 s.
2. All 16 interruptions still stop; the median stop latency rises to between 0.5 and 0.7 s, since no stop can come before 0.5 s of speech.
3. Babble: still cut in at least 6 of 8 item-runs (it is long and gives words).
4. Strict pass per run: 33 to 35.
5. A real command shorter than 0.5 s ("停") would be ignored. No item tests this.

**Cost.** About 6 to 7 US cents for both runs.

**Files (sha256, first 12 characters) at the start of this arm.** `agent/pipeline.py` `a887a0f5cc67` (adds the duration count; with no minimum set, A1 and A2 behave as before and their tests still pass), `agent/config.py` `4be2b9573093`, `agent/audio.py` `14b9a69e1f2e`, `agent/bargein.py` `7b8870bceeba`, `eval/run.py` `f91503defcdd`, `eval/score.py` `ea31e3afadff`, `tests/test_offline.py` `a0cac5f12f99` (18 tests pass).

**A3 status: NOT RUN.** Started 22:18 MYT on 2026-11-13; every one of the 84 item-runs failed at its first model call with HTTP 400 "credit balance is too low". No model call succeeded, nothing was spent, and no result exists for this arm. The failed records are kept in `results/aborted/run1-no-credit/` and `results/aborted/run2-no-credit/` and are not scored. The arm, the rule and the five expectations above stay as written; the run can start again once the API accepts the calls.

**Offline estimate while blocked (not the scored run).** `eval/dur_offline_check.py` runs Silero VAD alone over each backchannel and interruption clip (no model calls): `results/dur_offline_check.md`. The 0.41 s 嗯 clip gets 0.51–0.54 s of voiced time, because the voice-activity state stays on for a few frames after the sound ends; so the 0.5 s minimum would probably not spare it, and expectation 1 would probably not hold. Every interruption reaches 0.5 s of voiced time 0.53–0.68 s after it starts, which is where expectation 2 puts the median stop latency.

**A3 run log (2026-11-14).** After the account had credit again, the arm ran as written above: run1 03:46–03:50 and run2 03:50–03:56 MYT, 0 harness errors, 3 and 14 rate-limit retries (not counted in any timing). The files listed above had not changed (same hashes). The attempt of 2026-11-13 22:18 stays in `results/aborted/` and is not scored. The offline estimate above was wrong for 嗯: in the run the voice-activity detector, which had heard the whole conversation before, gave the clip 0.45 s and 0.48 s of voiced time, not 0.51–0.54 s. Results: `EVALUATION.md` section 6.9 and `results/dur_vs_base.md`.

## Addendum A4: pause first, then cancel or resume (written 2026-11-14 05:22 MYT, before any run of this arm)

**Question.** A1 to A3 let the agent talk through backchannels by waiting before it stops, so every real stop came later (median 0.26, 0.41, 0.58 s). LiveKit's default works differently. Speech heard while the agent talks pauses the agent's audio at once, without cancelling the reply. A final transcript ends the pause by interrupting the reply. If none arrives within `false_interruption_timeout` (default 2.0 s) after the user stops, the agent resumes from where it stopped (`resume_false_interruption`, default true). Excerpts and source lines are in `research/sources/interruption_settings_excerpts.md`. Can pausing keep vad-think's fast stop and still not lose the reply on a backchannel?

**Arm `vad-think-pause`.**
- When the agent is talking and 0.2 s of speech is heard (the vad-think onset), its audio pauses at once. The rest of the current chunk and every later chunk wait in a queue, and the reply keeps being generated. The pause is recorded as a barge-in (`by: "pause"`).
- The held speech is judged by the A3 rule, unchanged. It is read every 0.16 s with language auto-detect. A real interruption needs a read with at least 2 non-backchannel units and at least 0.5 s of voiced frames. The last read comes after 0.55 s of silence.
- If it is a real interruption, the queued audio never plays. The reply is cancelled and the user's turn starts at the onset, as in every other arm; the model is told what was heard before the pause.
- If it is not, the queued audio plays from where it stopped as soon as the verdict is in. The held speech is dropped and never reaches the model.
- New speech while paused is held and judged the same way.

**Where this differs from LiveKit's defaults (decided before the run).**
1. The pause starts at 0.2 s of speech, this project's onset as in vad-think, not at LiveKit's `min_duration` of 0.5 s. A fast stop is the point.
2. The verdict uses the A3 rule. LiveKit's documented rule resumes only when no user transcription arrives. In A1 to A3 every backchannel was transcribed as non-empty text (for example "好的。", "Okay." and "Meium."), so under that rule all eight would end the pause as interruptions.
3. The agent resumes as soon as the verdict is in (`pause_resume_after` 0.0 s), not 2.0 s after the user stops. LiveKit's timer waits for a final transcript from a streaming recognizer, which can arrive late. Here the verdict's read is known when the verdict is made. With 2.0 s, each resumed backchannel would leave about 2 s more silence. NOT RUN.

**Scoring.** Scoring is unchanged. A pause is a stop, because the agent goes silent while the user speaks. Under the frozen rule, a backchannel item whose reply paused does not count as "kept talking", even if the reply resumes. `eval/compare_words.py --pause` adds three measures for this arm, computed from the saved records:
- **Backchannels resumed:** backchannel item-runs where the paused reply later resumed.
- **Silence while paused:** seconds from the pause to the resume, for each resumed backchannel.
- **Wrong resumes:** interruption item-runs where the paused reply resumed.

**Run.** Two runs of all 42 items: `results/run1/vad-think-pause.jsonl` and `results/run2/vad-think-pause.jsonl`. They are compared with `vad-think-words-dur` and `vad-think`, which are not run again.

**Expectations, written down before the run.**
1. Interruptions: all 16 stop. The median stop latency is 0.24 to 0.30 s and the maximum is at most 0.35 s (vad-think: 0.26 and 0.31). Wrong resumes: 0 of 16.
2. Backchannels under the frozen rule: kept talking 0 of 8, because every backchannel pauses the agent (it stopped vad-think in all 8). Strict pass on backchannels: 0 of 8.
3. Backchannels resumed: 6 of 8 (B01, B03 and B04 in both runs). B02 is cancelled, as A3 stopped on it. B01 is fragile: A3 measured 0.45 and 0.48 s of voiced time against the 0.5 s line, so 4 of 8 would not be a surprise.
4. Silence while paused: 0.8 to 1.3 s for each resumed backchannel. A3 took 1.12 to 1.38 s from onset to verdict, and the pause starts about 0.2 s after the onset.
5. Babble: the agent pauses in at least 7 of 8 babble item-runs, and every babble pause ends with the reply cancelled. A3 read the babble as "家里。": 2 units, 0.77 s voiced.
6. Strict pass per run: 30 to 32 (vad-think: 30 and 31).
7. Clean tasks: median first audio 3.65 to 4.25 s (vad-think: 3.95 s). Nothing changes when the user does not talk over the agent.

**Cost.** About 6 to 7 US cents for both runs.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/pipeline.py` `5ce42a54fd5b`: adds the pause, the queue and the resume. The new code runs only when `pause` is set, and the saved trace fields of the earlier arms are unchanged.
- `agent/config.py` `af28bfd01f92`: adds the arm.
- Unchanged: `agent/audio.py` `14b9a69e1f2e`, `agent/bargein.py` `7b8870bceeba`, `eval/run.py` `f91503defcdd`, `eval/score.py` `ea31e3afadff`.
- `tests/test_offline.py` `d40a63e26dc5`: 20 tests pass. Two are new: a backchannel pauses the agent and the reply resumes with every character played once; an interruption pauses the agent and the reply is cancelled.

**A4 run log (2026-11-14).** The heading of this addendum first said 05:30. The file was saved at 05:22:06 MYT and the first item started at 05:22:44, so after the run the heading was corrected to 05:22; nothing else in A4 changed. Runs: run1 05:22–05:28 and run2 05:28–05:33 MYT, 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Model calls used the same standard interface as every earlier run. Results: `EVALUATION.md` section 6.10 and `results/pause_vs_base.md`.

## Addendum A5: a shorter first speech chunk (written 2026-11-14, before any run of this arm)

**Question.** Section 6.2 found the first speech chunk long, because a chunk must have at least 4 characters before a punctuation mark closes it, so "好的，" runs on to the next comma. In `vad-think` the first chunk of the first reply had a median of 15 characters and took a median of 0.85 s to synthesize, out of a first-audio median of 3.95 s. Does letting the first chunk be as short as "好的，" bring the first audio sooner, and what does it cost?

**Existing practice (`research/sources/tts_chunking_excerpts.md`).** None of the stacks checked starts this early by default:
- stream2sentence, the splitter behind RealtimeTTS, has a quick-yield option for the first fragment. It is off by default, needs 10 characters, and its fragment marks include the ASCII comma but not the Chinese comma.
- LiveKit's basic sentence tokenizer waits for 20 characters.
- Pipecat's default text aggregator waits for the end of a sentence.

This project's rule (any comma, 4 characters) is already earlier than all three. The new arm takes stream2sentence's idea, a short first fragment, further for Chinese. The values below were chosen after reading the earlier replies, where 好的， and colons open many first chunks. The run is new model output.

**Arm `vad-think-short`.** Same as `vad-think`, except the first chunk of each reply step:
- closes at the first punctuation mark once it has at least 2 characters (so "好的，" and "Sure," qualify);
- also closes at a full-width colon "：", or at an ASCII colon followed by a space ("10:00" does not close it).

Later chunks keep the 4-character rule. The speech model, its timing calibration and everything else are unchanged.

**Offline estimate (not a run).** The new rule was applied to the text of `vad-think`'s first replies to the 16 clean task items in both runs, and synthesis time was estimated from the calibration. 8 of the 32 first chunks would have been shorter, for example 「好的，」, 「抱歉，」 and 「已设置提醒：」, saving a median 0.93 s of synthesis each. The median first-chunk synthesis time would fall from 0.85 s to about 0.58 s. A short first chunk can leave a silence before the second chunk, which is synthesized once the reply's text is complete. In `vad-think`, 1 of 29 first steps with a second chunk had such a gap over 0.3 s (longest 0.49 s).

**New measures (from the saved records, `eval/compare_short.py`).**
- First-chunk length.
- Gap: the silence between the first and second chunk of the same reply step.
Scoring is otherwise unchanged.

**Expectations, written down before the run.** All on clean task items, first turn, run1 + run2.
1. First-chunk synthesis median: 0.45 to 0.70 s (`vad-think`: 0.85 s).
2. First chunks of 4 characters or fewer: 4 to 12 of 32.
3. First-audio median: 3.40 to 3.95 s (`vad-think`: 3.95 s). This may not stand out from run-to-run variation, which was 0.6 s between the two `vad-think` runs.
4. Gaps over 0.3 s after the first chunk: 2 to 8 steps (`vad-think`: 1 of 29).
5. Nothing else changes. All 16 interruptions stop, with a median stop latency of 0.24 to 0.30 s. Backchannels: kept talking 0 of 8. Strict pass per run: 29 to 33 (`vad-think`: 30 and 31).

**Run.** Two runs of all 42 items: `results/run1/vad-think-short.jsonl` and `results/run2/vad-think-short.jsonl`, compared with `vad-think`, which is not run again. Model calls use the standard interface, as in every earlier arm: these are the agent's own live replies.

**Cost.** About 6 to 7 US cents for both runs.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/llm.py` `66bf20d531e4`: the first-chunk rule takes a minimum and a colon option; the defaults keep the old rule.
- `agent/config.py` `78bee19d5f08`: adds the arm.
- `eval/run.py` `db80a8ffd3af`: passes the arm's first-chunk settings to the model client.
- Unchanged: `agent/pipeline.py` `5ce42a54fd5b`, `agent/audio.py` `14b9a69e1f2e`, `eval/score.py` `ea31e3afadff`.
- `tests/test_offline.py` `da92f30f12fd`: 21 tests pass. The new one checks the short first chunk, the colon rule and that the default rule is unchanged.

**A5 run log (2026-11-14).** The addendum was saved at 16:30:46 MYT (file time); the first item started at 16:31:00. Runs: run1 16:31–16:35 and run2 16:35–16:39 MYT, 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.12 and `results/short_vs_base.md`.

## Addendum A6: confirm before cancelling (written 2026-11-14, before any run of this arm)

**Question.** In every arm so far, "帮我取消明天的周会" followed by "等一下，先别取消" (I05) failed the same way: the meeting was already cancelled before the agent said a word, so the user's "wait" came too late (COMMITTED, both runs of every arm). Does asking for a spoken confirmation before a cancellation fix this, and what does the extra question cost?

**Existing practice (`research/sources/confirmation_excerpts.md`).**
- Agent frameworks mark individual tools as needing approval: `needs_approval` in the OpenAI Agents SDK, `interrupt_on` in LangChain's human-in-the-loop middleware. The run pauses before such a call until a person decides.
- Voice design guidance (Nuance Mix) says to confirm explicitly when "the application is about to perform an action it cannot undo".

In a voice agent the approval has to be spoken, so this arm turns the framework pattern into a question and an answer.

**Arm `vad-think-confirm`.** Same as `vad-think`, except for `cancel_meeting`, the only tool here that deletes data.
- **The first call does not run.** The model gets an error result instead: the call was not run, a deletion needs the user's confirmation, so restate the meeting, ask, and wait.
- **The next turn may run it.** The call is allowed in the next response, and only if the user heard at least part of the question. That response follows the user's reply, so the model judges from the reply whether the user agreed. The gate closes again after that response.
- **Nothing else changes.** Other tools, the system prompt and everything else are unchanged.

**The 42 items.** T04 (cancel a meeting; the scripted user never answers a question) and I05 (cancel, then "wait") are the only cancel requests. The set was written for an agent that does not ask, so T04 is expected to fail here: the meeting will stay. That is a property of the script, and it is the reason for the extra items below.

**Four extra items, written now (`eval/confirm_cases.json`; audio built with the same voices and checked by reading it back with the project's recognizer).** Each item is a cancel request followed by the user's answer, which plays 0.6 s after the agent stops talking:

| Item | Request | User's answer | Expected end state |
|---|---|---|---|
| C01 | 把明天的设计评审取消掉。 | 对，取消吧。 | M002 removed |
| C02 | Please cancel the design review for tomorrow. | Yes, cancel it. | M002 removed |
| C03 | 帮我取消明天的周会。 | 算了，先不取消了。 | nothing changed |
| C04 | 把明天下午的 design review 取消掉。 | 对，取消。 | M002 removed |

Both arms run these items twice (tags `confirm1` and `confirm2`), scored with `score.py --cases eval/confirm_cases.json`. For an agent that does not ask, the answer simply comes after it has finished. The C02 request first read "Please cancel tomorrow's design review."; the speech model skipped "tomorrow's", a word missing from its dictionary, so the text was changed before any run.

**Measures (`eval/compare_confirm.py`).** Scoring of the 42 items is unchanged. For the extra items, two measures are added:
- **Asked first:** no cancel ran before the user's answer began.
- **Cancel time:** seconds from the end of the request to the cancel that ran.

**Expectations, written down before the run.**
1. I05 passes in both runs (`vad-think`: COMMITTED in both).
2. T04 fails in both runs, because the scripted user never confirms (`vad-think`: passed in both).
3. Calls are held only in T04 and I05 among the 42 items.
4. Strict pass on the 42 items: 29 to 33 per run (`vad-think`: 30 and 31).
5. Extra items: `vad-think-confirm` passes at least 7 of 8 item-runs and asks first in 8 of 8. `vad-think` fails C03 in both runs, because it cancels before the user declines, and asks first in at most 1 of 8.
6. Confirming costs time: on the items where a cancel runs, the median cancel time is at least 2.0 s later than with `vad-think`.
7. Nothing else changes: all 16 interruptions stop, median stop latency 0.24 to 0.30 s, and no backchannel is talked through.

**Run.** `vad-think-confirm` on all 42 items twice (`results/run1`, `results/run2`), plus both arms on the four extra items twice. All model calls use the standard interface: they are the agent's own live replies.

**Cost.** About 8 US cents in all.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/pipeline.py` `4215313614c5`: holds a gated call and opens the gate for the next turn. Nothing changes when `confirm_tools` is not set.
- `agent/config.py` `68b6f23bbb3e`: adds the arm.
- `eval/confirm_cases.json` `b1271613c440` and `eval/confirm_cases.audio.json` `4366d9610a08`: the four items and their audio fingerprints.
- Unchanged: `agent/llm.py` `66bf20d531e4`, `agent/audio.py` `14b9a69e1f2e`, `eval/run.py` `db80a8ffd3af`, `eval/score.py` `ea31e3afadff`.
- `tests/test_offline.py` `b91e8ae50235`: 23 tests pass. The two new ones check that a cancel waits for the user's answer under this arm and runs at once under `vad-think`.

**A6 run log (2026-11-14).** The addendum was saved at 16:48:48 MYT (file time, printed when the run was started); the first item started at 16:49:14. Runs:
- `vad-think-confirm` on the 42 items: run1 16:49–16:53, run2 16:53–16:57.
- The four extra items: `vad-think` and `vad-think-confirm`, `confirm1` 16:57–16:59 and `confirm2` 16:58–17:00 MYT.

There were 0 harness errors and 0 rate-limit retries. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.13 and `results/confirm_vs_base.md`.

## Addendum A7: listen only to the first speaker (written 2026-11-14, before any run of this arm)

**Question.** Background talkers (four-voice babble, 15 dB below the user) defeat voice activity here. Silero marked 99.6% of pure babble frames as speech, so in all 8 babble item-runs of `vad-think` the first turn waited for the 20 s cap (first audio a median 20.4 s after the user stopped), and in all 8 the babble later cut the agent off mid-reply. Noise suppression removes non-speech noise, but the trouble here is speech. Does a voice-activity model that follows one speaker fix this, and what does it cost on clean speech?

**Existing practice (`research/sources/speaker_vad_excerpts.md`).** FireRedChat's personalized VAD (pVAD; FireRedTeam, Apache-2.0, zh and en) is built for this: its paper says it "suppresses background noise and non-target speakers, thereby reducing false interruptions". Its LiveKit plugin runs a 3.9 MB ONNX model on 10 ms windows with a 192-value speaker embedding (SpeechBrain ECAPA), zeros until it is updated "after the first utterance". The plugin's own defaults are not used; the pipeline's existing thresholds are kept so that only the model changes.

**Arm `vad-think-pvad`.** Same as `vad-think`, except that pVAD replaces Silero for every listening decision: turn start, turn end and barge-in, with the same thresholds (on at 0.5, off below 0.35, 0.2 s to start, 0.55 s of silence to end).
- The embedding starts as zeros. When the first turn ends, the embedding of that first utterance is set, 0.268 s later on the virtual clock (the median time it took to compute in `eval/pvad_enroll.py`).
- The embedding is computed beforehand per item from at most the first 5 s of the first utterance as the microphone hears it, noise included, as the plugin does (`eval/pvad_enroll.json`). The first utterance starts at the same fixed time in every run, so this does not depend on a run.
- pVAD takes 0.09 s of CPU per second of audio on this machine (Silero: 0.004 s), so it can run live.

**Offline check before this addendum (`results/pvad_offline_check.md`, no model calls).** Its rule was written before the output was seen (DECISIONS D-V23). It rebuilt the microphones of the `vad-think` runs and found:
- after the embedding: 0.1% of babble-only frames marked as speech (Silero 97.8%), no false onsets in babble (Silero 18), and 92.8% of the user's later frames caught on clean items (Silero 96.7%);
- with the zero embedding: 93.1% of first-utterance frames caught on clean items, and 11.4% of babble frames marked as speech (Silero 87.8%).
All three pass rules were met, and the zero-embedding result means pVAD is used from the start.

**Expectations, written down before the run.**
1. Babble: first turns forced at the 20 s cap in at most 2 of 8 item-runs (`vad-think`: 8 of 8).
2. Babble: the agent stopped mid-reply in at most 2 of 8 item-runs (`vad-think`: 8 of 8).
3. Babble: first-audio median under 6 s (`vad-think`: 20.4 s).
4. Clean tasks: first-audio median 3.65 to 4.25 s (`vad-think`: 3.95 s).
5. Interruptions: all 16 stop, median stop latency 0.20 to 0.40 s (`vad-think`: 0.26 s).
6. Backchannels: kept talking in 0 to 2 of 8. The user's own 嗯 is the target speaker's voice.
7. Pauses: no speech inside the pause in at least 10 of 12 (`vad-think`: 12 of 12). pVAD caught fewer of the user's frames, so a turn could end early.
8. Strict pass per run: 29 to 34 (`vad-think`: 30 and 31).

**Run.** Two runs of all 42 items: `results/run1/vad-think-pvad.jsonl` and `results/run2/vad-think-pvad.jsonl`, compared with `vad-think`, which is not run again (`eval/compare_pvad.py`). Model calls use the standard interface: they are the agent's live replies.

**Cost.** About 6 to 7 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/pipeline.py` `5cb79e500a10`: sets the embedding after the first turn end; nothing changes unless `pvad` is set.
- `agent/audio.py` `653b1e17b2e1`: adds `PersonalVAD`.
- `agent/config.py` `450b5d6b7ee7`: adds the arm.
- `eval/run.py` `d860272cad4d`: loads pVAD and the embeddings for this arm.
- `eval/pvad_enroll.json` `067798904a9a`: the embeddings.
- `pvad.onnx` `2114fd3c3fa8`: Hugging Face FireRedTeam/FireRedChat-pvad, snapshot 74561b17a50f.
- Unchanged: `agent/llm.py` `66bf20d531e4`, `eval/score.py` `ea31e3afadff`.
- `tests/test_offline.py` `522e0ff78def`: 25 tests pass. The two new ones check that the embedding is set once, its compute time after the first turn end, and that the wrapper streams 10 ms windows.

**A7 run log (2026-11-14).** The addendum was saved at 17:20:53 MYT (file time, printed when the run was started); the first item started at 17:21:07. Runs: run1 17:21–17:28 and run2 17:28–17:35 MYT, 0 harness errors, 0 rate-limit retries. The speaker embedding was set in all 84 item-runs. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.14 and `results/pvad_vs_base.md`.

## Addendum A8: the four changes that helped, together (written 2026-11-14, before any run of this arm)

**Question.** Each change was tested alone against `vad-think`. Do they still work when combined, and does any of them get in the way of another?

**Arm `vad-think-combo`.** `vad-think` plus four changes, each exactly as in its own addendum:
- FireRedChat pVAD for all listening (A7), with the embedding set 0.268 s after the first turn ends;
- a first speech chunk of 2 characters or more, also closed by a colon (A5);
- `cancel_meeting` held until the turn after the user heard the question (A6);
- pause at once, then cancel or resume with the A3 verdict: 2 non-backchannel units and 0.5 s of voiced frames (A4).

**Left out, and why (decided before the run).**
- The waiting rules of A1 to A3 were left out. They delay every real stop (0.41 to 0.58 s), while A4 keeps the 0.26 s stop and uses the same verdict.
- A2's fixed recognizer language was left out: it did not help.

**Runs.** The 42 items twice (`results/run1`, `results/run2`) and the four confirmation items of A6 twice (`results/confirm1`, `results/confirm2`), with the same speaker embeddings for those four items. The comparison is against `vad-think` and each single-change arm, none of which is run again (`eval/compare_combo.py`). All model calls use the standard interface, because they are the agent's live replies.

**What changed in the files.**
- `eval/pvad_enroll.json` now also holds the four confirmation items' embeddings, added by `pvad_enroll.py --add confirm_cases`. The 42 earlier embeddings and the 0.268 s timing are unchanged; this was checked value by value.
- `eval/mic_rebuild.py` can now read either cases file. The offline check of A7 was regenerated with it, with the same numbers.

**Expectations, written down before the run.**
1. Babble: first turn forced at the 20 s cap in at most 2 of 8; agent stopped mid-reply in at most 2 of 8; first-audio median under 6 s. As in A7.
2. I05 passes in both runs and T04 fails in both runs. As in A6.
3. All 16 interruptions stop (pause), median stop latency 0.20 to 0.40 s, and none is resumed by mistake.
4. Backchannels: the reply survives (kept talking or resumed) in at least 6 of 8.
5. Clean tasks: first-chunk synthesis median 0.45 to 0.70 s; first-audio median 3.40 to 4.30 s.
6. Confirmation items: at least 7 of 8 passed, and asked first in 8 of 8.
7. Pauses: strict pass in at least 10 of 12.
8. Strict pass on the 42 items: 30 to 35 per run (`vad-think`: 30 and 31).

**Cost.** About 7 to 8 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/config.py` `503d12d96391`: adds the arm.
- `eval/pvad_enroll.json` `154cd5fe6c60`: 46 items.
- Unchanged since A7: `agent/pipeline.py` `5cb79e500a10`, `agent/audio.py` `653b1e17b2e1`, `agent/llm.py` `66bf20d531e4`, `eval/run.py` `d860272cad4d`, `eval/score.py` `ea31e3afadff`.
- `eval/confirm_cases.json` `b1271613c440` (as in A6).
- `tests/test_offline.py` `52eb0189eae4`: 26 tests pass. The new one runs all four changes together: the embedding is set once, a short sound over the question pauses and resumes the agent, and the cancel waits for the answer.

**A8 run log (2026-11-14).** The addendum was saved at 20:19:29 MYT (file time, printed when the run was started); the first item started at 20:19:38. Runs: run1 20:19–20:24, run2 20:23–20:28, confirm1 20:28–20:29 and confirm2 20:29–20:30 MYT, 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.15 and `results/combo_vs_base.md`.

## Addendum A9: a brief confirmation question (written 2026-11-14, before any run of this arm)

**Question.** In A6 and A8 the confirmation restated date, time and every attendee. On the four confirmation items the question lasted a median 5.03 s (A8), and a cancel came a median 14.18 s after the request ended. Does asking briefly save that time without losing the confirmation?

**Existing practice (`research/sources/confirmation_excerpts.md`).** Bixby's design guide says the dialog at a confirmation moment "should be a brief and direct question that prompts the user to act".

**Arm `vad-think-combo-brief`.** Same as `vad-think-combo` (A8), except for the text the model receives when its first `cancel_meeting` call is held. It now asks for one very short question that names only the meeting's date, time and title, without the attendees. The text includes an example, 「取消明天下午两点的设计评审吗？」. The rule for when the call may run is unchanged.

**Runs.** The 42 items twice (`results/run1`, `results/run2`) and the four confirmation items twice (`results/confirm1`, `results/confirm2`). The comparison is against `vad-think-combo`, which is not run again (`eval/compare_followups.py`, which also reports the question's length: the seconds of agent speech in the response that held the call). All model calls use the standard interface, because they are the agent's live replies.

**Expectations, written down before the run.**
1. Confirmation items: question length median at most 3.0 s (A8: 5.03 s).
2. Confirmation items: cancel time median 9.5 to 12.0 s (A8: 14.18 s).
3. Confirmation items: at least 7 of 8 right and 8 of 8 asked first.
4. I05 passes in both runs, and T04 fails in both runs.
5. Everything else stays as in A8:
   - babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off;
   - interruptions: 16 of 16 stopped, with a median of 0.20 to 0.40 s;
   - backchannels: the reply survives at least 6 of 8;
   - strict pass: 29 to 34 per run.

**Cost.** About 7 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/pipeline.py` `0934fa344ee5`: adds the brief wording. Nothing changes unless `confirm_brief` is set.
- `agent/config.py` `62cd8e30f32d`: adds the arm.
- Unchanged since A8: `agent/audio.py` `653b1e17b2e1`, `agent/llm.py` `66bf20d531e4`, `eval/run.py` `d860272cad4d`, `eval/score.py` `ea31e3afadff` and `eval/pvad_enroll.json` `154cd5fe6c60`.
- `tests/test_offline.py` `2d13b358b34b`: 27 tests pass. The new one checks that this arm sends the brief wording and that `vad-think-combo` keeps the original.

**A9 run log (2026-11-14).** The addendum was saved at 20:41:16 MYT (file time, printed when the run was started); run1 ran 20:41–20:46 MYT. Run2 started at 20:46 and stopped after 10 items (T01 to T10, last one at 20:47); nothing in the files changed (same hashes). It was resumed at 22:57 with the same files: run.py skips the items already in the record, and the remaining 32 items ran 22:57–23:04. The interrupted run had not written its token usage, so the usage of the first 10 items (50,332 input and 2,015 output tokens, 24 calls) was added back from the per-call counts in their traces; the same sum over run1's traces matches run1's usage file exactly. The confirmation items ran 23:04–23:06. 0 harness errors, 0 rate-limit retries. Results: `EVALUATION.md` section 6.16 and `results/followups_vs_combo.md`.

## Addendum A10: keep a turn whole when the user spoke first (written 2026-11-14, before any run of this arm)

**Question.** In A8 (and once in A9), a pause item split into two turns. The user went on speaking just before the agent's short first chunk began. The voice-activity onset is only confirmed 0.2 s after speech starts, so the reply had already begun when the onset counted. The reply was then treated as heard and interrupted, and the continuation became a new turn. In every arm without the short chunk and pVAD, the same reply was dropped before it played, and the two halves stayed one turn (the rule of D-V11). Does judging by when the user started, not by when the start was confirmed, keep those turns whole?

**Existing practice.**
- No framework checked handles this exact race, and a web search found none (D-V26).
- The pipeline's own rule (D-V11) already drops a reply that has not started playing when the user goes on, and keeps the turn whole.
- LiveKit's turn handling passes the time speech started, not the time it was detected, to its start-of-speech handler (`on_start_of_speech(ev, speech_start_time)`, `research/sources/interruption_settings_excerpts.md` source file).

**Arm `vad-think-combo-merge`.** Same as `vad-think-combo` (A8), plus one rule. When speech is confirmed as an interruption while a reply plays (by barge-in, or by the verdict after a pause), the arm checks the speech's voice-activity onset. If that onset is earlier than the reply's first sound, the user spoke first, and:
- the reply is dropped as unheard, so the model is not told it was cut off;
- the turn continues from where it started, so the two halves are heard as one, as under D-V11;
- a held cancel's question counts as unheard too.

Speech that starts after the reply's first sound is handled exactly as before.

**Runs.** The 42 items twice (`results/run1`, `results/run2`), compared with `vad-think-combo`, which is not run again (`eval/compare_followups.py`). The confirmation items are not run for this arm: the rule cannot change them unless the user talks over a question before it starts, which those scripts do not do. All model calls use the standard interface, because they are the agent's live replies.

**Expectations, written down before the run.**
1. Pause items: the continuation becomes its own turn in at most 1 of 12 item-runs (A8: 4 of 12).
2. The rule fires only on pause items (where the user goes on after a pause), never on interruption or backchannel items.
3. Pause items: strict pass in at least 11 of 12.
4. Everything else as in A8:
   - babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off;
   - interruptions: 16 of 16 stopped, median 0.20 to 0.40 s;
   - backchannels: at least 6 of 8 replies survive;
   - I05 passes and T04 fails in both runs;
   - strict pass: 30 to 35 per run.

**Cost.** About 6 to 7 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/pipeline.py` `dcccf0c70eae`: adds the rule; nothing changes unless `spoke_first` is set.
- `agent/config.py` `d606a9c35964`: adds the arm (the A9 arm is unchanged).
- Unchanged since A8: `agent/audio.py` `653b1e17b2e1`, `agent/llm.py` `66bf20d531e4`, `eval/run.py` `d860272cad4d`, `eval/score.py` `ea31e3afadff`, `eval/pvad_enroll.json` `154cd5fe6c60`.
- `tests/test_offline.py` `5899cfb4fd50`: 28 tests pass. The new one rebuilds the P01 race, with the reply's text finishing either before or after the verdict, and checks that this arm keeps one turn while `vad-think-combo` splits it.

**A10 run log (2026-11-14).** The addendum was saved at 23:08:56 MYT (file time); the first item started at 23:09:25. Runs: run1 23:09–23:17 and run2 23:17–23:28 MYT, 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.17 and `results/followups_vs_combo.md`.

## Addendum A11: synthesize each chunk as its text streams in (written 2026-11-14, before any run of this arm)

**Question.** Since round 1 the simulation has synthesized a reply's later chunks only once the whole reply text was complete: only the first chunk was cut from the stream. After a short opening such as 「好的，」 the agent could therefore wait for the rest of the text (6.12: up to 0.77 s of silence). Pipecat and LiveKit hand their speech engines one sentence at a time as the model streams (`research/sources/tts_chunking_excerpts.md`). Does doing the same here remove those silences?

**Arm `vad-think-combo-stream`.** Same as `vad-think-combo` (A8), except for when later chunks are synthesized:
- the model client records when each chunk's text is complete in the stream, using the same rules that cut the final text into chunks;
- each later chunk is synthesized as soon as its own text is in, by the same single speech worker, one chunk after another.

If the recorded chunk ends do not match the chunks of the final text, that step falls back to the old rule and is counted. The first chunk, the timings of the speech engine and everything else are unchanged.

**What `vad-think-combo` showed (clean task items, first spoken reply step, `results/followups_vs_combo.md`).** Gaps over 0.3 s after the first chunk: 3 of 30, the longest 0.49 s. Total silence inside that step: median 0.0 s, p90 0.27 s. The step ended a median 9.28 s after the request ended.

**Expectations, written down before the run.**
1. Gaps over 0.3 s after the first chunk: at most 1 (A8: 3 of 30).
2. Silence inside the first spoken reply step: p90 at most 0.15 s (A8: 0.27 s).
3. End of that step after the request: median 8.8 to 9.6 s. This changes little, because synthesis is faster than playback and the text usually streams in long before it is needed.
4. Steps that fall back to the old rule: at most 5% of spoken reply steps.
5. Clean tasks: first-audio median 3.5 to 4.2 s (A8: 3.83 s).
6. Everything else as in A8:
   - babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off;
   - interruptions: 16 of 16 stopped, median 0.20 to 0.40 s;
   - backchannels: at least 6 of 8 replies survive;
   - I05 passes and T04 fails in both runs;
   - strict pass: 30 to 35 per run.

**Runs.** The 42 items twice, compared with `vad-think-combo` (`eval/compare_followups.py`). All model calls use the standard interface, because they are the agent's live replies.

**Cost.** About 6 to 7 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/llm.py` `c7a2717d086d`: records chunk ends while streaming. It records them for every arm, but only this arm uses them.
- `agent/pipeline.py` `226b02718437`: uses the chunk ends when `stream_tts` is set. Otherwise the timing is the same as before.
- `agent/config.py` `fcd34e80432d`: adds the arm.
- Unchanged: `agent/audio.py` `653b1e17b2e1`, `eval/run.py` `d860272cad4d`, `eval/score.py` `ea31e3afadff`, `eval/pvad_enroll.json` `154cd5fe6c60`.
- `tests/test_offline.py` `1dc4f6cbfd23`: 30 tests pass. The two new ones check two things: chunk ends found while streaming equal the chunks spoken from the final text, and a later chunk starts as soon as its text has arrived instead of waiting for the whole reply.

**A11 run log (2026-11-14).** The addendum was saved at 23:33:08 MYT (file time); the first item started at 23:33:30. Runs: run1 23:33–23:40 and run2 23:40–23:46 MYT, 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Results: `EVALUATION.md` section 6.18 and `results/followups_vs_combo.md`.

## Addendum A12: disfluent requests and new voices (written 2026-11-15, before any run of these items)

**Question.** The 42 items are fluent and use five Chinese and two English voices (section 9). How do the agent and the combined arm cope with requests that repeat, correct or restart themselves, and with voices they have not heard?

**Existing practice (`research/sources/disfluency_excerpts.md`).**
- LARD (LREC 2022) generates disfluencies of three types from fluent text: repetitions, replacements and restarts. Its tool works on English only.
- HumDial, the ICASSP 2026 challenge with real Chinese and English full-duplex recordings, sends its data only to teams that register with an institutional or corporate email. Whether to register is the user's decision, so it is not used here (NOT RUN).

**Items (`eval/disfluent_cases.json`, written now).** There are 14 items, each a single request with an answer fixed when the item was written:
- **D01–D10**: ten disfluent requests using LARD's three types plus fillers (呃, 嗯, um, uh):
  - three repetitions: D01 「帮我查查查一下…」, D05 「后天，后天…」;
  - three replacements: D03 「约张伟，不对，约李娜…」, D06 「八点，呃，八点半」, D08 "at two, no, at three";
  - two restarts: D04 「明天的那个……算了，把…」, D09 「那个，就是明天的 weekly meeting…」;
  - three with fillers: D02, D07, D10.
- **V01–V04**: four clean requests copied word for word from T01, T02, T05 and T11.
- **Voices**: all 14 use voices the 42 items do not use, Kokoro speakers 10, 26, 39, 66, 79 and 99 for Chinese and 1 for English.

**Construction check (as for the 42 items).** Each request was read back by SenseVoice and Whisper-small. An item was changed when both recognizers misheard the same keyword as a different sound. That happened twice before any run:
- D04's 「设计评审」 was heard as 「设计庭审」 and 「设计停神」, so D04 now names the meeting by its time (「明天下午两点的会」).
- V03's 「成都」 was heard as 「成读」 by both, so V03 is now a copy of T05 instead of T08.

D08 first said "for thirty minutes", but the speech engine's dictionary lacks "minutes" and skipped it, so it now says "for half an hour". Other mishearings (for example 「城都」 for 成都, or 「weekly密人」 heard by SenseVoice only) were kept, as the rule says, because they test recognition.

**A limit of these items.** Kokoro renders 「……」 as at most 0.26 s of silence (Silero, measured on the built audio). These items therefore test disfluent wording, not long hesitations. Long pauses inside a request are what the six pause items already test.

**Arms and runs.** `vad-think`, `vad-think-combo` (A8) and the text-only control, two runs each (`results/dis1`, `results/dis2`), scored with `score.py --cases eval/disfluent_cases.json`. Measures (`eval/compare_disfluent.py`):
- pass counts for D and V items;
- turn ends detected inside a request;
- what the recognizer heard;
- V items against their source items in the earlier runs.

All model calls use the standard interface, because they are the agent's live replies and the control's paired turns.

**Expectations, written down before the run.**
1. The text-only control passes at least 12 of 14 per run: the model can follow disfluent text.
2. `vad-think` passes at least 6 of the 10 D items per run.
3. `vad-think` passes at least 7 of the 8 V item-runs (their source items passed 8 of 8).
4. Turn ends inside a request: at most 1 of 28 item-runs per audio arm, since no pause reaches 0.55 s.
5. `vad-think-combo` is within 2 items of `vad-think` per run on the 14 items: on clean audio without overlap its changes have little to act on.

**Cost.** About 5 to 7 US cents for the three arms.

**Files (sha256, first 12 characters).** `eval/disfluent_cases.json` `5bfe48e22097`, `eval/disfluent_cases.audio.json` `87c334cacfab`, `eval/pvad_enroll.json` `3bfdcb260170` (14 items added; the 46 earlier embeddings and the 0.268 s timing unchanged). Code unchanged since A11: `agent/pipeline.py` `226b02718437`, `agent/config.py` `fcd34e80432d`, `agent/audio.py` `653b1e17b2e1`, `agent/llm.py` `c7a2717d086d`, `eval/run.py` `d860272cad4d`, `eval/score.py` `ea31e3afadff`; `tests/test_offline.py` `1dc4f6cbfd23` (30 tests pass).

**A12 run log (2026-11-15).** The addendum was saved at 00:04:52 MYT (file time); the first item started at 00:05:39. The first run of `vad-think` stopped after 10 items (D01 to D10, last at 00:06); nothing in the files changed (same hashes). It was resumed at 00:47 with the same files (run.py skips the items already in the record), and the token usage of the 10 completed items (44,455 input and 2,575 output tokens, 21 calls) was added back from the per-call counts in their traces, as in A9. The other runs: `vad-think-combo` and the text-only control dis1 00:47–00:51; dis2 00:52–00:59 MYT. 0 harness errors, 0 rate-limit retries. Results: `EVALUATION.md` section 6.19 and `results/disfluent_vs_base.md`.

## Addendum A13: say meeting durations in minutes (written 2026-11-15, before any run of this arm)

**Question.** The spoken-confirmation check (`results/confirm_consistency.md`, D-V29) found one real error, repeated 23 times: the agent booked a 30-minute meeting and then said 「一个半小时」 (an hour and a half). The model texts show the cause. The requests say 「开个半小时的会」, where 个 counts the meeting. The model wrote 「开一个半小时的会」, which a listener can only hear as 「一个半小时」, 90 minutes, and usually corrected itself in the same sentence (「……不对，是半小时的会议」). Over T07, N06, T09 and T14 in run1 and run2, 30 of the 120 item-runs of all arms have such a text; for `vad-think-combo` it is 4 of 8 (`eval/compare_minutes.py`). Does one rule in the system prompt, asking for durations in minutes, stop it?

**Existing practice (`research/sources/normalization_excerpts.md`).**
- ElevenLabs Agents have two ways to make the model's text speakable. The default adds instructions to the system prompt. The other runs a normalizer on the text after the model and before the speech engine.
- LiveKit Agents let a developer override `tts_node` to change the model's text before it is synthesized.
- OpenAI's guide for realtime voice models asks agents to confirm exact values, and to ask when a spoken number has more than one reading.

**Chosen: one more rule in the system prompt (`agent/llm.py`, `SAY_MINUTES`).** The rule says: 「说会议时长时，照工具参数里的分钟数说成“N分钟”（比如“30分钟”“90分钟”），不要说“半小时”“一个半小时”这类说法，免得听错。」 It is added after the existing rules only when the arm sets `say_minutes`. Every other arm keeps the old prompt byte for byte (a test checks its hash).

Not done:
- **A normalizer before synthesis.** Normalizers turn digits and symbols into words, and this phrase is already words.
- **A rewrite tied to the tool record.** It could change the number, but the model's own correction would still follow (「……不对，是半小时」), so the sentence would stay wrong in a new way.
- **Confirmations filled into fixed templates from the tool record.** This would remove the error, but it replaces every confirmation the model writes. That is a bigger change and is not tested here.

**Arm `vad-think-combo-minutes`.** Same as `vad-think-combo` (A8), plus the rule. T07 and N06 will still fail the task in most runs, because the recognizer hears 十点 as 0点; the rule cannot change that.

**Runs.**
- The 42 items twice (`results/run1`, `results/run2`).
- T07, N06, T09 and T14 five more times for `vad-think-combo` and for the new arm (`results/min1` to `results/min5`, `run.py --items`). Within each repeat, both arms run one after the other.
- All model calls use the standard interface, because they are the agent's live replies (D-V19).
- Measures: `eval/compare_minutes.py` (written now, before the run) for the wording, `eval/compare_followups.py` for everything else, and `eval/confirm_consistency.py` with the repeats added as a group.

**Expectations, written down before the run.**
1. `vad-think-combo-minutes` has no slip in any of its item-runs (84 in run1 and run2, 20 in the repeats).
2. `vad-think-combo` slips in at least 3 of its 20 repeat item-runs (run1 and run2: 4 of 8). If it slips in fewer, the repeats are too few to show a difference, and the report will say so.
3. Of the new arm's reply texts that mention a duration, at least 80% say it in minutes only (`vad-think-combo`: 13 of 48, 27%).
4. The confirmation check finds no "misspoken duration" flag for the new arm.
5. Everything else as in A8:
   - strict pass: 30 to 35 per run;
   - clean tasks: first-audio median 3.5 to 4.2 s;
   - babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off;
   - interruptions: 16 of 16 stopped, median 0.20 to 0.40 s;
   - backchannels: at least 6 of 8 replies survive;
   - I05 passes and T04 fails in both runs.

**Cost.** About 9 US cents (about 6 for the two runs, about 3 for the repeats).

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/llm.py` `906dafb52488`: adds `SAY_MINUTES` and `system_prompt()`. The prompt changes only when `say_minutes` is set.
- `agent/config.py` `f2c2e694d80d`: adds the arm.
- `eval/run.py` `4a81df459412`: passes `say_minutes` to the model client.
- `eval/compare_minutes.py` `d40a42a0bfe9`: new.
- Unchanged: `agent/pipeline.py` `226b02718437`, `agent/audio.py` `653b1e17b2e1`, `eval/score.py` `ea31e3afadff`, `eval/cases.json` `5d1f2cebefd5`, `eval/pvad_enroll.json` `3bfdcb260170`.
- `tests/test_offline.py` `70bd1d5b7928`: 31 tests pass. The new one checks three things: the old prompt is unchanged (sha256 `e759c7ab9b22`), only this arm adds the rule, and every other setting of the arm equals `vad-think-combo`.

**A13 run log (2026-11-15).** The addendum was saved at 03:54:05 MYT (file time); the first item started at 03:54:28. Runs: run1 03:54–03:59 and run2 03:59–04:03 MYT, then the repeats min1 to min5 04:03–04:09 (in each repeat `vad-think-combo` first, then the new arm). 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Model cost: 0.059 USD for the two runs and 0.026 USD for the repeats (0.013 per arm), 0.085 USD in all. Results: `EVALUATION.md` section 6.21, `results/minutes_vs_combo.md` and `results/followups_vs_combo.md`.

## Addendum A14: the four follow-ups together (written 2026-11-16, before any run of this arm)

**Question.** Four changes have each been tested alone on top of `vad-think-combo`:
- a brief confirmation question (A9);
- keeping a turn whole when the user spoke first (A10);
- synthesizing later chunks as their text streams in (A11);
- saying meeting durations in minutes (A13).

Each helped in its own run. Do they still help when they run together, and does anything break?

**Existing practice.** Nothing new to look up. The sources of each change are listed in A9 to A11 and A13, and the arms in A8 to A13 already show that each change works alongside the four changes of A8.

**Why they should not interfere.** They act on different parts of the code:
- the text sent back when a cancel is held (A9);
- what happens when the user's speech began before a reply's first sound (A10);
- when later chunks are synthesized (A11);
- one rule at the end of the system prompt (A13).

The first chunk, turn-taking, barge-in and the confirmation rule are unchanged.

**Arm `vad-think-combo-plus`.** `vad-think-combo` with `confirm_brief`, `spoke_first`, `stream_tts` and `say_minutes` all set. A test checks that the arm is exactly `vad-think-combo` plus these four switches, and that each earlier arm differs from `vad-think-combo` by its one switch only.

**Runs.** The 42 items twice (`results/run1`, `results/run2`) and the four confirmation items twice (`results/confirm1`, `results/confirm2`). Comparisons: `eval/compare_followups.py` (against `vad-think-combo` and each single change), `eval/compare_minutes.py`, and `eval/confirm_consistency.py`. All model calls use the standard interface, because they are the agent's live replies (D-V19).

**Expectations, written down before the run.** Each single-change result is in brackets.
1. Confirmation items:
   - question length median at most 3.0 s (A9: 2.81 s);
   - cancel time median 9.5 to 12.0 s (A9: 11.40 s);
   - at least 7 of 8 right and 8 of 8 asked first (A9: 8 and 8).
2. Pause items: the continuation becomes its own turn in at most 1 of 12 item-runs (A10: 0 of 12; A8: 4 of 12), and at least 11 of 12 pass strictly (A10: 12).
3. Clean tasks:
   - silence inside the first spoken reply step, p90 at most 0.20 s (A11: 0.15 s; A8: 0.27 s);
   - steps falling back to waiting for the whole text: at most 5%.
4. No item-run says 「一个半小时」 for a meeting that is not 90 minutes, and at least 80% of the reply texts with a duration say it in minutes only (A13: 0 of 104; 93%).
5. Everything else as in A8:
   - strict pass: 31 to 35 per run (the single changes: 30 to 33);
   - clean tasks: first-audio median 3.4 to 4.2 s;
   - babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off;
   - interruptions: at least 15 of 16 stopped, with a median of 0.20 to 0.40 s. With streamed chunks, one interruption in A11 began inside a gap between two chunks and could not be scored; any such case is reported, not counted as a miss;
   - backchannels: at least 6 of 8 replies survive;
   - I05 passes and T04 fails in both runs.

**Cost.** About 7 US cents.

**Files (sha256, first 12 characters) at the start of this arm.**
- `agent/config.py` `e079d8fd50c6`: adds the arm. Since A13 it also reads the local data folder from `PORTFOLIO_LOCAL` (change 4 under "Changes after the run").
- `tests/test_offline.py` `c08347f2d467`: 32 tests pass. The new one checks the arm's settings as described above.
- `eval/compare_minutes.py` `3625e519f399`: takes more arms as arguments.
- Unchanged since A13: `agent/llm.py` `906dafb52488`, `agent/pipeline.py` `226b02718437`, `agent/audio.py` `653b1e17b2e1`, `eval/run.py` `4a81df459412`, `eval/score.py` `ea31e3afadff`, `eval/pvad_enroll.json` `3bfdcb260170`, `eval/confirm_cases.json` `b1271613c440`.

**A14 run log (2026-11-16).** The addendum was saved at 18:25:18 MYT (file time); the first item started at 18:25:32. Runs: run1 18:25–18:30, run2 18:30–18:34, confirm1 18:34–18:35 and confirm2 18:35 MYT. 0 harness errors, 0 rate-limit retries. The files listed above had not changed (same hashes). Model cost: 0.069 USD. Results: `EVALUATION.md` section 6.22, `results/followups_vs_combo.md` and `results/minutes_vs_combo.md`.
