# Acoustic backchannel / turn-state models: saved excerpts (fetched 2026-11-14)

Repository and model facts from the GitHub API and the Hugging Face API on 2026-11-14.

## MaAI (github.com/MaAI-Kyoto/MaAI), 165 stars, MIT; PyPI `maai` 0.2.27 (MIT)

> Currently available for English, Chinese, and Japanese languages, MaAI will continue to expand its language coverage and non-linguistic behavior repertoire in the future.
> Thanks to its lightweight design, MaAI operates efficiently, even exclusively on CPU hardware⚡

From readme/bc_det.md:

> This model detects **whether the utterance a speaker is producing right now is a backchannel** (相槌, e.g. "うん", "はい", "yeah", "right"). It is a *detection* model: there is no time shift between the audio and the target.

> The model takes both speaker channels and processes them jointly with cross-channel attention. Both channels matter: the interlocutor's speech is most of the evidence that a short utterance is a backchannel rather than the beginning of a turn.

> To obtain a binary decision, apply a threshold. Note that **`0.5` is usually not the best operating point** on this task: backchannels cover only about 4% of frames, so the model is trained on heavily imbalanced data. On the Japanese development set the tuned thresholds were about `0.39` for frame-level F1 and `0.45` for event-level F1.

> Backchannels are short — the median duration is around 0.25 s — so smoothing the output (filling short gaps, removing short spikes) tends to delete real events rather than tidy their edges. It is off by default and is generally not recommended.

> Only the 12.5 Hz Mimi-based models (`model_type="normal-ver2"`) are currently released for this mode.

> For the single-channel version, pass only `audio_ch1` (omit `audio_ch2`); `result["p_bc_det"]` is then a single float. Because the model relies on the interlocutor's speech, the mono variant is less accurate than the two-channel one — pass `audio_ch2` when both channels are available.

Language table in readme/bc_det.md:

| lang | model_type | frame_rate |
| ---- | ---------- | ---------- |
| jp | `normal-ver2` (Mimi encoder) | 12.5 |
| en | `normal-ver2` (Mimi encoder) | 12.5 |
| ch | `normal-ver2` (Mimi encoder) | 12.5 |

Hugging Face (API, 2026-11-14):
- maai-kyoto/bc_det_ch: license cc-by-nc-nd-4.0; files bc_det_mimi_state_dict_ch_12.5hz_20000msec.pt (17.4 MB, two-channel) and bc_det_mono_mimi_state_dict_ch_12.5hz_20000msec.pt (17.4 MB, single-channel). The model card has no text beyond the licence.
- maai-kyoto/bc_det_en: 17 MB; no licence tag in the API answer.
- maai-kyoto/continuous-mimi-onnx (encoder the models use with use_mimi_onnx=True): license cc-by-4.0; continuous_mimi_fp32.onnx 155.9 MB, continuous_mimi_int8.onnx 156.0 MB.
- kyutai/mimi (encoder weights when ONNX is not used): license cc-by-4.0; model.safetensors 384.6 MB.
- PyPI maai 0.2.27 requires torch>=2.6.0, transformers==5.5.3, onnxruntime-gpu>=1.20.0 (not on macOS), PyQt5, pygame-ce, fastapi and others.

## Easy Turn (github.com/ASLP-lab/Easy-Turn), 156 stars, Apache-2.0

> The Easy Turn Trainset is a large-scale audio dataset for turn-taking detection, comprising both real and synthetic data. It contains four subsets corresponding to different conversational turn-taking states: 580 hours of complete state, 532 hours of incomplete state, 10 hours of backchannel state, and 23 hours of wait state, totaling approximately 1,100 hours. Each recording is accompanied by 

| Model                         | Params (MB) ↓ | Latency (ms) | Memory (MB) | ACC_cp (%) ↑ | ACC_incp (%) | ACC_bc (%) | ACC_wait (%) |
|-------------------------------|---------------|--------------|-------------|--------------|--------------|------------|--------------|
| [Paraformer](https://github.com/modelscope/FunASR) + [TEN Turn Detection](https://github.com/ten-framework/ten-turn-detection) | 7220          | 204          | 15419       | 86.67        | 89.3         | –          | 91           |
| [Smart Turn V2](https://github.com/pipecat-ai/smart-turn)                 | **95**        | **27**       | **370**     | 78.67        | 62           | –          | –            |
| **Easy Turn (Proposed)**          | 850           | 263          | 2559        | **96.33**    | **97.67**    | **91**     | **98**       |

> We evaluate **Easy Turn** against two open-source turn-taking detection models, TEN Turn Detection and Smart Turn V2, using the **Easy Turn testset**. All experiments are conducted on a single NVIDIA RTX 4090 GPU. Notably, since TEN Turn Detection lacks dir

Hugging Face ASLP-lab/Easy-Turn: license apache-2.0; checkpoint.pt 3451.8 MB.

## Others checked

- x-square-robot/X2-Turn-4B-0812 (arXiv 2608.10878): license apache-2.0, languages zh and en, 10485 MB of files; a 4B-parameter streaming ASR model with a turn-state head.
- brgroup/TurnSense: license apache-2.0, zh and en, 1452 MB of files; text-based classes complete / incomplete / invalid (model card, via web search).
- bnovikov/bargein-classifier: license cc-by-4.0, language en only.
- Krisp VIVA interruption prediction (Pipecat KrispVivaIPUserTurnStartStrategy): needs KRISP_VIVA_API_KEY from the Krisp developer portal for SDK 1.6.1 and later (Pipecat docs, via web search).
- LiveKit adaptive interruption handling: runs on LiveKit Cloud inference only (docs, see interruption_settings_excerpts.md).
