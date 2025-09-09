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
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv

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

ALLOWED_LANG_CODES = {"en-IN","hi-IN","bn-IN","kn-IN","ml-IN","mr-IN","od-IN","pa-IN","ta-IN","te-IN","gu-IN","unknown"}
SHORTHAND_MAP = {"en":"en-IN","hi":"hi-IN","bn":"bn-IN","kn":"kn-IN","ml":"ml-IN","mr":"mr-IN","od":"od-IN","pa":"pa-IN","ta":"ta-IN","te":"te-IN","gu":"gu-IN"}

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

def record_from_mic(duration_seconds=DEFAULT_RECORD_SECONDS, samplerate=DEFAULT_SAMPLE_RATE, channels=DEFAULT_CHANNELS):
    print(f"Recording for {duration_seconds}s — speak now...")
    recording = sd.rec(int(duration_seconds * samplerate), samplerate=samplerate, channels=channels, dtype="int16")
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
        resp = client.speech_to_text.transcribe(file=audio_file_like, model=model, language_code=language_code)
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
    """Robust extraction of transcript from Sarvam response.

    Handles:
      - dict responses with keys like 'transcript', 'data' -> 'transcript', 'alternatives'
      - string responses that contain "transcript='...'" or 'transcript="..."'
      - fallback: try to split on "transcript=" and extract up to common delimiters
      - last-resort: return the raw string (so you don't lose info)
    """
    if not resp:
        return None

    # If it's a dict and contains an explicit error marker, bail early
    if isinstance(resp, dict) and "error" in resp:
        return None

    # --- Case: dict-like structured response (preferred) ---
    if isinstance(resp, dict):
        # common direct keys
        for key in ("transcript", "text", "result", "transcription"):
            if key in resp and isinstance(resp[key], str) and resp[key].strip():
                return resp[key].strip()
        # nested under data
        if "data" in resp and isinstance(resp["data"], dict):
            d = resp["data"]
            for key in ("transcript", "text", "transcription"):
                if key in d and isinstance(d[key], str) and d[key].strip():
                    return d[key].strip()
        # alternatives array
        if "alternatives" in resp and isinstance(resp["alternatives"], list) and len(resp["alternatives"]) > 0:
            alt0 = resp["alternatives"][0]
            if isinstance(alt0, dict) and "transcript" in alt0 and isinstance(alt0["transcript"], str):
                return alt0["transcript"].strip()

    # --- Case: string-like response (Sarvam sometimes returns a str that contains transcript=...) ---
    if isinstance(resp, str):
        s = resp.strip()
        # 1) single-quoted transcript
        m = re.search(r"transcript\s*=\s*'([^']*)'", s)
        if m and m.group(1).strip():
            return m.group(1).strip()
        # 2) double-quoted transcript
        m2 = re.search(r'transcript\s*=\s*"([^"]*)"', s)
        if m2 and m2.group(1).strip():
            return m2.group(1).strip()
        # 3) more permissive split-based extraction:
        #    look for "transcript=" and capture until a likely delimiter (space + word= or end)
        idx = s.find("transcript=")
        if idx != -1:
            tail = s[idx + len("transcript="):]
            # If it starts with a quote, strip it using whichever quote is present
            if tail.startswith("'"):
                tail = tail[1:]
                end_idx = tail.find("'")
                if end_idx != -1:
                    candidate = tail[:end_idx].strip()
                    if candidate:
                        return candidate
            elif tail.startswith('"'):
                tail = tail[1:]
                end_idx = tail.find('"')
                if end_idx != -1:
                    candidate = tail[:end_idx].strip()
                    if candidate:
                        return candidate
            else:
                # no surrounding quotes — stop at known field names or at " timestamps" or " language_code"
                stop_tokens = [" timestamps", " timestamps=", " language_code", " diarized_transcript", " request_id"]
                stop_positions = [tail.find(tok) for tok in stop_tokens if tail.find(tok) != -1]
                if stop_positions:
                    stop = min(stop_positions)
                    candidate = tail[:stop].strip()
                else:
                    # as last resort, take the whole tail up to 200 chars
                    candidate = tail.strip()[:200]
                if candidate:
                    return candidate

    # --- If it's neither dict nor string, try converting to str and retry above heuristics once ---
    try:
        s = str(resp)
        m = re.search(r"transcript\s*=\s*'([^']*)'", s)
        if m and m.group(1).strip():
            return m.group(1).strip()
    except Exception:
        pass

    # --- Final fallback: if resp is a dict-ish object whose json string is useful, return its json dump ---
    try:
        return json.dumps(resp, ensure_ascii=False)
    except Exception:
        return None


