"""Local speech components, all on CPU: Silero VAD, Smart Turn v3.2, SenseVoice ASR, two TTS voices."""
import time

import numpy as np
import onnxruntime as ort
import sherpa_onnx as so

from config import MODELS, SR

THREADS = 4


def _resample(x: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    if sr_in == sr_out:
        return x.astype(np.float32)
    n = int(round(len(x) * sr_out / sr_in))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class SileroVAD:
    """Streaming speech probability per 512-sample frame (sherpa-onnx release of Silero VAD)."""

    def __init__(self):
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1
        o.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(MODELS / "silero_vad.onnx"), sess_options=o)
        self.reset()

    def reset(self):
        self.h = np.zeros((2, 1, 64), np.float32)
        self.c = np.zeros((2, 1, 64), np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        p, self.h, self.c = self.sess.run(None, {"x": frame.reshape(1, -1).astype(np.float32),
                                                 "h": self.h, "c": self.c})
        return float(np.asarray(p).reshape(-1)[0])


PVAD_DIR = (MODELS / "hf" / "hub" / "models--FireRedTeam--FireRedChat-pvad" / "snapshots"
            / "74561b17a50fbe9d8f84dacc453f175cb97f567c")


class PersonalVAD:
    """FireRedChat pVAD (Apache-2.0): speech probability of one target speaker, run on 160-sample windows with a
    recurrent state, as in its LiveKit plugin. Same calls as SileroVAD (reset, one 512-sample frame per call: the
    probability of the last complete window); set_speaker() gives the 192-value ECAPA embedding (zeros until then)."""

    def __init__(self):
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1
        o.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(PVAD_DIR / "pvad.onnx"), sess_options=o)
        self.reset()

    def reset(self):
        self.mel = np.zeros((1, 80, 15), np.float32)
        self.gru = np.zeros((2, 1, 256), np.float32)
        self.emb = np.zeros((1, 192), np.float32)
        self.buf = np.zeros(0, np.float32)
        self.p = 0.0

    def set_speaker(self, emb):
        self.emb = np.asarray(emb, np.float32).reshape(1, 192)

    def __call__(self, frame: np.ndarray) -> float:
        self.buf = np.concatenate([self.buf, frame.astype(np.float32)])
        while len(self.buf) >= 160:
            w, self.buf = self.buf[:160], self.buf[160:]
            out = self.sess.run(None, {"input_audio": w.reshape(1, 160), "spkemb": self.emb,
                                       "mel_buffer": self.mel, "gru_buffer": self.gru})
            self.p, self.mel, self.gru = float(np.asarray(out[1]).reshape(-1)[0]), out[2], out[3]
        return self.p


class SmartTurn:
    """Pipecat Smart Turn v3.2 (CPU build): probability that the speaker has finished the turn."""

    def __init__(self):
        from transformers import WhisperFeatureExtractor
        o = ort.SessionOptions()
        o.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        o.inter_op_num_threads = 1
        o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(MODELS / "smart-turn-v3.2-cpu.onnx"), sess_options=o)
        self.fe = WhisperFeatureExtractor(chunk_length=8)

    def __call__(self, audio: np.ndarray) -> tuple[float, float]:
        t = time.perf_counter()
        a = audio[-8 * SR:]
        if len(a) < 8 * SR:
            a = np.concatenate([np.zeros(8 * SR - len(a), np.float32), a])  # pad at the start, as upstream
        f = self.fe(a, sampling_rate=SR, return_tensors="np", padding="max_length",
                    max_length=8 * SR, truncation=True, do_normalize=True)
        x = f.input_features.squeeze(0).astype(np.float32)[None]
        p = float(self.sess.run(None, {"input_features": x})[0].reshape(-1)[0])
        return p, time.perf_counter() - t


class ASR:
    """SenseVoice-Small int8 (zh, en, ja, ko, yue) through sherpa-onnx."""

    def __init__(self, use_itn: bool = True, language: str = "auto"):
        d = MODELS / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
        self.rec = so.OfflineRecognizer.from_sense_voice(
            model=str(d / "model.int8.onnx"), tokens=str(d / "tokens.txt"),
            use_itn=use_itn, language=language, num_threads=THREADS)

    def __call__(self, audio: np.ndarray) -> tuple[str, float]:
        t = time.perf_counter()
        s = self.rec.create_stream()
        s.accept_waveform(SR, audio.astype(np.float32))
        self.rec.decode_stream(s)
        return s.result.text.strip(), time.perf_counter() - t


class AgentTTS:
    """The agent's voice: MeloTTS zh_en (VITS), resampled to 16 kHz."""

    def __init__(self):
        d = MODELS / "vits-melo-tts-zh_en"
        cfg = so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(vits=so.OfflineTtsVitsModelConfig(
            model=str(d / "model.onnx"), lexicon=str(d / "lexicon.txt"), tokens=str(d / "tokens.txt"),
            dict_dir=str(d / "dict")), num_threads=THREADS),
            rule_fsts=",".join(str(d / f) for f in ("date.fst", "new_heteronym.fst", "number.fst", "phone.fst")),
            max_num_sentences=1)
        self.tts = so.OfflineTts(cfg)

    def __call__(self, text: str) -> tuple[np.ndarray, float]:
        t = time.perf_counter()
        a = self.tts.generate(text, sid=0, speed=1.0)
        if a.sample_rate <= 0 or len(a.samples) == 0:
            # a chunk made only of symbols the voice cannot say (a lone bracket, an emoji, "*"): no audio
            return np.zeros(0, np.float32), time.perf_counter() - t
        return _resample(np.array(a.samples, np.float32), a.sample_rate), time.perf_counter() - t


class UserTTS:
    """Simulated users: Kokoro v1.1 multi-lang (103 voices; 0-2 English, 3-102 Chinese)."""

    def __init__(self):
        d = MODELS / "kokoro-multi-lang-v1_1"
        cfg = so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(kokoro=so.OfflineTtsKokoroModelConfig(
            model=str(d / "model.onnx"), voices=str(d / "voices.bin"), tokens=str(d / "tokens.txt"),
            data_dir=str(d / "espeak-ng-data"), dict_dir=str(d / "dict"),
            lexicon=f"{d / 'lexicon-us-en.txt'},{d / 'lexicon-zh.txt'}"), num_threads=THREADS),
            rule_fsts=f"{d / 'date-zh.fst'},{d / 'number-zh.fst'}", max_num_sentences=1)
        self.tts = so.OfflineTts(cfg)

    def __call__(self, text: str, sid: int, speed: float = 1.0) -> np.ndarray:
        a = self.tts.generate(text, sid=sid, speed=speed)
        return _resample(np.array(a.samples, np.float32), a.sample_rate)


def trim(x: np.ndarray, thr: float = 0.01, pad: float = 0.02) -> np.ndarray:
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x
    p = int(pad * SR)
    return x[max(0, idx[0] - p): idx[-1] + p]
