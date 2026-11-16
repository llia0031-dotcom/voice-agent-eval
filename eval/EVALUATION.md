# Evaluating a cascaded Chinese voice agent: pauses, interruptions, backchannels and tool calls

Report, 13 to 17 November 2026. The plan, the items and the scoring rules were fixed before the run in [`PREREGISTRATION.md`](PREREGISTRATION.md); every number below comes from `results/run1`, `results/run2` and `results/asr_check.json`, through `score.py` and `tables.py` (generated tables: `results/summary.md`). Sections 6.7 to 6.10, 6.12 to 6.19, 6.21 and 6.22 are follow-up runs, each with its own plan written before it ran (addenda A1 to A14 of the preregistration; tables: `results/words_vs_base.md`, `results/lang_vs_base.md`, `results/dur_vs_base.md`, `results/pause_vs_base.md`, `results/short_vs_base.md`, `results/confirm_vs_base.md`, `results/pvad_vs_base.md`, `results/combo_vs_base.md`, `results/followups_vs_combo.md`, `results/minutes_vs_combo.md`). Section 6.11, the check before 6.14 and section 6.20 are offline, with no model calls (`results/bcdet_offline_check.md`, `results/pvad_offline_check.md`, `results/confirm_consistency.md`).

## Summary

A local cascaded voice agent (Silero VAD, SenseVoice, `claude-haiku-5-5` with MCP tools, MeloTTS) was run on 42 scripted Chinese, English and code-switched conversations, in three listening and thinking set-ups plus a text-only control, twice each.

| | `vad` (thinking off) | `smart` (Smart Turn) | `vad-think` (thinking on) | text only |
|---|---|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 29 | 29 / 30 | 30 / 31 | 41 / 41 |
| First audio after the user stops, clean tasks, median (p90) | 2.94 s (3.49) | 2.80 s (5.47) | 3.95 s (5.24) | — |
| Answer audio (reply after the last tool call), median | 5.80 s | 5.55 s | 3.95 s | — |
| Stopped when interrupted / stop latency median | 16 of 16 / 0.25 s | 16 of 16 / 0.26 s | 16 of 16 / 0.26 s | — |
| Kept talking through 嗯 / 好的 / Okay | 0 of 8 | 0 of 8 | 0 of 8 | — |
| Item-runs with reasoning said aloud (of 84) | 23 | 17 | 0 | 13 in text |

1. **What breaks the experience is listening, not the model.** With perfect transcripts and turn-taking the same model, prompt and tools pass 41 of 42 items in both runs. With audio, about 30 pass. After reading every failure, the causes are: recognition of names, times and short pauses (10–12 item-runs per arm), stopping on a backchannel (8 per arm, every backchannel), a cancellation done before the user could say "wait" (2 per arm; a confirmation question fixes it, section 6.13), background speech (0–3), Smart Turn ending a turn inside a pause (2, `smart` only) and talking too long after "不用说了" (0–1).
2. **Barge-in is fast but cannot tell "wait" from "嗯".** The agent stopped within 0.25 s of every interruption, and also within the same time on every 嗯, 嗯嗯, 好的 and Okay. A 0.2 s voice-activity rule has no notion of what was said.
3. **A spoken filler buys first-audio time and costs answer time.** With thinking off the agent says something like "好的，我查一下" while tools run: first audio comes 1.0 s sooner than with thinking on, but the actual answer comes 1.9 s later, because it queues behind the filler. With thinking off the agent also said its reasoning aloud in 23 of 84 item-runs ("The user asks about…", "后天是 2026-11-18…"), sometimes in English to a Chinese user; with thinking on, never. Letting the first chunk be as short as "好的，" (section 6.12) cut the first-audio median with thinking on from 3.95 s to 3.79 s, less than the 0.60 s difference between two runs of the same arm.
4. **Smart Turn halves early turn ends in pauses but adds a long tail.** It caught 3 of 6 mid-sentence pauses (the 0.55 s silence rule caught none), lowered the median first-audio time by 0.14 s, and raised the 90th percentile from 3.5 s to 5.5 s, because it judged 4 of 20 finished Chinese requests and 2 of 6 code-switched ones unfinished and waited for its 3 s fallback. When it was wrong in a pause it answered sooner than the silence rule would, so it was the only arm to talk into a pause (2 item-runs).
5. **Background speech defeats voice-activity turn-taking.** Silero marked 99.6% of pure four-talker babble frames as speech, so every babble item waited for the 20 s cap, and in 23 of 24 babble item-runs a gap in the babble then cut the agent off mid-answer. Pink noise at 5 dB was marked as speech in no frame and cost one item (周会 heard as 都会). A voice-activity model that follows the first speaker (section 6.14) ended every babble turn when the user stopped and never let the babble cut in.
6. **Waiting for words fixes half of the backchannels (follow-up, section 6.7).** With a two-word rule on barge-in, the agent talked through 好的 and Okay every time, still stopped for all 16 interruptions (median 0.41 s instead of 0.26 s, at most 0.99 s), and passed 33 of 42 in both runs instead of 30 and 31. It still stopped on 嗯 and 嗯嗯, which the recognizer read as "Me you" and "ねな"; reading them as Chinese instead (section 6.8) only turned them into "没题" and "你能". Adding LiveKit's default 0.5 s minimum (section 6.9) spared 嗯 as well (6 of 8 backchannels, 34 of 42 in both runs), at the cost of a median stop latency of 0.58 s. Pausing instead of waiting (section 6.10) kept the 0.26 s stop and resumed the reply after 6 of 8 backchannels, after 0.90–1.15 s of silence; the scoring rule still counts each pause as a stop. An acoustic backchannel detector, tried offline on the saved recordings, found fewer backchannels than the word rule (section 6.11).

7. **The changes that helped also work together (section 6.15).** With pVAD, the short first chunk, the confirmation before cancelling and the pause, babble never held a turn or cut a reply, every real interruption stopped within 0.36 s, the reply survived all 8 backchannels and "wait" stopped the cancellation in both runs. On the frozen strict score this is 30 and 32 of 42 against 30 and 31, because pauses count as stops and one script (T04) cannot answer the confirmation question. Adding the four later follow-ups (section 6.22) kept the brief question, the whole turns and the minutes; streaming showed no gain, because the remaining silences come from synthesis time.
8. **Disfluent requests and new voices (section 6.19).** Fourteen more items, in voices the 42 do not use, passed about as often as fluent ones. The model handled disfluent wording from text in every case. The failures came from a filler that the recognizer wrote as a character (「呃」 as 「鄂」, a pause as 「已」), which changed what the request seemed to say.
9. **What the agent says about a change matches what the tools did, with one repeated slip (section 6.20).** Checked with evidence-check over all saved runs, 605 of 628 rated confirmations were consistent (96%). All 23 others are the same slip: a half-hour meeting booked correctly but announced as 「一个半小时」 before a correction. One rule in the system prompt, asking for durations in minutes, removed it: 0 of 104 item-runs, against 9 of 28 for the same arm without the rule on the same four items (section 6.21).

The set is synthetic (one synthesis model, a few voices, short pauses only), small (42 items, two runs) and run on one machine; see section 9.

## 1. Why this evaluation

A voice agent is judged in the first second of a conversation: does it wait while the user is thinking, stop when the user cuts in, keep talking through "嗯", and still do the task right when the words were misheard? Open benchmarks measure parts of this:

| Benchmark | Measures | Chinese | Tool calls |
|---|---|---|---|
| Full-Duplex-Bench v1 / v1.5 (arXiv 2503.04721, 2507.23159) | pause handling, backchannels, turn-taking, interruption; stop and response latency | no | no |
| Full-Duplex-Bench v3 (arXiv 2604.04847) | multi-step tool calls from real disfluent speech | no | yes |
| FLEXI (arXiv 2509.22243) | six full-duplex scenarios incl. model-initiated interruption | not stated | no |
| FD-Bench (arXiv 2507.19040) | interruption types, noise, early interruption | no | no |
| HumDial Track 2, ECHO (arXiv 2609.17360) | Chinese turn-taking and interruption | yes | no |

None found combines Chinese and code-switched speech, interruptions, pauses and backchannels with tool calls that change data. This evaluation reuses their metric definitions (response latency and stop latency from FDB v1.5, turn-over in pauses from FDB v1, strict tool pass from FDB v3) and adds that combination. Their code is not copied: FDB is CC BY-NC 4.0 and FD-Bench is under a non-commercial licence.

## 2. System under test

A cascaded agent of the kind many products start with, run on one laptop CPU (Intel i9-14900HX) except for the language model:

```
microphone ─► Silero VAD ─► turn end? ─► SenseVoice-Small ─► claude-haiku-5-5 ◄─► MCP tool server
   ▲            (barge-in)    (silence or Smart Turn)  (ASR)        (streamed)      (weather, calendar, reminders)
   │                                                                      │
   └──────────────── user stops it by talking ◄── MeloTTS speech ◄────────┘ first chunk at the first comma or full stop
```

The tools are served by a local MCP server (official Python SDK); the agent lists them at start-up and converts them to Claude tool definitions. All data is invented and fixed (today is 2026-11-16; three seeded meetings; eight cities over three days).

**Time.** A virtual clock moves through the microphone signal in 32 ms frames. When the agent decides the user has finished, each step really runs on the machine (recognition, every model request including network time, every tool call, every speech chunk) and its measured time is added to the clock; between steps the clock catches up frame by frame, so a user who goes on talking is heard at the right moment. Before the agent speaks, that cancels the reply and the turn continues; while it speaks, the agent stops (barge-in) and its next request says how far the user heard. Assumed: perfect echo cancellation (the microphone holds only the user and the noise) and an instant stop at the detecting frame.

## 3. Test set

42 scripted items, answers fixed when written ([`cases.json`](cases.json)). The user's voice is synthesized locally (Kokoro v1.1; five Chinese and two English voices), trimmed and set to one loudness.

| Category | Items | zh / en / mixed | What happens |
|---|---|---|---|
| task | 16 | 10 / 3 / 3 | weather, create / move / cancel a meeting, reminder; T09 must ask for the time first; T10 asks for a city with no data |
| pause | 6 | 4 / 1 / 1 | the user stops mid-request for 1.2–2.0 s ("帮我约个会，……明天上午十点，和王强，一个小时。") |
| interrupt | 8 | 5 / 1 / 2 | 0.8–1.5 s into the agent's answer: a correction ("等一下，改成四点"), "stop" ("好了，不用说了"), or "先别取消" |
| backchannel | 4 | 3 / 1 / 0 | 嗯 / 嗯嗯 / 好的 / Okay during the answer; the agent should keep talking |
| noise | 8 | 5 / 1 / 2 | copies of task items with pink noise (5 dB SNR) or four-talker babble (15 dB SNR) |

