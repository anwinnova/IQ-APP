"""
utils.py — Speech utilities for IQ
Changes:
  - Lazy model loading: WhisperModel loads on first use, not at import time
    (prevents Railway startup crash while model downloads)
  - Model cached globally after first load
  - Graceful error handling for missing ffmpeg/libsndfile
  - Saves audio to audio_files/ folder (consistent path)
"""
import os
from gtts import gTTS

# ── Lazy Whisper model — loads only when first transcription is requested ──
_whisper_model = None

def _get_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("[Whisper] Loading model 'base' on CPU...")
            _whisper_model = WhisperModel(
                "base",
                device="cpu",
                compute_type="int8",      # int8 uses less RAM, works on Railway free tier
                download_root="/tmp/whisper_models",  # persistent within session
            )
            print("[Whisper] Model loaded OK")
        except Exception as e:
            print(f"[Whisper] Model load failed: {e}")
            _whisper_model = None
    return _whisper_model


def speech_to_text(audio_path: str) -> str:
    """Transcribe audio file to text using Whisper. Returns empty string on error."""
    model = _get_model()
    if model is None:
        print("[Whisper] Model not available — returning empty transcript")
        return ""
    if not os.path.exists(audio_path):
        print(f"[Whisper] Audio file not found: {audio_path}")
        return ""
    file_size = os.path.getsize(audio_path)
    if file_size < 100:
        print(f"[Whisper] Audio file too small ({file_size} bytes) — skipping")
        return ""
    try:
        segments, info = model.transcribe(audio_path, language="en", beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[Whisper] Transcribed ({file_size} bytes → {len(text)} chars): '{text[:60]}...' " if len(text)>60 else f"[Whisper] '{text}'")
        return text
    except Exception as e:
        print(f"[Whisper] Transcription error: {e}")
        return ""


def text_to_speech(text: str, filename: str = "output.mp3") -> str:
    """Convert text to speech MP3 using gTTS. Saves to filename path."""
    try:
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
        tts = gTTS(text, lang="en", slow=False)
        tts.save(filename)
        print(f"[TTS] Saved: {filename}")
        return filename
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return filename