def extract_detected_language(resp):
    """
    More robust extraction of detected language code from Sarvam response.

    - Checks direct keys: language_code, language, detected_language, lang, detectedLang
    - Looks inside nested dicts: data, metadata, alternatives
    - Parses string/object reprs like "language_code='hi-IN'"
    - Normalizes short forms using SHORTHAND_MAP and validates against ALLOWED_LANG_CODES
    - Returns normalized code (e.g. 'pa-IN') or None
    """
    if not resp:
        return None

    def _normalize(code: str):
        if not code or not isinstance(code, str):
            return None
        c = code.strip()
        # unify underscores/dashes and lower for matching
        c = c.replace("_", "-")
        # direct exact allowed
        if c in ALLOWED_LANG_CODES:
            return c
        # try case-insensitive match to allowed codes
        for ac in ALLOWED_LANG_CODES:
            if ac.lower() == c.lower():
                return ac
        # shorthand map (e.g. 'pa' -> 'pa-IN' or 'en' -> 'en-IN')
        if c in SHORTHAND_MAP:
            return SHORTHAND_MAP[c]
        if c.lower() in SHORTHAND_MAP:
            return SHORTHAND_MAP[c.lower()]
        # bare 2-letter code -> attempt to map to xx-IN
        if re.fullmatch(r"^[a-z]{2}$", c.lower()):
            cand = SHORTHAND_MAP.get(c.lower(), c.lower() + "-IN")
            if cand in ALLOWED_LANG_CODES:
                return cand
            return cand
        return None

    # 1) If dict-like: check common keys at top-level
    if isinstance(resp, dict):
        for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
            if key in resp and isinstance(resp[key], str) and resp[key].strip():
                norm = _normalize(resp[key].strip())
                if norm:
                    return norm

        # 2) check nested under 'data' or 'metadata'
        for parent in ("data", "metadata"):
            if parent in resp and isinstance(resp[parent], dict):
                d = resp[parent]
                for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
                    if key in d and isinstance(d[key], str) and d[key].strip():
                        norm = _normalize(d[key].strip())
                        if norm:
                            return norm

        # 3) check alternatives list
        if "alternatives" in resp and isinstance(resp["alternatives"], list):
            for alt in resp["alternatives"]:
                if isinstance(alt, dict):
                    for key in ("language_code", "language", "detected_language", "lang", "detectedLang"):
                        if key in alt and isinstance(alt[key], str) and alt[key].strip():
                            norm = _normalize(alt[key].strip())
                            if norm:
                                return norm

    # 4) If response is a string or object repr: regex search for language codes
    try:
        s = resp if isinstance(resp, str) else str(resp)
        # look for patterns like language_code='hi-IN' or language="pa-IN" or lang=pa
        m = re.search(r"(?:language_code|language|detected_language|lang)\s*=\s*['\"]?([a-z]{2}(?:-[A-Za-z]{2})?)['\"]?", s)
        if m:
            norm = _normalize(m.group(1))
            if norm:
                return norm
    except Exception:
        pass

    # Nothing reliable found
    return None


def record_and_transcribe(language: str = "auto", seconds: int = DEFAULT_RECORD_SECONDS, model: str = STT_MODEL_NAME, save_to: str = None):
    """
    Record from mic, transcribe and return (transcript, detected_language).
    Saves transcript to transcripts/latest_transcript.txt (overwrites).
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
        print("No transcript returned by Sarvam. Raw response:")
        print(resp)
        return None, detected_lang

    # Save only LATEST (overwrite)
    try:
        with open(save_to or LATEST_TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
            f.write(transcript)
    except Exception as e:
        print("Warning: could not save transcript to file:", e)

    return transcript, detected_lang

# Command-line convenience
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