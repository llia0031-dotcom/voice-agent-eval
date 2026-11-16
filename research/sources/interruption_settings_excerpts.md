# Interruption settings: saved excerpts (fetched 2026-11-13)

## LiveKit Agents, turn handling options (https://docs.livekit.io/reference/agents/turn-handling-options.md)

        "min_duration": 0.5,
        "min_words": 0,
        "discard_audio_if_uninterruptible": True,
        "false_interruption_timeout": 2.0,
        "resume_false_interruption": True,
    },

- **`min_words`** _(int)_ (optional) - Default: `0`: Minimum number of words to be considered as an interruption. Only used if STT is enabled. Set to a value greater than `0` to require actual speech content before triggering interruptions.

- **`resume_false_interruption`** _(bool)_ (optional) - Default: `True`: Whether to resume the agent's speech after a false interruption is detected. When `True`, the agent continues speaking from where it left off after the `false_interruption_timeout` period has passed with no user transcription. To learn more, see [False interruptions](https://docs.livekit.io/agents/logic/turns.md#false-interruptions).

## LiveKit, adaptive interruption handling (https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling.md)

40:- Your agent is [deployed to LiveKit Cloud](https://docs.livekit.io/agents/deploy.md), or running in dev mode with LiveKit Cloud credentials.

## LiveKit issue 4450 'Ignore Filler Words During Interruption Detection'

state=closed state_reason=not_planned closed_at=2026-08-11T00:14:54Z

## Pipecat, user turn strategies (https://docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies.md)

### MinWordsUserTurnStartStrategy

Requires the user to speak a minimum number of words before triggering a turn start. This is useful for preventing brief utterances like "okay" or "yeah" from triggering responses.

**min\_words** `int` *required*

Minimum number of spoken words required to trigger the start of a user turn.

**use\_interim** `bool` (default: True)

Whether to consider interim transcription frames for earlier detection.

```python theme={null}
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy

# Require at least 3 words to start a turn
strategy = MinWordsUserTurnStartStrategy(min_words=3)
```

> [!NOTE]
>
> When the bot is not speaking, this strategy will trigger after just 1 word.
> The `min_words` threshold only applies when the bot is actively speaking,
> preventing short affirmations from interrupting the bot. A shorter transcript
> while the bot is speaking is discarded, so it doesn't reach the context.

Uses Krisp's Interruption Prediction (IP) model to distinguish genuine user interruptions from backchannels (e.g., "uh-huh", "yeah"). When VAD detects user speech, this strategy feeds audio frames into the Krisp VIVA IP model, which outputs a probability indicating whether the speech is a genuine interruption. While the bot is speaking, a user turn is triggered only when this probability exceeds t

This strategy is designed to work alongside other start strategies (e.g., `TranscriptionUserTurnStartStrategy` as a fallback).

## Repositories (GitHub API, 2026-11-13)

- pipecat-ai/pipecat: 17232 stars, BSD-2-Clause
- livekit/agents: 15207 stars, Apache-2.0
- inokoj/VAP-Realtime: 114 stars, MIT
- huggingface.co/bnovikov/bargein-classifier: license cc-by-4.0, language en, 6 likes, onnxruntime

## LiveKit, min_duration (same page as above)

- **`min_duration`** _(float)_ (optional) - Default: `0.5 seconds`: Minimum duration of speech to be considered as an interruption. Helps filter out brief sounds or noise that shouldn't trigger interruptions. Python uses seconds (for example, `0.5`); Node.js uses milliseconds (for example, `500`).

## LiveKit, false interruptions (fetched 2026-11-14)

Docs: https://docs.livekit.io/agents/logic/turns.md, section "False interruptions":

> In some cases, the framework detects human speech audio and interrupts the agent, but the transcription comes up empty as no actual words are spoken. In these cases, the VAD-based interruption is considered a false positive. By default, the agent resumes speaking from where it left off after a false interruption. You can configure this behavior using the `resume_false_interruption` and `false_interruption_timeout` parameters.
> 
> - `false_interruption_timeout`: If an interruption is detected, but the user is silent, this is the duration of silence to wait after an interruption before emitting an `agent_false_interruption` event. Python uses seconds (for example, `2.0`); Node.js uses milliseconds (for example, `2000`).
> - `resume_false_interruption`: Whether to resume the agent's speech after a false interruption is detected. If `True`, the agent continues speaking from where it left off after the `false_interruption_timeout` period has passed with no user transcription.

Source: livekit/agents main at commit 3e5156882414 (15214 stars, Apache-2.0, GitHub API 2026-11-14), file livekit-agents/livekit/agents/voice/agent_activity.py.

Speech heard while the agent talks pauses the audio instead of cancelling the reply (`_interrupt_by_audio_activity`):

```python
            if self._pause_enabled():
                timeout = interruption_options["false_interruption_timeout"]
                assert timeout is not None
                audio_output = self._session.output.audio
                assert audio_output is not None

                # EOS arms false-interruption resume. A final transcript or a
                # replying turn commit interrupts the paused handle.
                self._update_paused_speech(self._current_speech, timeout)
                audio_output.pause()
                self._session._update_agent_state("listening")
                self._on_end_of_agent_speech(ended_at=time.time())
```

Voice activity reaching `min_duration` triggers that pause (`on_vad_inference_done`):

```python
        active_speech = ev.speech_duration >= self._session.options.interruption["min_duration"]
        if active_speech and (
            self._turn_detection != "stt"
            or not self._stt_eos_received
            or ev.raw_accumulated_silence == 0
        ):
            # STT may send EOS before VAD EOS, we only interrupt if:
            # 1. turn detection is not STT; or
            # 2. STT EOS hasn't been received yet; or
            # 3. VAD speech is still ongoing
            self._interrupt_by_audio_activity()
```

End of the user's speech starts the resume timer (`on_end_of_speech`):

```python
        if self._paused_speech:
            self._start_false_interruption_timer(self._paused_speech.timeout)
```

A final transcript ends the pause by interrupting the reply (`on_final_transcript` -> `_cancel_speech_pause`):

```python
        self._cancel_speech_pause_task = asyncio.create_task(
            self._cancel_speech_pause(old_task=self._cancel_speech_pause_task)
        )

        if (
            interrupt
            and not self._paused_speech.handle.interrupted
            and self._paused_speech.handle.allow_interruptions
        ):
            # a final transcript or a committed turn ended the pause
            self._paused_speech.handle.interrupt(source="user_turn")
            # ensure the generation is done — but only if a generation
```

When the timer runs out with the reply still paused, it resumes from where it stopped (`_start_false_interruption_timer`):

```python
            resumed = False
            if (
                self._session.options.interruption["resume_false_interruption"]
                and (audio_output := self._session.output.audio)
                and audio_output.can_pause
                and not self._paused_speech.handle.done()
            ):
                self._restore_paused_speech_state(self._paused_speech)
                audio_output.resume()
                resumed = True
                logger.debug("resumed false interrupted speech", extra={"timeout": timeout})

            self._session.emit(
                "agent_false_interruption", AgentFalseInterruptionEvent(resumed=resumed)
```

Silero plugin defaults (livekit-plugins/livekit-plugins-silero/livekit/plugins/silero/vad.py, same commit), the same thresholds and silence as this project's VAD (0.5 / 0.35 / 0.55 s):

```python
        min_speech_duration: float = 0.05,
        min_silence_duration: float = 0.55,
        prefix_padding_duration: float = 0.5,
        max_buffered_speech: float = 60.0,
        activation_threshold: float = 0.5,
        sample_rate: Literal[8000, 16000] = 16000,
        force_cpu: bool = True,
        onnx_file_path: NotGivenOr[Path | str] = NOT_GIVEN,
        deactivation_threshold: NotGivenOr[float] = NOT_GIVEN,
            deactivation_threshold (float): Negative threshold (noise or exit threshold). If model's current state is SPEECH, values BELOW this value are considered as NON-SPEECH. Default is max(activation_threshold - 0.15, 0.01).
```

## LiveKit: start of speech is handled with the time speech started (same file and commit, on_start_of_speech)

```python
    def on_start_of_speech(
        self,
        ev: vad.VADEvent | None,
        speech_start_time: float,
    ) -> None:
        self._session._update_user_state("speaking", last_speaking_time=speech_start_time)
        if self._audio_recognition:
            self._audio_recognition._on_start_of_speech(
                started_at=speech_start_time,
                speech_duration=ev.speech_duration if ev else 0.0,
                user_speaking_span=self._session._user_speaking_span,
                skip_adaptive_interruption=self._interruption_detected,
            )
        self._user_silence_event.clear()
        self._stt_eos_received = False
```
