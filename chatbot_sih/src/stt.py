#!/usr/bin/env python3
"""
stt.py — STT-only (Sarvam) with auto-detect.
Saves only transcripts/latest_transcript.txt (overwritten).
Exports: record_and_transcribe(language='auto', seconds=6, save_to=None)
"""
import os
import io
import json
import re
import numpy as np
# soundfile is only needed for saving BytesIO audio
import soundfile as sf
from dotenv import load_dotenv

# sounddevice (PortAudio) is optional: works locally, not on Render
try:
    import sounddevice as sd
except Exception:
    sd = None

# Load environment variables (local: .env, Render: injected env vars)
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
if not SARVAM_API_KEY:
    raise SystemExit("Set SARVAM_API_KEY in environment or .env")

# Sarvam SDK for STT
try:
    from sarvamai import SarvamAI
except Exception:
    raise SystemExit("Install sarvamai SDK: pip install sarvamai")

# Config
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_RECORD_SECONDS = 6
STT_MODEL_NAME = "saarika:v2.5"

ALLOWED_LANG_CODES = {
    "en-IN","hi-IN","bn-IN","kn-IN","ml-IN","mr-IN","od-IN","pa-IN","ta-IN","te-IN","gu-IN","unknown"
}
SHORTHAND_MAP = {
    "en":"en-IN","hi":"hi-IN","bn":"bn-IN","kn":"kn-IN","ml":"ml-IN","mr":"mr-IN",
    "od":"od-IN","pa":"pa-IN","ta":"ta-IN","te":"te-IN","gu":"gu-IN"
}

# Transcripts folder (single-file behavior)
TRANSCRIPTS_DIR = os.path.join(os.getcwd(), "transcripts")
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
LATEST_TRANSCRIPT_PATH = os.path.join(TRANSCRIPTS_DIR, "latest_transcript.txt")


def normalize_lang_code(user_input: str) -> str:
    if not user_input:
        return ""
    u = user_input.strip()
    if u.lower() == "auto":
        return "unknown"
    if u in ALLOWED_LANG_CODES:
        return u
    if u in SHORTHAND_MAP:
        return SHORTHAND_MAP[u]
    u2 = u.replace("_","-").lower()
    for code in ALLOWED_LANG_CODES:
        if code.lower() == u2:
            return code
    if u.lower() in SHORTHAND_MAP:
        return SHORTHAND_MAP[u.lower()]
    return ""


def record_from_mic(duration_seconds=DEFAULT_RECORD_SECONDS,
                    samplerate=DEFAULT_SAMPLE_RATE,
                    channels=DEFAULT_CHANNELS):
    """
    Record from mic only when sounddevice (PortAudio) is available.
    On servers without PortAudio this raises a clear error — you shouldn't
    call this on Render (server) where uploads are expected instead.
    """
    if sd is None:
        raise RuntimeError("sounddevice/PortAudio not available in this environment. "
                           "Use uploaded audio files instead.")
    print(f"Recording for {duration_seconds}s — speak now...")
    recording = sd.rec(int(duration_seconds * samplerate),
                       samplerate=samplerate,
                       channels=channels,
                       dtype="int16")
    sd.wait()
    audio_np = np.asarray(recording)
    bio = io.BytesIO()
    sf.write(bio, audio_np, samplerate, format="WAV", subtype="PCM_16")
    bio.seek(0)
    return bio


# STT client
client = SarvamAI(api_subscription_key=SARVAM_API_KEY)


def transcribe_with_sarvam(audio_file_like, language_code: str = "unknown", model: str = STT_MODEL_NAME):
    try:
        resp = client.speech_to_text.transcribe(
            file=audio_file_like, model=model, language_code=language_code
        )
        return resp
    except Exception as e:
        err_str = str(e)
        parsed = {"message": err_str}
        try:
            jstart = err_str.find("{")
            if jstart != -1:
                parsed_json = json.loads(err_str[jstart:])
                parsed = parsed_json
        except Exception:
            pass
        return {"error": parsed}


