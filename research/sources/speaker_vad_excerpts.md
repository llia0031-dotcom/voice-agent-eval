# Listening only to the main speaker: saved excerpts (fetched 2026-11-14)

Stars and licences from the GitHub API, sizes and licences from the Hugging Face API, 2026-11-14.

## FireRedChat pVAD (FireRedTeam; paper arXiv 2509.06502)

- FireRedTeam/FireRedChat: 604 stars, Apache-2.0. Plugin fireredchat-submodules/livekit-plugins-fireredchat-pvad: 24 stars, Apache-2.0.
- Hugging Face FireRedTeam/FireRedChat-pvad: license apache-2.0, languages zh and en; pvad.onnx 3.9 MB; spkrec-ecapa-voxceleb/embedding_model.ckpt 83.3 MB, classifier.ckpt 5.5 MB, label_encoder.ckpt 0.1 MB (base model speechbrain/spkrec-ecapa-voxceleb, apache-2.0).

From the paper (HTML version):

> The controller integrates streaming personalized VAD (pVAD) to suppress false barge-ins from noise and non-primary speakers, precisely timestamp primary-speaker segments, and explicitly enable primary-speaker barge-ins; a semantic end-of-turn detector improves stop decisions.
> To address this, we introduce a streaming personalized voice activity detection module (pVAD) that suppresses background noise and non-target speakers, thereby reducing false interruptions, improving the success rate of primary-speaker barge-in, and yielding more accurate localization of the target speaker’s speech segments.

From the model card:

> # After the first utterance (or when primary speaker switches based on RMS), call VADStream's update_speaker() to update speaker embedding.

From the plugin, livekit/plugins/fireredchat_pvad/vad.py (10 ms frames, a 192-value speaker embedding, recurrent state):

```python
        self.window_size_samples = 160
        self.mel_buffer = np.zeros((1, 80, 15), dtype=np.float32)
        self.gru_buffer = np.zeros((2, 1, 256), dtype=np.float32)
        self.spkemb = np.zeros((1, 192), dtype=np.float32)
        self.sample_rate = 16000
        outputs = self._session.run(None, {
            'input_audio': wav_np,
            'spkemb': self.spkemb,
            'mel_buffer': self.mel_buffer,
            'gru_buffer': self.gru_buffer
        })
        raw_prob = outputs[1][0].tolist()[0] # 1
        self.mel_buffer = outputs[2] # (1, 80, 15)
        self.gru_buffer = outputs[3] # (2, 1, 256) 
        self._ecapa_window_size = 80000 # take 1 second for spk embedding calculation
```

Plugin defaults (same file):

```python
        min_speech_duration: float = 0.16,
        min_silence_duration: float = 0.40,
        prefix_padding_duration: float = 0.5,
        max_buffered_speech: float = 20.0,
        activation_threshold: float = 0.5,
        sample_rate: Literal[16000] = 16000,
```

## Other options checked

- personal-vad (PyPI; a reproduction of Google's Personal VAD 1.0 and 2.0, Apache-2.0, pretrained models on Hugging Face under wq2012): not checked further, FireRedChat pVAD is built for barge-in in voice agents and covers Chinese.
- Speaker verification as a gate: csukuangfj/speaker-embedding-models (sherpa-onnx), 3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx 28.3 MB. Would need a gating rule of this project's own; kept as the fallback.
- Noise suppression (RNNoise, DeepFilterNet) removes non-speech noise; the failures here come from background speech, which Silero already treats as speech, and pink noise was marked as speech in no frame.
- PyPI: speechbrain 1.1.2 (Apache-2.0) needs torch>=2.7.1 and torchaudio>=2.7.1; torchaudio 2.11.1 needs torch>=2.11, Windows wheel 0.3 MB; sentencepiece 0.2.3 Windows wheel 1.7 MB.
