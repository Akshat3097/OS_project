"""Optional local speech-to-text with faster-whisper (offline; no audio leaves the laptop).

    pip install faster-whisper
setup.bat downloads the model (small.en ≈ 460 MB) and the server loads it at start-up. CPU int8 is the default
because it works everywhere: plugged in, a one-minute answer takes about 10 s with small.en (about 3 s with
base.en, which mishears more). Set TUTOR_WHISPER_DEVICE=cuda to use the GPU once CUDA libraries are set up.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from pathlib import Path

import config

_model = None
_loading = threading.Lock()     # the server warms the model in a thread while a recording may already arrive


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model
    with _loading:
        if _model is None:
            from faster_whisper import WhisperModel
            compute = "int8" if config.WHISPER_DEVICE == "cpu" else "float16"
            _model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE, compute_type=compute)
    return _model


def decode(path: str):
    """Audio file (browser WebM/Opus, WAV, …) → 16 kHz mono float32 samples, as Whisper expects.
    Done here rather than by faster-whisper because its own decoder passes an option (metadata_errors) that
    PyAV 14+ no longer accepts; these PyAV calls work across versions."""
    import av
    import numpy as np
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    with av.open(path, mode="r") as container:
        for frame in container.decode(container.streams.audio[0]):
            chunks += [f.to_ndarray() for f in resampler.resample(frame)]
        chunks += [f.to_ndarray() for f in resampler.resample(None)]          # flush what the resampler buffered
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


# Whisper is primed with the words it should expect; the base model mishears course terms without it.
VOCABULARY = ("Operating systems: CPU scheduling, FCFS, SJF, SRTF, round robin, time quantum, priority, aging, starvation, "
              "preempt, preemptive, non-preemptive, burst time, arrival time, completion time, turnaround time, "
              "waiting time, Gantt chart, context switch, ready queue, critical section, race condition, mutex, "
              "semaphore, wait, signal, producer, consumer, bounded buffer, readers, writers, dining philosophers, "
              "chopsticks, deadlock, circular wait, hold and wait, Banker's algorithm, safe state, need matrix.")


LAST_DIR = Path(config.DATA_DIR) / "speech"     # the last recording, kept on this laptop to check what the mic heard
SILENT_PEAK_DB = -55.0                          # quieter than this the microphone heard nothing (speech peaks near -10)


def level(samples) -> dict:
    """Length and loudness of 16 kHz samples, in seconds and dB below full scale."""
    import numpy as np
    db = lambda v: round(20 * math.log10(max(v, 1e-6)), 1)
    if not len(samples):
        return {"seconds": 0.0, "rms_db": -120.0, "peak_db": -120.0}
    return {"seconds": round(len(samples) / 16000, 1), "rms_db": db(float(np.sqrt(np.mean(samples ** 2)))),
            "peak_db": db(float(np.abs(samples).max()))}


def transcribe_checked(audio_bytes: bytes, suffix: str = ".wav", hint: str = "") -> dict:
    """Text plus how much to trust it. hint: the lesson's title, added to the vocabulary prompt.
    Whisper invents fluent sentences from unclear audio, often continuing its prompt, so the prompt is only the
    vocabulary and the title, each segment is decoded on its own (no carried-over text that lets one bad guess run
    on), and segments it is unsure of make the result "unsure" so the page asks the student to check it."""
    model = _load()
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)
        samples = decode(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    out = {"text": "", "unsure": False, "reason": "", **level(samples)}
    segs = []
    if out["peak_db"] < SILENT_PEAK_DB:
        out.update(unsure=True, reason="silent")
    else:
        segments, _info = model.transcribe(samples, language="en", vad_filter=True, condition_on_previous_text=False,
                                           initial_prompt=(VOCABULARY + " " + hint).strip())
        for s in segments:
            seg = {"text": s.text.strip(), "logprob": round(s.avg_logprob, 2), "no_speech": round(s.no_speech_prob, 2),
                   "compression": round(s.compression_ratio, 2)}
            seg["dropped"] = s.no_speech_prob > 0.6 and s.avg_logprob < -0.7          # most likely not speech at all
            seg["doubtful"] = not seg["dropped"] and (s.avg_logprob < -1.0 or s.compression_ratio > 2.4)
            segs.append(seg)
        out["text"] = " ".join(s["text"] for s in segs if not s["dropped"]).strip()
        if any(s["doubtful"] for s in segs):
            out.update(unsure=True, reason="unclear")
    _keep_last(audio_bytes, suffix, {**out, "segments": segs, "model": config.WHISPER_MODEL})
    return out


def _keep_last(audio_bytes: bytes, suffix: str, report: dict) -> None:
    try:
        LAST_DIR.mkdir(parents=True, exist_ok=True)
        for old in LAST_DIR.glob("last.*"):
            old.unlink()
        (LAST_DIR / f"last{suffix}").write_bytes(audio_bytes)
        (LAST_DIR / "last.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    except OSError:
        pass                                     # only a check aid: never fail the transcription over it


def transcribe(audio_bytes: bytes, suffix: str = ".wav", hint: str = "") -> str:
    return transcribe_checked(audio_bytes, suffix, hint)["text"]
