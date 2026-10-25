"""Voice teach-back: a recording in the browser's format (WebM/Opus) is decoded and transcribed offline.
tests/data/srtf_explanation.webm is an 18-second explanation of SRTF made with Windows text-to-speech."""
from pathlib import Path

import pytest

import config
from tutor import speech

CLIP = Path(__file__).parent / "data" / "srtf_explanation.webm"


def test_decode_webm_to_16k_mono():
    pytest.importorskip("av")
    audio = speech.decode(str(CLIP))
    assert audio.dtype.name == "float32" and 17 < len(audio) / 16000 < 19 and abs(audio).max() <= 1.0


def test_transcribe_and_assess(tmp_path):
    if not speech.available():
        pytest.skip("faster-whisper is not installed")
    try:
        from huggingface_hub import try_to_load_from_cache
        if not try_to_load_from_cache(f"Systran/faster-whisper-{config.WHISPER_MODEL}", "model.bin"):
            pytest.skip("the speech model is not downloaded (run setup.bat)")
    except ImportError:
        pytest.skip("huggingface_hub missing")
    text = speech.transcribe(CLIP.read_bytes(), ".webm")
    assert "remaining time" in text.lower() and "arrival" in text.lower()
    from tutor import lessons as L, teachback
    a = teachback.keyword_assess(L.LESSON_BY_ID["srtf"], text)
    assert sum(v == "clear" for v in a["ideas"].values()) >= 3


def test_checked_transcription_flags_silence_and_keeps_the_last_clip(tmp_path, monkeypatch):
    if not speech.available():
        pytest.skip("faster-whisper is not installed")
    try:
        from huggingface_hub import try_to_load_from_cache
        if not try_to_load_from_cache(f"Systran/faster-whisper-{config.WHISPER_MODEL}", "model.bin"):
            pytest.skip("the speech model is not downloaded (run setup.bat)")
    except ImportError:
        pytest.skip("huggingface_hub missing")
    import io
    import json
    import wave
    monkeypatch.setattr(speech, "LAST_DIR", tmp_path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:                     # two seconds from a microphone that hears nothing
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 32000)
    silent = speech.transcribe_checked(buf.getvalue(), ".wav")
    assert silent["reason"] == "silent" and silent["unsure"] and not silent["text"]

    clear = speech.transcribe_checked(CLIP.read_bytes(), ".webm", hint="Shortest Remaining Time First (SRTF).")
    assert not clear["unsure"] and "remaining time" in clear["text"].lower() and clear["peak_db"] > -20
    report = json.loads((tmp_path / "last.json").read_text(encoding="utf-8"))
    assert (tmp_path / "last.webm").exists() and report["segments"] and report["model"] == config.WHISPER_MODEL