A task passes when the mock server's final data is exactly right (a duplicate meeting fails) and, where stated, the right weather call was made and the key fact was actually heard. Before any agent run, two recognizers (SenseVoice and Whisper-small) transcribed the clean synthetic speech; one English name both heard as a different word ("Anna" as "Ho" / "Honour") was replaced, and English words missing from the synthesis lexicon were rephrased. Homophone misses (李娜 heard as 李那, 西安 as 夕安) were kept as genuine recognition problems.

## 4. Arms

| Arm | Turn end | Model thinking |
|---|---|---|
| `vad` | 0.55 s of silence (LiveKit's Silero default) | off |
| `smart` | 0.2 s of silence, then Smart Turn v3.2 must judge the turn complete; 3 s fallback (Pipecat defaults) | off |
| `vad-think` | as `vad` | adaptive |
| `oracle` | no audio: the scripted text goes turn by turn to the same model and tools | off |

All arms: `claude-haiku-5-5`, effort low, the same system prompt (Chinese, with a contact list and the rule "reply in the user's language") and tools. Barge-in in every audio arm: 0.2 s of continuous speech while the agent talks (Pipecat's `start_secs`). Four more arms were added after the main run to test rules on barge-in: `vad-think-words` (section 6.7), `vad-think-words-lang` (section 6.8), `vad-think-words-dur` (section 6.9) and `vad-think-pause` (section 6.10); three more test a shorter first speech chunk, `vad-think-short` (section 6.12), a spoken confirmation before a cancellation, `vad-think-confirm` (section 6.13), and a voice-activity model that follows one speaker, `vad-think-pvad` (section 6.14). `vad-think-combo` combines the four changes that helped (section 6.15), and later arms change it one thing at a time (section 6.16 on). `oracle` separates hearing errors from reasoning errors. Each arm ran twice over all 42 items.

## 5. What was measured

Rules in [`score.py`](score.py), fixed before the run:

- **Task pass**: final tool data exactly right; where stated, the right weather call and the key fact actually heard (only the played part of each speech chunk counts), no temperature for a city with no data, no meeting created before the user gave the time.
- **Interaction pass** (audio arms): the agent stops within an interruption (+1 s) and says at most 3 s more after "stop"; it keeps talking through a backchannel; no agent audio inside a pause.
- **Strict pass**: both.
- **Response latency**: first agent audio after the user's turn ends minus the end of the user's speech (FDB v1.5, Eq. 2); also the answer audio and its parts.
- **Stop latency**: barge-in detection minus the start of the interruption (FDB v1.5, Eq. 1).
- **Recognition**: mixed error rate (each Chinese character and English word is one token) on the exact user segments; key words present in what the model received.
- **Reasoning said aloud**: heard text matching `用户|the user|识别结果|应为|2026-1x-xx|工具|tool`.

**Time of the local speech steps.** During the run the machine was fully loaded by programs outside this evaluation, which made recognition and synthesis 3–10 times slower than on the smoke runs. The speech components therefore still run for real (their words and audio are used), but the time they add comes from a linear fit of the smoke-run timings: recognition 0.056 s per second of audio, synthesis 0.39 s per second of output audio, Smart Turn 0.025 s. Model calls, tool calls and network time are measured live. Section 6.2 gives the latency at the full-load timings as a sensitivity check. [`PREREGISTRATION.md`](PREREGISTRATION.md) lists this and two other harness changes made after the run started (rate-limit retries; a reply waiting to play is now dropped when the user goes on, with five items rerun in every arm).

## 6. Results

### 6.1 Pass rates

Strict pass, run1 + run2 (out of twice the number of items):

| Arm | task (16) | pause (6) | interrupt (8) | backchannel (4) | pink (4) | babble (4) | all (42) |
|---|---|---|---|---|---|---|---|
| `vad` | 26/32 | 12/12 | 11/16 | 0/8 | 4/8 | 6/8 | 59/84 |
| `smart` | 26/32 | 10/12 | 12/16 | 0/8 | 6/8 | 5/8 | 59/84 |
| `vad-think` | 26/32 | 12/12 | 11/16 | 0/8 | 4/8 | 8/8 | 61/84 |
| text only | 32/32 | 12/12 | 14/16 | 8/8 | 8/8 | 8/8 | 82/84 |

The three audio arms are within two item-runs of each other, which the plan treats as noise. Same-item agreement between run1 and run2 was 41/42 (`vad`), 39/42 (`smart`), 41/42 (`vad-think`) and 42/42 (text only). The babble column says little: 23 of 24 babble item-runs were cut off by the babble at the same moment, and an item passed when the key fact had been said before that (section 6.5).

### 6.2 Latency

Clean task items, first user turn, run1 + run2 (n = 32 per arm), seconds:

| Arm | First audio median | p90 | Answer audio median | Turn-end wait | Recognition | Model to first speech chunk | First chunk synthesis |
|---|---|---|---|---|---|---|---|
| `vad` | 2.94 | 3.49 | 5.80 | 0.57 | 0.20 | 0.95 | 1.11 |
| `smart` | 2.80 | 5.47 | 5.55 | 0.24 | 0.19 | 0.97 | 1.16 |
| `vad-think` | 3.95 | 5.24 | 3.95 | 0.57 | 0.20 | 2.32 | 0.85 |

(Parts are medians of each part, so they do not add up exactly.)

- The model (network included) and the first chunk of speech take most of the time; tools take milliseconds. The first chunk was long, a median of 24 characters in the `vad` arm, because "好的，" alone is under the 4-character minimum, so the chunk ran to the next comma. A shorter first chunk is the cheapest latency fix this run points to; section 6.12 tests it.
- With thinking on, the time to the first speech chunk rises from 0.95 s to 2.32 s and there is no filler; with thinking off, the filler arrives first and the answer waits behind it (5.80 s vs 3.95 s).
- Per run, the first-audio median was 2.96 / 2.86 s (`vad`), 2.85 / 2.78 s (`smart`) and 4.47 / 3.87 s (`vad-think`).
- Sensitivity: at the full-load speech timings (`local_timing_loaded.json`) the clean-task first-audio median would be about 3.9 s (`vad`), 4.1 s (`smart`) and 4.8 s (`vad-think`), a static re-estimate without re-simulating the conversation.
- For context only (different speech, language, set-up and measurement): the Full-Duplex-Bench v1 table reports smooth turn-taking latency of 1.470 s for GPT-Realtime and 0.567 s for Gemini 3.1 Flash Live (minimal).

### 6.3 Interruptions and backchannels

| Arm | Interruptions during speech | Stopped | Stop latency median (max) | Quiet after "stop" (I03, I08) | Backchannels during speech | Kept talking |
|---|---|---|---|---|---|---|
| `vad` | 16/16 | 16 | 0.25 s (0.45) | 3/4 | 8/8 | 0 |
| `smart` | 16/16 | 16 | 0.26 s (0.47) | 4/4 | 8/8 | 0 |
| `vad-think` | 16/16 | 16 | 0.26 s (0.31) | 3/4 | 8/8 | 0 |

Every interruption and every backchannel started while the agent was talking, so all were scored. After a correction the agent was told how far the user had heard; corrections were applied correctly when the first request had been heard correctly (I01 in every arm moved the new meeting to 16:00 with `update_meeting` rather than creating a second one). After a false stop the backchannel became a new user turn, and the recognizer made it worse: 嗯 came out as "Meium", "Me you" or "Ma you", and 嗯嗯 as Japanese ("ねなや？"). The agent then restarted or summarized its answer, sometimes after explaining the transcript aloud ("用户说的是日语…"); with thinking on it answered 嗯嗯 in Japanese in both runs, and "Okay" switched some replies to English.

### 6.4 Pauses

Six items with a 1.2–2.0 s pause mid-request, run1 + run2 (12 item-runs per arm):

| Arm | Turn end detected inside the pause | Agent audio inside the pause | Change made inside the pause | Task pass |
|---|---|---|---|---|
| `vad` | 12 | 0 | 0 | 12 |
| `smart` | 6 | 2 | 0 | 12 |
| `vad-think` | 12 | 0 | 0 | 12 |

The 0.55 s silence rule ended the turn in every pause, but the reply took longer than the rest of the pause, so the user's next words cancelled it before it played and the whole turn was heard again. Smart Turn judged the pause unfinished for "帮我约个会，", "把明天的周会，" and "帮我查一下，" and finished for "查一下，", "提醒我后天，" and "Book a meeting with Tom Lee," (the same in both runs); when it was wrong it answered sooner, and twice the agent's "Sure," or a question played before the user went on. No arm made a change inside a pause, but the cost of the early turn ends is a wasted model request in 6 to 12 of 12 item-runs.

### 6.5 Noise

- **Pink noise, 5 dB SNR** (N01–N04): the VAD marked no frame of pure pink noise as speech, so turn-taking was unaffected (first-audio median 3.24 s for `vad`). One item flipped: N03, where 周会 became 都会 in the `vad` and `vad-think` runs. The `smart` runs ended the turn sooner, sent a slightly shorter window to the recognizer and got 周会 right: the same audio, segmented differently, was recognized differently.
- **Four-talker babble, 15 dB SNR** (N05–N08): the turn ended only at the 20 s cap in every item-run (first-audio median 18.6–20.4 s). Then, in 23 of 24 item-runs, a short gap in the babble followed by more babble was taken as a barge-in at the same moment (28.4 s), the answer was cut, and a second 20 s turn of babble alone followed, after which the agent said it had not heard clearly and asked the user to repeat. Whether the item passed depended only on whether the key fact had been said before 28.4 s. One `smart` run created a 90-minute meeting from "开个半小时的会", reading 个半小时 as one and a half hours.

### 6.6 Recognition

On the exact user segments (SenseVoice, no turn-taking): mixed error rate 4.7% in Chinese (14 of 301 tokens, 32 segments), 8.7% in English (6/69) and 7.5% code-switched (7/93). Errors that changed the outcome:

| Item | Said | Recognized | Result |
|---|---|---|---|
| T07 | 后天上午十点 | 后天上午0点 | a meeting at 00:00 in every item-run, sometimes after the agent remarked that 凌晨0点 was odd |
| T09 | 明天下午两点，半个小时 | 明天下午2点半个小时 | the pause was lost and "2点半" read as 14:30, every item-run |
| T14 | 帮我约 Tom | 帮我约汤明 | the agent asked who 汤明 is (often suggesting Tom Lee) in 5 of 6 item-runs and booked "汤明" in one |
| I07 | 帮我约 Emma 后天上午十一点 | 帮我约M后，天上51点 | no meeting, or one with Emma Smith tomorrow at 17:00 (`smart`) |
| N03 | 明天的周会推迟 (pink noise) | 明天的都会推迟 | "都会" read as "all meetings": both of tomorrow's meetings moved by an hour (`vad`, `vad-think`) |
| N04 | 帮我约 Tom (pink noise) | 帮我约康 | the agent asked who 康 is, every item-run |

The contact list did repair a homophone: in I01 the `smart` runs heard 李娜 as 李那, and the agent still booked 李娜. Every key word listed for an item reached the model in 70 of 84 `vad` item-runs (backchannel items list none).

### 6.7 Follow-up: wait for words before stopping

After the main run, one fix from section 10 was tested. The arm `vad-think-words` is `vad-think` with a word rule on barge-in: while the agent talks, user speech no longer stops it after 0.2 s. The recognizer re-reads the held speech every 0.16 s, and the agent stops once a read holds two units (a Chinese character or an English word) that are not backchannel words such as 嗯, 好的 or Okay. Speech that never reaches two units is dropped and never reaches the model. This is Pipecat's minimum-words turn start, counted per character for Chinese, with a backchannel list as proposed in a LiveKit issue (`agent/bargein.py`). The rule, the word list and five expectations were written in [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A1 before the arm ran. It ran twice over all 42 items, about twelve hours after the main run; `vad-think` was not rerun.

| | `vad-think` | `vad-think-words` |
|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 33 / 33 |
| Kept talking through a backchannel | 0 of 8 | 4 of 8 |
| Stopped when interrupted | 16 of 16 | 16 of 16 |
| Stop latency median (max) | 0.26 s (0.31) | 0.41 s (0.99) |
| Babble item-runs cut off mid-answer | 8 of 8 | 8 of 8 |
| First audio, clean tasks, median | 3.95 s | 3.81 s |

- **It works when the recognizer reads the backchannel as a word.** 好的 (B03) and Okay (B04) were read correctly in all four item-runs, and the agent talked straight through to the end of its answer.
- **It fails on the hum.** 嗯 (B01) was read as "Me you" or "Ma you" and 嗯嗯 (B02) as "ねな": two units each, so the agent stopped 0.62 s and 0.33 s after they began, and the false turn went as badly as in the main run: after 嗯 the answer restarted from the top (in English in one run, after the transcript "Meium."), and after 嗯嗯 ("ねなんや？") it continued in Japanese in both runs. The word list was not changed after the run.
- **Chinese interruptions barely slowed down; English ones did.** SenseVoice often returns two characters from the first fraction of a second of Chinese speech, sometimes the wrong ones (等一下 read as 等于 or 东意), so every interruption that starts in Chinese (I01–I05, I07) stopped at the first or second read, 0.27–0.47 s after it began. English words take longer: "Sorry, I meant Guangzhou." stopped after 0.87–0.88 s. "OK 可以了，stop。" took 0.99 s, because its first word is on the backchannel list; the agent said one more phrase ("气温 12 到 18 摄氏度，") before it stopped. Every stop request was still followed by less than 3 s of speech.
- **Babble is not helped.** Background speech was read as kana ("そぱ") at the first read and cut the answer at the same moment as before. N06 failed in one run: that time the model asked to confirm the meeting instead of booking it, and the cut came before the user could answer.
- **Cost:** 0.064 USD for the two runs.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Backchannels kept talking: at least 5 of 8 | Not held: 4 of 8 (好的 and Okay in both runs; 嗯 and 嗯嗯 misread as two units) |
| 2 | All 16 interruptions stop; median stop latency 0.45–0.8 s | Half held: 16 of 16 stopped; the median rose less than expected, to 0.41 s; the maximum was 0.99 s |
| 3 | Babble stops about as often (8 of 8) | Held: 8 of 8 |
| 4 | Strict pass 2 to 4 higher per run | Held: +3 and +2 |
| 5 | A one-word command ("停", "No") would not stop the agent | Not tested: no item has one |

A word count is only as good as the recognizer on half-second fragments: here the misses come from a hum turned into foreign words, not from the rule. Three tests follow from this, each on the same items with its own plan: read held speech in Chinese and English only, so that no Japanese text can appear (section 6.8); LiveKit's pause and resume (go quiet at once, carry on if no words arrive; section 6.10); and an acoustic backchannel model, once one is available for Chinese without a cloud account.

### 6.8 Follow-up: read held speech in the conversation's language

The misses in 6.7 looked like a language problem, so a second follow-up fixed the recognizer's language for the held speech. `vad-think-words-lang` is `vad-think-words` with SenseVoice set to Chinese when the user's last turn was Chinese and to English when it was English; the turn sent to the model is still read with auto-detect. Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A2. Two runs over all 42 items; tables: `results/lang_vs_base.md`.

| | `vad-think` | `vad-think-words` | `vad-think-words-lang` |
|---|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 33 / 33 | 33 / 32 |
| Kept talking through a backchannel | 0 of 8 | 4 of 8 | 4 of 8 |
| Stopped when interrupted | 16 of 16 | 16 of 16 | 16 of 16 |
| Stop latency median (max) | 0.26 s (0.31) | 0.41 s (0.99) | 0.34 s (1.07) |
| Babble item-runs cut off mid-answer | 8 of 8 | 8 of 8 | 6 of 8 |

- **The hum still becomes two words.** Read as Chinese, 嗯 came out as "没题" or "没天" and 嗯嗯 as "你能" or "奶奶": two characters each, so the agent stopped as before. The turn sent to the model, still auto-detected, was again "Me you." or Japanese, and the reply came in English or Japanese. Fixing the language only changed which wrong words appeared.
- **好的 and Okay** were ignored in all four item-runs, as in 6.7.
- **English got slower.** With English fixed, "Sorry, I meant Guangzhou." stopped after 1.06–1.07 s (0.87–0.88 s with auto-detect).
- **An English user in Chinese babble is spared.** In N07, an English request in Chinese babble, the English recognizer read the babble as "." in both runs, so the answer was not cut; the three Chinese babble items were cut as before. The rule re-read the babble 50 times over 21 s before dropping it.
- **Failures not caused by the rule.** I03 failed in run2 because the agent said 3.9 s more after "好了，不用说了。", the same failure as `vad-think` run1. In run1, T09 hit a harness error in speech synthesis; it was fixed and the item-run rerun (PREREGISTRATION A2).
- **Cost:** 0.063 USD for the two runs and the rerun.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Backchannels kept talking: at least 6 of 8 | Not held: 4 of 8, the same two items as in 6.7 |
| 2 | All 16 interruptions stop; median stop latency within 0.1 s of 0.41 s | Held: 16 of 16, 0.34 s |
| 3 | Babble still cut in at least 6 of 8 item-runs | Held: 6 of 8 |
| 4 | Strict pass 33 to 35 per run | Half held: 33 and 32 |
| 5 | B04 still kept talking; I06 stops within 1.0 s | Half held: B04 yes; I06 took 1.06–1.07 s |

Together, 6.7 and 6.8 show that this recognizer cannot tell a hum from a short command by its text, whatever language it is told to expect: it writes two syllables for 嗯 either way. The next test has to use something other than the transcript: how long the sound lasts (LiveKit by default ignores speech shorter than 0.5 s), a short pause that resumes when no words arrive, or an acoustic backchannel model. The first of these, LiveKit's default 0.5 s minimum, is section 6.9.

### 6.9 Follow-up: a 0.5 s minimum as well as words

LiveKit counts an interruption only when the speech has lasted at least `min_duration` (default 0.5 s) and, if set, has `min_words`. The arm `vad-think-words-dur` adds that default to the word rule of 6.7 (auto-detect): the agent stops only when a read holds two units and the held speech has 0.5 s of voiced frames; a stretch with less voiced time is dropped whatever it says. The 0.5 s is LiveKit's default, not a value fitted to these items. Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A3. A first attempt stopped at the first model call, which the API rejected for billing (kept in `results/aborted/`, not scored); the arm then ran twice over all 42 items with the same files. Tables: `results/dur_vs_base.md`.

| | `vad-think` | `vad-think-words` | `vad-think-words-dur` |
|---|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 33 / 33 | 34 / 34 |
| Kept talking through a backchannel | 0 of 8 | 4 of 8 | 6 of 8 |
| Stopped when interrupted | 16 of 16 | 16 of 16 | 16 of 16 |
| Stop latency median (max) | 0.26 s (0.31) | 0.41 s (0.99) | 0.58 s (1.04) |
| Babble item-runs cut off mid-answer | 8 of 8 | 8 of 8 | 6 of 8 |

- **嗯 is spared, by a small margin.** The detector gave the 0.41 s 嗯 clip 0.45 s and 0.48 s of voiced time, under the 0.5 s line, so its reading ("Meium.") never counted and the agent talked straight through in both runs. 嗯嗯 got 0.51 s, just over the line, was read as "ねな？" and stopped the agent as before (B02, 0.57 s after it began). The margins are 0.02–0.05 s: a slightly longer hum would flip either result.
- **Every stop now waits.** Interruptions that start in Chinese stopped 0.53–0.71 s after they began (0.24–0.30 s with `vad-think`); English and "OK …" ones 0.80–1.04 s. Each stop request was still followed by less than 3 s of speech.
- **Babble is not helped.** Background speech still passed both checks, 0.5 s later than before; two answers had already ended by then, which is why 6 and not 8 babble item-runs were cut.
- **An offline estimate was wrong.** Before this run, running the detector alone over each clip from a reset state (`results/dur_offline_check.md`) gave 嗯 0.51–0.54 s and predicted no gain. In the conversation the detector had context and gave less. Only the full run settles a threshold this close.
- **Cost:** 0.062 USD for the two runs.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Backchannels kept talking: at least 6 of 8 | Held: 6 of 8 (B01, B03, B04 in both runs) |
| 2 | All 16 interruptions stop; median stop latency 0.5–0.7 s | Held: 16 of 16, 0.58 s |
| 3 | Babble still cut in at least 6 of 8 item-runs | Held: 6 of 8 |
| 4 | Strict pass 33 to 35 per run | Held: 34 and 34 |
| 5 | A real command shorter than 0.5 s would be ignored | Not tested: no item has one |

Across 6.7 to 6.9 the trade is plain: each step that lets the agent talk through more backchannels makes every real stop later, from 0.26 s with voice activity alone to 0.58 s with words and a 0.5 s minimum, and 嗯嗯 still stops it. LiveKit's other default, a short pause that resumes when no words arrive, could keep a fast stop and recover from false ones; section 6.10 tests it.

### 6.10 Follow-up: pause first, then cancel or resume

LiveKit's default does not wait before it stops. Speech heard while the agent talks pauses the agent's audio without cancelling the reply; if no transcript arrives within `false_interruption_timeout` (2.0 s) after the user stops, the agent carries on from where it stopped. The arm `vad-think-pause` pauses at vad-think's 0.2 s onset and judges the held speech with the rule of 6.9 (two units and 0.5 s of voiced time). A real interruption cancels the reply; anything else resumes it as soon as the verdict is in. Three settings differ from LiveKit's defaults, all fixed before the run:
- the pause starts at 0.2 s of speech, not 0.5 s;
- the verdict uses the 6.9 rule, because under LiveKit's own rule any transcript ends the pause as an interruption, and every backchannel here was transcribed as text;
- the reply resumes at once instead of after 2.0 s.

Scoring is unchanged, so a pause counts as a stop. Plan and seven expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A4. The arm ran twice over all 42 items. Tables: `results/pause_vs_base.md`.

| | `vad-think` | `vad-think-words-dur` | `vad-think-pause` |
|---|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 34 / 34 | 31 / 28 |
| Stopped (or paused) when interrupted | 16 of 16 | 16 of 16 | 16 of 16 |
| Stop latency median (max) | 0.26 s (0.31) | 0.58 s (1.04) | 0.26 s (0.34) |
| Reply survived a backchannel | 0 of 8 | 6 of 8, without a break | 6 of 8, after a 0.90–1.15 s pause |
| Babble item-runs cut off mid-answer | 8 of 8 | 6 of 8 | 7 of 8 |

- **Real stops are as fast as with voice activity alone.** The agent went quiet 0.24–0.34 s after each interruption began (vad-think: 0.24–0.31 s). The verdict that followed cancelled all 16 replies; none was resumed by mistake.
- **A backchannel costs about a second of silence instead of the reply.** After 嗯, 好的 and Okay the agent fell silent for 0.90–1.15 s and then went on from where it stopped, in both runs. The backchannel never reached the model. 嗯嗯 was again read as "ねな？" and cancelled the reply, as in 6.9. Under the frozen rule all eight items still count as stops, so strict pass on backchannels stays 0 of 8.
- **Babble is not helped.** Background speech at 28.4 s paused the agent in 7 of 8 item-runs. It was read as "家里。" and cancelled the reply each time.
- **Run2's lower strict count does not come from the pause.** Against vad-think, the arm passed T14 and I03 in run1 and lost N06 in both runs, and I03 and N08 in run2.
  - In I03 (run2) the agent stopped at once but its reply after the stop ran 4.2 s, over the 3 s limit; vad-think failed the same way in run1.
  - In N06 and N08 the model's first reply came before any overlap, to the same recognizer text the other arms got. It asked for confirmation or found no matching meeting instead of making the change. `vad-think-words-dur` lost N06 in run1 the same way.
- **Cost:** 0.063 USD for the two runs.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | All 16 interruptions stop; median 0.24–0.30 s, max at most 0.35 s; no wrong resumes | Held: 16 of 16, 0.26 s, max 0.34 s, 0 wrong resumes |
| 2 | Backchannels kept talking under the frozen rule: 0 of 8 | Held: 0 of 8 |
| 3 | The paused reply resumes after 6 of 8 backchannels | Held: 6 of 8 (B01, B03, B04 in both runs) |
| 4 | Silence while paused: 0.8–1.3 s | Held: 0.90–1.15 s |
| 5 | Babble pauses the agent in at least 7 of 8 item-runs, and every babble pause cancels the reply | Held: 7 of 8, all 7 cancelled |
| 6 | Strict pass 30 to 32 per run | Not held: 31 and 28 |
| 7 | Clean tasks: median first audio 3.65–4.25 s | Held: 4.18 s |

Of the settings tried, only pausing keeps the 0.26 s stop and still keeps the reply after most backchannels. The price is about a second of silence after each 嗯, 好的 or Okay, and the frozen score cannot tell that from a cancelled reply. It uses the verdict of 6.9, so the same fragility applies: 嗯 was spared at 0.45 s of voiced time against a 0.5 s line, and 嗯嗯 still cancels the reply. LiveKit's own 2.0 s wait before resuming was not run; it would add about 2 s to each pause.

### 6.11 Offline check: an acoustic backchannel detector

Every rule so far judged the held speech by its transcript, and the recognizer writes 嗯 and 嗯嗯 as foreign syllables. MaAI (Kyoto University; code MIT; the Chinese model's weights CC BY-NC-ND 4.0, the English model lists no licence) includes `bc_det`, which hears both sides of the conversation and gives, every 80 ms, the probability that the user is backchanneling. Chinese, English and Japanese versions run on a CPU. Before any scored run it was tried offline on the saved two-channel recordings of 6.9 and 6.10 (`eval/bcdet_offline_check.py`, no model calls; table: `results/bcdet_offline_check.md`).

The rule was fixed before any output was seen. A held stretch counts as a backchannel if the score reaches 0.45 within 0.8 s of the onset; 0.45 is MaAI's event-level threshold for its Japanese data. A scored round would follow only if this got more of the 24 backchannel and interruption stretches right than the word-and-duration rule of 6.9, which got 22.

| Judged by | Recordings from | Backchannels found | Interruptions kept as interruptions | Right (of 24) |
|---|---|---|---|---|
| `bc_det` | `vad-think-pause` | 2 of 8 | 16 of 16 | 18 |
| `bc_det` | `vad-think-words-dur` | 1 of 8 | 16 of 16 | 17 |
| Word-and-duration rule (6.9) | same items | 6 of 8 | 16 of 16 | 22 |

- **It never took an interruption for a backchannel, but it found few backchannels.** 嗯嗯 scored at most 0.05 and 好的 at most 0.14. Only Okay (0.29–0.69) and 嗯 (0.07–0.50) came near the line.
- **No threshold would have done better.** I03's "好了，不用说了" scored up to 0.32, above every 嗯嗯 and 好的.
- **The clips may be part of the reason.** The user voices here are synthetic, and MaAI does not say what the Chinese detector was trained on. A synthetic 嗯 may not sound like the backchannels it learned, so this result is about these clips, not about the model in general.
- **Speed is not the problem.** It took 0.41 s per second of audio on this CPU, fast enough to run live.

The scored fifth round was therefore not run (NOT RUN).

### 6.12 Follow-up: a shorter first speech chunk

A speech chunk here closes at a punctuation mark once it has 4 characters, so "好的，" runs on to the next comma (section 6.2). The stacks checked start no earlier by default:
- stream2sentence, the splitter behind RealtimeTTS, can yield a first fragment early, but not by default, with 10 characters, and not at a Chinese comma;
- LiveKit's basic tokenizer waits for 20 characters;
- Pipecat waits for the end of a sentence.

The arm `vad-think-short` lets the first chunk of each reply step close after 2 characters, and also at a colon; later chunks are unchanged. Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A5. The arm ran twice over all 42 items. Tables: `results/short_vs_base.md`.

| Clean task items, first turn, run1 + run2 | `vad-think` | `vad-think-short` |
|---|---|---|
| First audio median (p90) | 3.95 s (5.24) | 3.79 s (5.26) |
| First audio median, run1 / run2 | 4.47 / 3.87 s | 3.79 / 3.80 s |
| First chunk synthesis, median | 0.85 s | 0.58 s |
| First chunk, median characters | 15 | 8 |
| Gaps over 0.3 s between the first and second chunk (longest) | 1 of 29 (0.49 s) | 3 of 29 (0.77 s) |
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 29 / 31 |

- **Where the rule applied, the agent spoke sooner.** In 7 item-runs the first chunk became a short opening: 「好的，」 four times, 「抱歉，」 twice and 「已设置提醒：」 once. Against the same item and run in `vad-think`, their first chunk took 0.16–1.21 s less to synthesize (median 1.0 s).
- **The cost is a short silence after the opening.** The rest of a reply is synthesized once its text is complete, so after 「好的，」 the agent can stop briefly. In T13 it stopped for 0.77 s in both runs.
- **The overall gain is smaller than the noise.** Most first chunks already ended at the first comma, so the first-audio median fell by 0.16 s, while the two `vad-think` runs differed by 0.60 s. The model's time to the first chunk (median 2.30 s against 2.32 s) still dominates.
- **Nothing else moved.** All 16 interruptions stopped (median 0.25 s), no backchannel was talked through, and strict pass stayed within one item per run.
- **Cost:** 0.065 USD for the two runs.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | First chunk synthesis median 0.45–0.70 s | Held: 0.58 s |
| 2 | First chunks of 4 characters or fewer: 4 to 12 of 32 | Held: 6 of 32 |
| 3 | First-audio median 3.40–3.95 s, perhaps within run-to-run variation | Held: 3.79 s, a 0.16 s drop against a 0.60 s difference between the two `vad-think` runs |
| 4 | Gaps over 0.3 s after the first chunk: 2 to 8 steps | Held: 3 of 29 |
| 5 | Nothing else changes: 16 of 16 stops at a median 0.24–0.30 s, 0 of 8 backchannels talked through, strict 29 to 33 per run | Held: 16 of 16 at 0.25 s, 0 of 8, strict 29 and 31 |

A two-character opening is a cheap change. In all 7 item-runs where it applied, the first audio came sooner than in the same item and run of `vad-think`. It mostly helps replies that open with 好的 or 抱歉. To shorten the silence after the opening, the rest of the reply would need to be synthesized as its text streams in, not after the text is complete; that was not tested.

### 6.13 Follow-up: confirm before cancelling

In I05 every arm cancelled the meeting before saying a word, so the user's "等一下，先别取消" came too late. Existing practice:
- agent frameworks hold such calls tool by tool (`needs_approval` in the OpenAI Agents SDK, `interrupt_on` in LangChain);
- voice design guidance (Nuance Mix) asks for an explicit yes or no before an action that cannot be undone.

The arm `vad-think-confirm` holds the first `cancel_meeting` call and tells the model to restate the meeting and ask. The call can run only in the next turn, and only if the user has heard the question. The 42 items were written for an agent that does not ask, so four more were written with the user's answer (three yes, one no) and run in both arms. Plan and seven expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A6. Tables: `results/confirm_vs_base.md`.

| | `vad-think` | `vad-think-confirm` |
|---|---|---|
| Strict pass on the 42 items, run1 / run2 | 30 / 31 | 32 / 31 |
| I05 (cancel, then "wait") | failed in both runs: cancelled already | passed in both runs |
| T04 (cancel; the scripted user never answers) | passed in both runs | failed in both runs: the agent asked, the meeting stayed |
| Four items with an answer: right end state | 6 of 8 | 8 of 8 |
| Asked before cancelling | 0 of 8 | 8 of 8 |
| Seconds from the end of the request to the cancel, median | 2.94 | 14.33 |

- **"Wait" now works.** In I05 the agent began to restate the meeting, "等一下，先别取消" cut in, and nothing was cancelled, in both runs. When the user declined (C03), the meeting stayed; without the question it was cancelled before the user spoke, in both runs.
- **The question is slow mostly because it is long.** A cancel took a median 14.3 s instead of 2.9 s:
  - the question began 4.6–5.8 s after the request ended (the cancel itself came 2.6–3.5 s after it without the question);
  - it lasted 4.6–6.5 s, restating date, time and every attendee;
  - then came the user's answer, 0.55–0.68 s of silence and 1.0–1.2 s more to the cancel.
  A shorter question, such as "取消明天下午两点的设计评审？", would save several seconds; not tested.
- **T04 fails because of its script.** Its user never answers, so the agent waited and the meeting stayed. The preregistered attribution labels this MODEL, the first rule that applies.
- **Nothing else moved.** All 16 interruptions stopped (median 0.26 s), and no backchannel was talked through. Calls were held only in T04 and I05.
- **Cost:** 0.065 USD for the 42 items twice, and 0.019 USD for the four items in both arms.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | I05 passes in both runs | Held |
| 2 | T04 fails in both runs | Held |
| 3 | Calls held only in T04 and I05 | Held |
| 4 | Strict pass 29 to 33 per run | Held: 32 and 31 |
| 5 | Four extra items: at least 7 of 8 passed and 8 of 8 asked first; `vad-think` fails C03 twice and asks first in at most 1 of 8 | Held: 8 of 8 and 8 of 8; `vad-think` failed C03 twice and asked first in 0 of 8 |
| 6 | The cancel comes at least 2.0 s later | Held: 14.33 s against 2.94 s |
| 7 | Nothing else changes | Held: 16 of 16 stops at 0.26 s, 0 of 8 backchannels talked through |

Confirming fixes the one failure no listening change could reach, because the cancellation no longer happens before the user can object. The question costs about 11 s per cancel here. A real product would ask more briefly, and would ask only before actions that cannot be undone, as here.

### 6.14 Follow-up: listen only to the first speaker

Background talkers defeat Silero here (section 6.5), and noise suppression would not help, because the noise is speech. FireRedChat's personalized VAD (pVAD; FireRedTeam, Apache-2.0) gives the probability that one particular speaker is talking, once it has that speaker's voice (a 192-value embedding of the first utterance). Its authors built it to "suppress background noise and non-target speakers". The arm `vad-think-pvad` uses it instead of Silero for every listening decision, with the same thresholds; the embedding is set when the first turn ends, as its LiveKit plugin does.

An offline check on rebuilt microphones came first (`results/pvad_offline_check.md`). After the embedding, pVAD marked 0.1% of babble-only frames as speech (Silero 97.8%) and caught 92.8% of the user's later frames on clean items (Silero 96.7%). Plan and eight expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A7. Tables: `results/pvad_vs_base.md`.

| | `vad-think` | `vad-think-pvad` |
|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 32 / 31 |
| Babble: first turn forced at the 20 s cap | 8 of 8 | 0 of 8 |
| Babble: agent cut off mid-reply | 8 of 8 | 0 of 8 |
| Babble: first audio median after the user stops | 20.4 s | 4.56 s |
| Clean tasks: first audio median (p90) | 3.95 s (5.24) | 4.01 s (5.52) |
| Interruptions stopped; stop latency median (max) | 16 of 16; 0.26 s (0.31) | 16 of 16; 0.27 s (0.45) |
| Backchannels talked through | 0 of 8 | 2 of 8 (嗯, both runs) |

- **Background talk no longer runs the conversation.** Every babble turn ended when the user stopped (turn-end wait 0.56 s instead of 15.5 s), and no gap in the babble cut the agent off. The transcripts lost the babble words as well: 「后天杭州会下雨吗？版。」 became 「后天杭州会下雨吗？」, and 「改明天的 review改到下午3点，周版。」 became 「明天的design review改到下午3点。」
- **Babble strict pass fell from 8 to 6, for a reason the clean set already shows.** N06 is a noisy copy of T07, whose 「上午十点」 the recognizer hears as 「上午0点」 in every arm. With Silero, 20 s of babble turned the transcript into 「后天上50点…」, and the meetings ended up at 10:00. With pVAD the transcript is the clean one, with the clean error, and the meeting was set at 00:00 in both runs.
- **Clean speech costs little.** First audio moved by 0.06 s. All 16 interruptions stopped, the slowest after 0.45 s instead of 0.31 s. No turn ended inside a pause (12 of 12, as before).
- **嗯 slipped through.** pVAD did not count the 0.41 s 嗯 (B01) as the user's speech in either run, so the agent talked on; 嗯嗯, 好的 and Okay still stopped it. This comes from a stricter speech detector, not from a backchannel rule.
- **Pink noise: listening got faster, the replies did not.** Turn ends came sooner (0.56 s instead of 1.38 s), but the model's time to the first chunk (3.16 s against 1.97 s) and the first chunk's synthesis (0.90 s against 0.59 s) rose over these 8 item-runs, so first audio went from 4.25 s to 5.03 s. Strict pass stayed at 4 of 8.
- **Cost:** 0.060 USD for the two runs.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Babble: first turn forced at the cap in at most 2 of 8 | Held: 0 of 8 |
| 2 | Babble: cut off mid-reply in at most 2 of 8 | Held: 0 of 8 |
| 3 | Babble: first-audio median under 6 s | Held: 4.56 s |
| 4 | Clean tasks: first-audio median 3.65–4.25 s | Held: 4.01 s |
| 5 | 16 of 16 stops, median 0.20–0.40 s | Held: 16 of 16, 0.27 s |
| 6 | Backchannels talked through: 0 to 2 of 8 | Held: 2 of 8 |
| 7 | Pauses: no speech inside the pause in at least 10 of 12 | Held: 12 of 12 |
| 8 | Strict pass 29 to 34 per run | Held: 32 and 31 |

Following one speaker removes the worst failure in this set: background talk that held every babble turn for 20 s and then cut off the answer. It costs almost nothing on clean speech. It assumes that the first utterance comes from the user. It was tested with one user voice per conversation and synthetic babble; not tested: another real person in the room who speaks first, or a user whose voice changes during the conversation.

### 6.15 Follow-up: the four changes together

The arm `vad-think-combo` combines the four changes that helped, each as tested alone:
- pVAD for all listening (6.14);
- the short first chunk (6.12);
- the confirmation before cancelling (6.13);
- the pause, then the verdict of 6.9 (6.10).

The waiting rules of 6.7 to 6.9 were left out: they make every real stop later, while the pause keeps the fast stop with the same verdict. Plan and eight expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A8. The arm ran twice over the 42 items and twice over the four confirmation items. Tables: `results/combo_vs_base.md`, which also lists each single-change arm.

| | `vad-think` | `vad-think-combo` |
|---|---|---|
| Strict pass, run1 / run2 (of 42) | 30 / 31 | 30 / 32 |
| Clean tasks: first audio median; first chunk synthesis median | 3.95 s; 0.85 s | 3.83 s; 0.57 s |
| Babble: first turn held to the 20 s cap; agent cut off mid-reply | 8 of 8; 8 of 8 | 0 of 8; 0 of 8 |
| Babble: first audio median | 20.4 s | 4.36 s |
| Interruptions stopped; stop latency median (max) | 16 of 16; 0.26 s (0.31) | 16 of 16; 0.25 s (0.36) |
| Reply survived a backchannel (kept talking or resumed) | 0 of 8 | 8 of 8 |
| I05 (cancel, then "wait") | failed twice | passed twice |
| Four confirmation items: right end state; asked first | 6 of 8; 0 of 8 | 8 of 8; 8 of 8 |

- **The effects add up.** Each change kept what it did alone:
  - babble never held a turn or cut off a reply (as with pVAD alone);
  - the first chunk took 0.57 s to synthesize (0.58 s alone);
  - every cancellation was asked first, and I05 passed;
  - no interruption was resumed by mistake.
- **Every reply survived its backchannel, more than any single change managed.** pVAD let 嗯 pass without a pause in both runs. 好的 and Okay paused the agent, which resumed after 0.99 s each time. 嗯嗯 was again read as 「ねなんや？」, but pVAD counted only 0.48 and 0.45 s of voiced time for it, under the 0.5 s line, so the agent resumed after it too (0.99 and 0.90 s). That margin is as thin as the one for 嗯 in 6.9.
- **One new interaction.** In P01 the user pauses after 「帮我约个会，」.
  - pVAD ended that turn 0.13 s sooner, and the short first chunk was ready sooner, so 「好」 began 0.10–0.13 s after the user went on.
  - In every single-change arm the same reply was dropped before it played, and the two halves were heard as one turn. Here the agent paused, the verdict cancelled the reply, and the request became two turns.
  - In run1 the model then asked for a meeting name instead of booking the meeting.
- **The frozen score barely moves.** Pauses count as stops (B02–B04), T04 fails because its script cannot answer the question, N06 fails on the recognition error its clean copy has (6.14), and P01 failed once.
- **Cost:** 0.068 USD for the 42 items twice and the four confirmation items twice.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Babble: at most 2 of 8 held to the cap and at most 2 of 8 cut off; first audio under 6 s | Held: 0, 0, 4.36 s |
| 2 | I05 passes twice, T04 fails twice | Held |
| 3 | 16 of 16 stops, median 0.20–0.40 s, no wrong resumes | Held: 16 of 16, 0.25 s, 0 |
| 4 | The reply survives at least 6 of 8 backchannels | Held: 8 of 8 |
| 5 | First chunk synthesis 0.45–0.70 s; first audio 3.40–4.30 s | Held: 0.57 s; 3.83 s |
| 6 | Confirmation items: at least 7 of 8 right, 8 of 8 asked first | Held: 8 of 8 and 8 of 8 |
| 7 | Pauses: strict pass in at least 10 of 12 | Held: 11 of 12 |
| 8 | Strict pass 30 to 35 per run | Held: 30 and 32 |

Together, the four changes fix the experience problems this evaluation found:
- background talk no longer runs the conversation;
- a real interruption stops the agent in a quarter of a second;
- a backchannel no longer loses the reply;
- "wait" can still stop a cancellation.

The price is about 11 s more per cancellation, and one new way for a paused request to split into two turns. The frozen strict score was written before these fixes existed, and it scores a pause as a stop and expects T04 to cancel without asking. Under it the combined arm is level with the baseline; on the problems the changes target, it is the best arm tested.

### 6.16 Follow-up: a brief confirmation question

The confirmation of 6.13 and 6.15 restated date, time and every attendee, so a cancel came a median 14 s after the request. Bixby's design guide asks for "a brief and direct question" at a confirmation moment. The arm `vad-think-combo-brief` is `vad-think-combo` with one change: when the cancel is held, the model is asked for one very short question with the meeting's date, time and title only, and given an example (「取消明天下午两点的设计评审吗？」). Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A9. Tables: `results/followups_vs_combo.md`.

The second run stopped after 10 items. It was resumed two hours later with unchanged files, and the 10 completed items were kept. Their token use, which the interrupted run had not written out, was added back from the per-call counts in their traces.

| | `vad-think-combo` | `vad-think-combo-brief` |
|---|---|---|
| Confirmation items: question length, median | 5.03 s | 2.81 s |
| Confirmation items: request to cancel, median | 14.18 s | 11.40 s |
| Confirmation items: right end state; asked first | 8 of 8; 8 of 8 | 8 of 8; 8 of 8 |
| Strict pass, run1 / run2 (of 42) | 30 / 32 | 33 / 31 |

- **The question halved, and every cancel was still asked first.** The cancel came 2.8 s sooner. It still came 8.5 s later than with no question at all (2.94 s, 6.13): the extra model step, the user's answer and one more turn remain.
- **Nothing else moved.** Babble never held a turn or cut a reply, all 16 interruptions stopped (median 0.27 s), and every reply survived its backchannel. I05 passed in both runs; T04 failed in both, for the reason in 6.13. Pause items were split into two turns in 2 of 12 item-runs (4 of 12 in 6.15). That is the same race seen in 6.15, and it varies with timing.
- **Cost:** 0.068 USD.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Question length median at most 3.0 s | Held: 2.81 s |
| 2 | Request to cancel 9.5–12.0 s | Held: 11.40 s |
| 3 | At least 7 of 8 right, 8 of 8 asked first | Held: 8 of 8, 8 of 8 |
| 4 | I05 passes twice, T04 fails twice | Held |
| 5 | Everything else as in A8 (babble, 16 of 16 stops at 0.20–0.40 s, at least 6 of 8 replies surviving, strict 29 to 34) | Held: 0 and 0 of 8, 16 of 16 at 0.27 s, 8 of 8, strict 33 and 31 |

### 6.17 Follow-up: keep a turn whole when the user spoke first

In 6.15 a pause item split into two turns when the user went on just before the agent's short first chunk began. A voice-activity onset is confirmed 0.2 s after speech starts, so by then the reply had begun, and it was treated as heard and interrupted. In every arm without the short chunk and pVAD, the same reply was dropped before it played, and the turn stayed whole (D-V11). The arm `vad-think-combo-merge` is `vad-think-combo` plus one rule: if the speech that interrupts a reply started before that reply's first sound, the reply is dropped as unheard and the turn goes on as one. Plan and four expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A10. Tables: `results/followups_vs_combo.md`.

| Pause items, run1 + run2 | `vad-think-combo` | `vad-think-combo-merge` |
|---|---|---|
| Agent audio started while the user went on | 4 of 12 | 1 of 12 |
| Continuation became its own turn | 4 of 12 | 0 of 12 |
| Strict pass | 11 of 12 | 12 of 12 |

- **When the race happened, the turn stayed whole.** It happened once in these runs (P06, run1), against 4 times in 6.15 and twice in 6.16; how often it happens depends on timing. The rule dropped the barely started reply, and the recognizer heard the request as one sentence, 「帮我查一下singapore后天的天气。」, which was answered correctly.
- **The evidence is mostly the offline test.** One live occurrence is little. The offline test rebuilds the P01 race, with the reply's text finishing either before or after the verdict, and the rule keeps the turn whole in both cases, while `vad-think-combo` splits it.
- **The rule fired nowhere else.** It cannot fire on a real interruption, which always starts after the reply's first sound. All 16 interruptions stopped (median 0.25 s), babble never held a turn or cut a reply, I05 passed and T04 failed in both runs, and strict pass was 32 and 31.
- **One backchannel reply was lost, by the margin seen before.** In run1, 嗯嗯 (B02) got 0.51 s of voiced time against the 0.5 s line and cancelled the reply; in run2 it got 0.48 s and the reply resumed.
- **Cost:** 0.058 USD.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Pause items: continuation its own turn in at most 1 of 12 | Held: 0 of 12 |
| 2 | The rule fires only on pause items | Held: once, on P06 |
| 3 | Pause items: strict pass in at least 11 of 12 | Held: 12 of 12 |
| 4 | Everything else as in A8 (babble, 16 of 16 stops at 0.20–0.40 s, at least 6 of 8 replies surviving, I05 and T04, strict 30 to 35) | Held: 0 and 0 of 8, 16 of 16 at 0.25 s, 7 of 8, I05 passed and T04 failed twice, strict 32 and 31 |

### 6.18 Follow-up: synthesize each chunk as its text streams in

Until this section, the simulation cut only the first speech chunk from the model's stream. Later chunks were synthesized once the whole reply text was complete. Pipecat and LiveKit instead hand their speech engines one sentence at a time as the text streams. The arm `vad-think-combo-stream` is `vad-think-combo` with that change: each later chunk is synthesized as soon as its own text is in. Plan and six expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A11. Tables: `results/followups_vs_combo.md`.

| Clean task items, first spoken reply step | `vad-think-combo` | `vad-think-combo-stream` |
|---|---|---|
| Silence inside the step, p90 | 0.27 s | 0.15 s |
| Gaps over 0.3 s after the first chunk (longest) | 3 of 30 (0.49 s) | 2 of 31 (0.64 s) |
| End of the step after the request, median | 9.28 s | 9.44 s |
| Steps where the streamed chunk ends did not match the final text | 0 of 112 | 0 of 112 |

- **Streaming removed most silences, but not the longest one.** Both remaining gaps are T13, in both runs. 「好的，」 plays for 0.55 s, and the next chunk, 「已设置明天上午9点提醒你提交报告。」, takes 1.18 s to synthesize. Its text was already in, so waiting for text was not the problem; the speech engine is. A shorter second chunk, or an engine that streams its own audio, would close that gap; neither was tested.
- **The end of a reply barely moves.** Synthesis here is faster than playback, and the text usually streams in long before it is needed.
- **One interruption could not be scored.** In I07 (run2) the user started speaking at 10.549 s, inside a 0.10 s gap between two chunks, 「请再确认一下：」 and 「是和」. The frozen rule does not count that moment as the agent talking, so the item has no stop measure. The agent stopped after 「是和」. The other 15 interruptions stopped, with a median of 0.27 s.
- **Nothing else moved.** Babble never held a turn or cut a reply, every reply survived its backchannel, I05 passed and T04 failed in both runs, and strict pass was 30 and 32. Pause items split into two turns in 4 of 12 item-runs, as in 6.15; this arm does not have the guard of 6.17.
- **Cost:** 0.058 USD.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Gaps over 0.3 s after the first chunk: at most 1 | Not held: 2 of 31, both T13 (see above) |
| 2 | Silence inside the step, p90 at most 0.15 s | Held: 0.15 s |
| 3 | End of the step after the request: median 8.8–9.6 s | Held: 9.44 s |
| 4 | Steps falling back to the old rule: at most 5% | Held: 0 of 112 |
| 5 | Clean tasks: first audio median 3.5–4.2 s | Held: 3.87 s |
| 6 | Everything else as in A8 (babble, 16 of 16 stops at 0.20–0.40 s, at least 6 of 8 replies surviving, I05 and T04, strict 30 to 35) | Held in part: babble 0 and 0 of 8, 8 of 8 replies, I05 and T04 as expected, strict 30 and 32; stops 15 of 15 at 0.27 s, one interruption not scorable (I07, run2) |

### 6.19 Follow-up: disfluent requests and new voices

The 42 items are fluent and use seven voices. Fourteen more items were written with their answers before any run (addendum A12), all in voices the 42 do not use:
- ten disfluent requests, built from the three types of LARD (repetitions, replacements, restarts) plus fillers;
- four clean requests, copied word for word from T01, T02, T05 and T11.

Two items were changed before any run, because both recognizers misheard a keyword in their synthesized audio. The speech engine renders 「……」 as at most 0.26 s of silence, so these items test disfluent wording, not long hesitations; the pause items cover those. `vad-think`, `vad-think-combo` and the text-only control ran twice each. Table: `results/disfluent_vs_base.md`.

| | `vad-think` | `vad-think-combo` | text only |
|---|---|---|---|
| Disfluent items passed, run1 / run2 (of 10) | 8 / 9 | 9 / 8 | 10 / 10 |
| New-voice items passed (of 8 item-runs) | 8 | 8 | 8 |
| Turn ends inside a request (of 28 item-runs) | 0 | 0 | — |

- **The model copes with disfluent wording.** From the text, all ten disfluent items were right in both runs. From audio, the recognizer kept the repetitions and corrections (「帮我渣查查…」, 「帮我预张维不对，约李娜…」), and the model still did the right thing in most of them.
- **A filler written as a character changed the meaning.**
  - In D06 (「明天早上八点，呃，八点半…」) the recognizer wrote 「8点鄂8点半」. The model read it as 8:00 to 8:30 and set the reminder at 8:00 (run1, both arms), or asked again instead of acting (run2, both arms). None of the four audio item-runs set 8:30, which the text-only control set both times.
  - In D04 a pause became 「已」 (「明天的那个已算了…」). Twice the model asked whether 「算了」 meant cancelling instead of moving the meeting.
- **New voices did not change the result.** The four copied items passed in all 8 item-runs, as their sources did in the original voices.
- **Run note.** The first run of `vad-think` stopped after 10 items. It was resumed with unchanged files, and the token use of the 10 completed items was added back from their traces, as in 6.16.
- **Cost:** 0.047 USD for the three arms.

| # | Expectation written before these items ran | Result |
|---|---|---|
| 1 | Text-only control: at least 12 of 14 per run | Held: 14 and 14 |
| 2 | `vad-think`: at least 6 of the 10 disfluent items per run | Held: 8 and 9 |
| 3 | `vad-think`: at least 7 of the 8 new-voice item-runs | Held: 8 of 8 |
| 4 | Turn ends inside a request: at most 1 of 28 per audio arm | Held: 0 and 0 |
| 5 | `vad-think-combo` within 2 items of `vad-think` per run | Held: 13 and 12 against 12 and 13 |

### 6.20 Offline check: do spoken confirmations match what the tools did?

When the agent changes data it says so, for example 「已设置提醒：明天上午9点…」. This check asks whether those words match the tool calls behind them. It uses evidence-check (section 12), whose script compares dates, times and numbers across languages and formats (上午9点, 9:00, 9 a.m.).
- **What is checked:** for every reply in which a data-changing tool succeeded, the words the user heard after the last such call.
- **Against what:** a record of the tool calls; durations are first written in minutes, because the script does not convert hours.
- **Which runs:** all saved runs, no model calls.

Rules: `eval/confirm_consistency.py`. Tables: `results/confirm_consistency.md`.

The record defined first contained only the reply's data-changing calls, and that turned out too narrow: confirmations also state facts the agent looked up earlier, such as the old time of a meeting it moved. A second record, every tool call of the conversation so far, was added after seeing the first count. Both are reported, and every flag left under the second record was read and given one category; those categories were written after reading.

| 42 items, every arm, run1 + run2 | |
|---|---|
| Confirmations; with a number | 684; 632 |
| Consistent, record = the reply's changes (rule fixed first) | 414 (66%) |
| Consistent, record = all tool calls so far | 564 (89%) |
| Of the other 68: end times (a start plus a duration) | 8 |
| Clock times the script reads without their 上午 or 下午 (「10点改到11点」, one 下午 for two times) | 29 |
| Counts read as numbers (一次, 一场) | 4 |
| Cut off mid-number by an interruption, not rated | 4 |
| The agent said something the tools did not do | 23 |

- **The words match, with one repeated slip.** After reading every flag, 605 of 628 rated confirmations were consistent (96%). All 23 others are the same slip, in T07, T09, T14 and N06, across arms and runs. The user asked for a half-hour meeting (「开个半小时的会」, 「半小时」, 「半个小时」). The agent booked 30 minutes, but its confirmation said 「一个半小时」 (90 minutes) first, then corrected itself (「……不对，是半小时」) or contradicted itself (「一个半小时的会，也就是30分钟」). The booking was right; what the user heard first was not.
- **The extra item sets are clean.** All 27 confirmations on the four confirmation items and all 32 on the disfluent and new-voice items were consistent once the script's reading limits were set aside.
- **Limits.** Only numbers are checked; names and titles are not. Confirmations with no number (52 of 684) are counted but not rated. Not measured: a confirmation of something no tool did (NOT RUN). Consistency is not correctness: T07's meeting booked at 00:00 after a recognition error is consistently confirmed as 00:00.

The table file now also contains the arm and the repeats of section 6.21, and its 'all' rows include them; the numbers above are for the arms before it.

### 6.21 Follow-up: say meeting durations in minutes

The slip found in 6.20 comes from the wording of the request. 「开个半小时的会」 means "hold a half-hour meeting", with 个 counting the meeting. The model wrote it as 「开一个半小时的会」, which a listener can only hear as 「一个半小时」, an hour and a half. Some guides add instructions to the system prompt so the model writes its text in a speakable form (ElevenLabs' default); others rewrite the text before synthesis (ElevenLabs' normalizer, LiveKit's `tts_node`). A normalizer does not help here, because the phrase has no digits or symbols to convert. A rewrite would leave the model's own correction behind it. The arm `vad-think-combo-minutes` is `vad-think-combo` plus one rule at the end of the system prompt: say a meeting's duration as the number of minutes passed to the tool (「30分钟」), not as 「半小时」 or 「一个半小时」. Every other arm keeps the old prompt byte for byte. Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A13. Tables: `results/minutes_vs_combo.md` and `results/followups_vs_combo.md`.

Besides the two runs of the 42 items, the four items with the slip (T07, N06, T09, T14) were run five more times for both arms, because two runs give only 8 chances per arm.

| | `vad-think-combo` | `vad-think-combo-minutes` |
|---|---|---|
| Item-runs with the slip, 42 items × 2 | 4 of 84 (all on the four items) | 0 of 84 |
| Item-runs with the slip, the four items × 5 more | 5 of 20 | 0 of 20 |
| Reply texts with a duration said in minutes only, 42 items × 2 | 13 of 48 (27%) | 43 of 46 (93%) |
| Spoken confirmations consistent with all tool calls so far (6.20, record B), 42 items × 2 | 37 of 44 (84%) | 45 of 46 (98%) |
| Strict pass, run1 / run2 | 30 / 32 | 31 / 32 |

- **The slip is gone.** Across 104 item-runs the new arm never said 「一个半小时」 for a half-hour meeting, while the old arm did in 9 of 28 on the same four items. It now says 「开一个30分钟的会议」 or 「时长30分钟」. Every meeting either arm booked in the repeats was 30 minutes, as before: the slip was only in what the user heard.
- **The rule is followed, not perfectly.** Three texts still say hours. Two say 「推迟一小时」, a shift rather than a duration, which the rule does not cover. One, a question before booking in N04 (run2), says 「明天下午4点半小时的会议」. A listener can hear that as 4:30, the same kind of ambiguity in another place. It is not a slip by the preregistered rule, which counts only 「一个半小时」.
- **The confirmation check agrees.** Under record B, the one flag left for the new arm is a clock time the script cannot read (「10点改到11点」, 6.20). On the repeats, the old arm's confirmations were consistent 15 of 20 times and the new arm's 20 of 20.
- **The task results do not change.** The four items pass or fail exactly as before (T14 passes every time; T07, N06 and T09 fail on recognition: 十点 heard as 0点, and 「两点，半个小时」 heard without its pause, so 2:30 was booked). The rule changes how a booking is said, not what is booked.
- **Cost:** 0.059 USD for the two runs and 0.026 USD for the repeats.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | No slip in any item-run of the new arm (84 + 20) | Held: 0 of 104 |
| 2 | `vad-think-combo` slips in at least 3 of its 20 repeats | Held: 5 of 20 |
| 3 | At least 80% of the new arm's texts with a duration say it in minutes only | Held: 93% (43 of 46) |
| 4 | No "misspoken duration" flag for the new arm in the confirmation check | Held: 0 |
| 5 | Everything else as in A8 (strict 30 to 35, first-audio median 3.5–4.2 s, babble, 16 of 16 stops at 0.20–0.40 s, at least 6 of 8 replies surviving, I05 and T04) | Held in part: strict 31 and 32, babble 0 and 0 of 8, 16 of 16 stops at a median of 0.27 s, 8 of 8 replies, I05 and T04 as expected. First-audio median 3.44 s, just below the range. That is faster, not slower, and smaller than the 0.60 s seen between two runs of the same arm (summary, point 3) |

### 6.22 Follow-up: the four follow-ups together

Sections 6.16 to 6.18 and 6.21 each tested one change on top of `vad-think-combo`. The arm `vad-think-combo-plus` has all four: the brief confirmation question, keeping a turn whole when the user spoke first, synthesizing later chunks as their text streams in, and durations in minutes. A test checks that it is exactly `vad-think-combo` plus those four switches. Plan and five expectations: [`PREREGISTRATION.md`](PREREGISTRATION.md) addendum A14. Tables: `results/followups_vs_combo.md`, `results/minutes_vs_combo.md` and `results/confirm_consistency.md`.

| | `vad-think-combo` | The change alone | `vad-think-combo-plus` |
|---|---|---|---|
| Confirmation items: question length, median | 5.03 s | 2.81 s (6.16) | 2.83 s |
| Confirmation items: cancel time, median | 14.18 s | 11.40 s (6.16) | 10.86 s |
| Pause items: continuation became its own turn | 4 of 12 | 0 of 12 (6.17) | 0 of 12 |
| Clean tasks: silence inside the first spoken reply step, p90 | 0.27 s | 0.15 s (6.18) | 0.66 s |
| Item-runs announcing 「一个半小时」 for a shorter meeting | 4 of 84 | 0 of 84 (6.21) | 0 of 84 |
| Reply texts with a duration said in minutes only | 27% | 93% (6.21) | 94% |
| Strict pass, run1 / run2 | 30 / 32 | 30 to 33 | 31 / 32 |

- **Three of the four kept their gain.** The question stayed short, and every cancel was still asked first (8 of 8, right end state 8 of 8). Every pause item stayed one turn and passed (12 of 12). No meeting was announced as 「一个半小时」.
- **Streaming did not show its gain.** Silences over 0.3 s came in T13, in both runs as in 6.18, and now also in T06, in both runs (0.71 and 0.76 s). In T06 the model opened with a short clause, 「已设置提醒，」. The next chunk, the whole reminder, took longer to synthesize than the opening took to play. In 6.18 the same item opened with the reminder itself, so there was no gap. Streaming removes the wait for text, not the time synthesis takes. Its own check held: the streamed chunk ends matched the final text in 112 of 112 steps.
- **The merge rule fired in 7 of 12 pause item-runs, against once in 6.17.** In this run the agent's first sound often came just after the user went on. Every time, the turn stayed whole and the item passed. But the reply had already started when the onset was confirmed, so the user heard 0.05 to 0.22 s of it, at most one syllable such as 「好」. Overlap of this kind happened in 7 of 12 item-runs: 4 in `vad-think-combo`, 1 in 6.17. It depends on when the model's reply lands, which varies from run to run. Avoiding it would mean holding back every reply's first sound.
- **Nothing else moved.** Babble never held a turn or cut a reply. 16 of 16 interruptions stopped, with a median of 0.28 s; the slowest was I08 in run2 at 0.59 s. Every reply survived its backchannel. I05 passed and T04 failed in both runs. First-audio median was 3.75 s. The confirmation check found no misspoken duration (44 of 45 consistent; the one flag is a clock time the script cannot read).
- **Cost:** 0.069 USD.

| # | Expectation written before this arm ran | Result |
|---|---|---|
| 1 | Confirmation items: question at most 3.0 s, cancel 9.5–12.0 s, at least 7 of 8 right, 8 of 8 asked first | Held: 2.83 s, 10.86 s, 8 of 8, 8 of 8 |
| 2 | Pause items: at most 1 of 12 split into two turns, at least 11 of 12 pass | Held: 0 of 12, 12 of 12 |
| 3 | Silence inside the first reply step: p90 at most 0.20 s; at most 5% of steps falling back | Half held: no fallback (0 of 112), but p90 0.66 s, from T06 and T13 (see above) |
| 4 | No 「一个半小时」 slip; at least 80% of duration texts in minutes only | Held: 0 of 84, 94% |
| 5 | Everything else as in A8 (strict 31 to 35, first-audio median 3.4–4.2 s, babble, at least 15 of 16 stops at 0.20–0.40 s, at least 6 of 8 replies surviving, I05 and T04) | Held: strict 31 and 32, 3.75 s, babble 0 and 0 of 8, 16 of 16 at 0.28 s, 8 of 8, I05 and T04 as expected |

## 7. Negative cases and attribution

Every strict failure was labelled by the preregistered rules and then read. Reading changed four labels: T09 and I07 (rule: MODEL, because the key words listed for them were present) are recognition errors, since the text-only control passes both and the transcript lost a pause or a time; I03 (rule: BARGE-IN, from "quiet after stop") is the model talking too long after "不用说了"; I07 in one `smart` run (rule: COMMITTED) is a recognition error that produced a wrong meeting before the interruption.

| Cause after reading | `vad` | `smart` | `vad-think` | Items |
|---|---|---|---|---|
| Recognition (names, times, a lost pause, noise) | 12 | 10 | 12 | T07, T09, T14, I07, N03, N04 |
| Stopped on a backchannel | 8 | 8 | 8 | B01–B04 |
| Change made before the user could stop it | 2 | 2 | 2 | I05 |
| Background speech: 20 s turns and a false barge-in | 2 | 3 | 0 | N05, N06 |
| Turn ended inside a pause, agent spoke | 0 | 2 | 0 | P03, P05 |
| Talked too long after "stop" | 1 | 0 | 1 | I03 |
| **Total strict failures** | **25** | **25** | **23** | |

Three cases worth describing:

- **I05, "帮我取消明天的周会" … "等一下，先别取消"**: the agent looked up and cancelled the meeting before its answer began (before any audio in 5 of 6 item-runs), so the user's "wait" 0.8 s into the answer came after the fact; in one run the agent then offered to re-create it. The text-only control fails the same way. A product fix is a confirmation step, or a short undo window, for destructive actions.
- **I07**: the transcript "帮我约M后，天上51点开会半小时" lost the name and the time. With thinking off the agent started to explain the misrecognition aloud ("这句话里'M后'应该是'Emma'的误识别"), was interrupted with "改成 one hour", and then switched to English and asked which meeting to change. In one `smart` run it guessed "Emma Smith tomorrow at 5 PM" and created that meeting.
- **B03**: "后天有什么安排？" … the agent says "后天，也就是11月18日，" … user: "好的。" The agent stops within 0.4 s, hears "好的。" as a new turn, and answers it, so the user hears a fragment and then the answer restarted. B02 is worse: 嗯嗯 becomes "ねなや？" and, with thinking on, the agent continues in Japanese.

## 8. Expectations written before the run

| # | Expectation | Result |
|---|---|---|
| 1 | `vad`: early turn end in all 6 pauses; audible takeover in at most 2 of 6; pause items still pass | Held: 12/12 early, 0 audible, 12/12 pass |
| 2 | `smart`: fewer early turn ends, higher median latency | Half held: 6/12 early turn ends; the median was lower (2.80 vs 2.94 s), only the 90th percentile was higher (5.47 vs 3.49 s). Not predicted: it was the only arm to talk into a pause |
| 3 | `vad-think`: higher first-audio latency, less reasoning aloud | Held: +1.0 s, 0 vs 23 item-runs. Not predicted: the answer itself came 1.9 s sooner |
| 4 | Backchannels stop the agent at least 3 of 4 times | Held: 8 of 8 in every arm |
| 5 | Babble runs to the 20 s cap (>15 s); pink noise close to clean | Held for babble (18.6–20.4 s). Pink: one item of four flipped in two arms. Not predicted: a false barge-in in 23 of 24 babble item-runs |
| 6 | Stop latency about 0.2–0.35 s | Held for the medians (0.25–0.26 s); the maximum was 0.47 s |
| 7 | Text-only ≥ 90% on clean tasks; clean-task audio failures mostly recognition | Held: 32/32; all clean-task audio failures (T07, T09, T14) are recognition |
| 8 | I05 fails in every arm | Held, text-only included |

## 9. Limitations

- **Synthetic users.** One synthesis model, fourteen voices (seven of them added in section 6.19), read speech with inserted pauses. Fillers, repetitions and self-corrections exist only as synthesized text (section 6.19); there are no real recordings (FDB v3 uses real disfluent recordings for this reason). Code-switched names were spoken by Chinese voices, which is part of why "Tom" became 汤.
- **Simulated time.** Perfect echo cancellation and an instant stop are assumed; real playback buffers add delay. Local speech times come from a calibration (section 5), not from this run.
- **Small and repeated.** 42 items, two runs; one item flipping is noise. Interruption and backchannel moments are fixed offsets into the answer.
- **One machine, one network.** Model latency includes the network path from this machine to the API, and the API was shared with other jobs on the same account during the run (rate-limit retries were excluded from timings).
- **Construction.** Items, answers and the agent prompt were written by the same author; two items were rephrased after the recognizer check and before any agent run.
- **No end-to-end model yet.** No realtime speech-to-speech model was run.

## 10. Next steps

1. Run one end-to-end realtime model on the same 42 items for a direct comparison (Gemini Live free tier first; OpenAI Realtime needs a paid account).
2. The three fixes this run pointed to have been tested against the same items: a short first speech chunk (section 6.12), a confirmation before cancelling (section 6.13) and voice activity that follows one speaker (section 6.14), and together with the pause of 6.10 (section 6.15). A shorter confirmation question has been tested too (section 6.16). So have a guard against the turn split seen in P01 in 6.15 (section 6.17) and synthesizing each chunk as its text streams in (section 6.18). Disfluent requests and new voices have been tested (section 6.19). Still open: closing the gap when a short opening is followed by a long chunk (6.18); and real recorded speech (the HumDial data needs registration). The 「一个半小时」 slip found in 6.20 has a tested fix (section 6.21), and the follow-ups of 6.16 to 6.18 and 6.21 have been tested together (section 6.22). The backchannel filter has been tested (sections 6.7 to 6.11); what is left is at the end of 6.10 and in 6.11.
3. Disfluent speech and more voices: done with synthesized speech (section 6.19). Real recordings are still open (item 2).

## 11. Reproduce

From the project root with the project's Python environment: `python -X utf8 eval/build_audio.py`, `python -X utf8 eval/asr_check.py --whisper`, then for each arm and run `python -X utf8 eval/run.py --arm <arm> --tag <run>` (needs an API key file named by `VOICE_EVAL_ENV_FILE`), then `python -X utf8 eval/score.py results/run1 results/run2` and `python -X utf8 eval/tables.py`; for sections 6.7 to 6.10, `--arm vad-think-words`, `--arm vad-think-words-lang`, `--arm vad-think-words-dur` and `--arm vad-think-pause` for both runs, then `python -X utf8 eval/compare_words.py` with no flag, `--lang`, `--dur` and `--pause`; for section 6.12, `--arm vad-think-short` for both runs, then `python -X utf8 eval/compare_short.py`; for section 6.14, `eval/pvad_enroll.py` in an environment with SpeechBrain (it writes `eval/pvad_enroll.json`), `eval/pvad_offline_check.py`, then `--arm vad-think-pvad` for both runs and `python -X utf8 eval/compare_pvad.py`; for section 6.15, `eval/pvad_enroll.py --add confirm_cases`, then `--arm vad-think-combo` for both runs and with `--cases eval/confirm_cases.json` for `confirm1` and `confirm2`, then `python -X utf8 eval/compare_combo.py`; for section 6.16, `--arm vad-think-combo-brief` on both item sets as for 6.15, then `python -X utf8 eval/compare_followups.py vad-think-combo-brief`; for section 6.17, `--arm vad-think-combo-merge` for both runs of the 42 items, then `python -X utf8 eval/compare_followups.py vad-think-combo-brief vad-think-combo-merge`; for section 6.18, `--arm vad-think-combo-stream` for both runs, then `python -X utf8 eval/compare_followups.py vad-think-combo-brief vad-think-combo-merge vad-think-combo-stream`; for section 6.19, `build_audio.py eval/disfluent_cases.json`, `pvad_enroll.py --add disfluent_cases`, then `vad-think`, `vad-think-combo` and `oracle` with `--cases eval/disfluent_cases.json` and tags `dis1` and `dis2`, `score.py --cases eval/disfluent_cases.json eval/results/dis1 eval/results/dis2` and `python -X utf8 eval/compare_disfluent.py`; for section 6.20, `python -X utf8 eval/confirm_consistency.py` (no model calls; needs the evidence-check repository next to this one); for section 6.21, `--arm vad-think-combo-minutes` for both runs, then `vad-think-combo` and `vad-think-combo-minutes` with `--items T07,N06,T09,T14` and tags `min1` to `min5`, `score.py` on each of those folders, `python -X utf8 eval/compare_minutes.py`, `compare_followups.py` with `vad-think-combo-minutes` added, and `confirm_consistency.py` again; for section 6.22, `--arm vad-think-combo-plus` on both item sets as for 6.15, then `compare_followups.py` and `compare_minutes.py` with `vad-think-combo-plus` added, and `confirm_consistency.py` again; for section 6.13, `--arm vad-think-confirm` for both runs, then both `vad-think` and `vad-think-confirm` with `--cases eval/confirm_cases.json` and tags `confirm1` and `confirm2` (after `build_audio.py eval/confirm_cases.json`), `score.py --cases eval/confirm_cases.json eval/results/confirm1 eval/results/confirm2` and `python -X utf8 eval/compare_confirm.py`. For section 6.11, `eval/bcdet_offline_check.py` runs in a separate environment with MaAI 0.2.27 installed (it reads the recordings that `run.py --save-audio` keeps). Offline tests: `python -X utf8 -m unittest discover -s tests`. Cost of the scored runs: 0.26 USD (2.1 million input and 86,000 output tokens on `claude-haiku-5-5`); sections 6.7 to 6.10 and 6.12 to 6.15 added 0.064, 0.063, 0.062, 0.063, 0.065, 0.084, 0.060 and 0.068 USD; section 6.16 0.068 USD; section 6.17 0.058 USD; section 6.18 0.058 USD; section 6.19 0.047 USD; section 6.21 0.085 USD; section 6.22 0.069 USD.

## 12. Place in the portfolio

This evaluation is the interaction case in a small portfolio built around one idea: an AI system should show its evidence. The other cases cover answering from documents, judging and generating. Two things are shared across them:
- **The method.** Items, answers and scoring rules are written before anything runs (here, `PREREGISTRATION.md` and its addenda). Each change is retested on the same items, and every change in a score is explained, including the expectations that did not hold.
- **One checking component, [evidence-check](https://github.com/Jason-d-e/evidence-check)** (MIT). It checks that what an AI states is backed by a source, quote for quote and number for number. Here it checks the agent's spoken confirmations against the record of its tool calls (section 6.20).