def extract_transcript(resp):
    """Robust extraction of transcript from Sarvam response."""
    if not resp:
        return None

    if isinstance(resp, dict) and "error" in resp:
        return None

    if isinstance(resp, dict):
        for key in ("transcript", "text", "result", "transcription"):
            if key in resp and isinstance(resp[key], str) and resp[key].strip():
                return resp[key].strip()
        if "data" in resp and isinstance(resp["data"], dict):
            d = resp["data"]
            for key in ("transcript", "text", "transcription"):
                if key in d and isinstance(d[key], str) and d[key].strip():
                    return d[key].strip()
        if "alternatives" in resp and isinstance(resp["alternatives"], list) and resp["alternatives"]:
            alt0 = resp["alternatives"][0]
            if isinstance(alt0, dict) and "transcript" in alt0 and isinstance(alt0["transcript"], str):
                return alt0["transcript"].strip()

    if isinstance(resp, str):
        s = resp.strip()
        m = re.search(r"transcript\s*=\s*'([^']*)'", s)
        if m and m.group(1).strip():
            return m.group(1).strip()
        m2 = re.search(r'transcript\s*=\s*"([^"]*)"', s)
        if m2 and m2.group(1).strip():
            return m2.group(1).strip()
        idx = s.find("transcript=")
        if idx != -1:
            tail = s[idx + len("transcript="):]
            if tail.startswith("'"):
                tail = tail[1:]
                end_idx = tail.find("'")
                if end_idx != -1:
                    return tail[:end_idx].strip()
            elif tail.startswith('"'):
                tail = tail[1:]
                end_idx = tail.find('"')
                if end_idx != -1:
                    return tail[:end_idx].strip()
            else:
                stop_tokens = [" timestamps", " language_code", " diarized_transcript", " request_id"]
                stop_positions = [tail.find(tok) for tok in stop_tokens if tail.find(tok) != -1]
                stop = min(stop_positions) if stop_positions else None
                candidate = tail[:stop].strip() if stop else tail.strip()[:200]
                if candidate:
                    return candidate

    try:
        s = str(resp)
        m = re.search(r"transcript\s*=\s*'([^']*)'", s)
        if m and m.group(1).strip():
            return m.group(1).strip()
    except Exception:
        pass

    try:
        return json.dumps(resp, ensure_ascii=False)
    except Exception:
        return None


def extract_detected_language(resp):
    """Extract detected language code from Sarvam response."""
    if not resp:
        return None

    def _normalize(code: str):
        if not code or not isinstance(code, str):
            return None
        c = code.strip().replace("_", "-")
        if c in ALLOWED_LANG_CODES:
            return c
        for ac in ALLOWED_LANG_CODES:
            if ac.lower() == c.lower():
                return ac
        if c in SHORTHAND_MAP:
            return SHORTHAND_MAP[c]
        if c.lower() in SHORTHAND_MAP:
            return SHORTHAND_MAP[c.lower()]
        if re.fullmatch(r"^[a-z]{2}$", c.lower()):
            cand = SHORTHAND_MAP.get(c.lower(), c.lower() + "-IN")
            return cand if cand in ALLOWED_LANG_CODES else cand
        return None

    if isinstance(resp, dict):
        for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
            if key in resp and isinstance(resp[key], str) and resp[key].strip():
                return _normalize(resp[key].strip())
        for parent in ("data", "metadata"):
            if parent in resp and isinstance(resp[parent], dict):
                for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
                    if key in resp[parent] and isinstance(resp[parent][key], str) and resp[parent][key].strip():
                        return _normalize(resp[parent][key].strip())
        if "alternatives" in resp and isinstance(resp["alternatives"], list):
            for alt in resp["alternatives"]:
                if isinstance(alt, dict):
                    for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
                        if key in alt and isinstance(alt[key], str) and alt[key].strip():
                            return _normalize(alt[key].strip())

    try:
        s = resp if isinstance(resp, str) else str(resp)
        m = re.search(r"(?:language_code|language|detected_language|lang)\s*=\s*['\"]?([a-z]{2}(?:-[A-Za-z]{2})?)['\"]?", s)
        if m:
            return _normalize(m.group(1))
    except Exception:
        pass

    return None


def record_and_transcribe(language: str = "auto", seconds: int = DEFAULT_RECORD_SECONDS, model: str = STT_MODEL_NAME, save_to: str = None):
    """
    Record from mic (if available), transcribe and return (transcript, detected_language).
    On Render, you should not call this — instead upload audio and call transcribe_with_sarvam directly.
    """
    normalized = normalize_lang_code(language) or "unknown"
    if language.lower() == "auto":
        normalized = "unknown"

    audio = record_from_mic(duration_seconds=seconds)
    audio.seek(0)
    resp = transcribe_with_sarvam(audio, language_code=normalized, model=model)

    transcript = extract_transcript(resp)
    detected_lang = extract_detected_language(resp)

    if not transcript:
        print("No transcript returned by Sarvam. Raw response:", resp)
        return None, detected_lang

    try:
        with open(save_to or LATEST_TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
            f.write(transcript)
    except Exception as e:
        print("Warning: could not save transcript:", e)

    return transcript, detected_lang


if __name__ == "__main__":
    lang = input("Language (en/hi/auto) [default auto]: ").strip() or "auto"
    try:
        secs = int(input(f"Record seconds (default {DEFAULT_RECORD_SECONDS}): ").strip() or DEFAULT_RECORD_SECONDS)
    except Exception:
        secs = DEFAULT_RECORD_SECONDS
    t, d = record_and_transcribe(language=lang, seconds=secs)
    if t:
        print("Transcript:\n", t)
        print("(saved to:", LATEST_TRANSCRIPT_PATH, ")")
    else:
        print("No transcript produced.")
