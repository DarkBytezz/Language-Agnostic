#!/usr/bin/env python3
"""
run_all.py — single command to run STT -> RAG -> print & save answer.

Usage examples:
  python run_all.py                    # record (auto), process, print answer (no translation)
  python run_all.py --stt-lang auto --target hi-IN --max-secs 6
"""
import argparse
import importlib
import sys
import os

# Try to import stt and rag either from package 'src' or local module
def import_module_try(names):
    for name in names:
        try:
            mod = importlib.import_module(name)
            return mod
        except Exception:
            continue
    raise ImportError(f"Could not import any of: {names}")

# Try common locations
stt = None
rag = None
try:
    stt = import_module_try(["stt", "chatbot_sih.src.stt"])
except Exception as e:
    print("Error: could not import stt module:", e)
    sys.exit(1)

try:
    rag = import_module_try(["rag", "chatbot_sih.src.rag"])
except Exception as e:
    print("Error: could not import rag module:", e)
    sys.exit(1)

TRANSCRIPTS_DIR = os.path.join(os.getcwd(), "transcripts")
LATEST_TRANSCRIPT = os.path.join(TRANSCRIPTS_DIR, "latest_transcript.txt")
LATEST_ANSWER = os.path.join(TRANSCRIPTS_DIR, "latest_answer.txt")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stt-lang", default="auto", help="Language for STT (auto/en-IN/hi-IN)")
    parser.add_argument("--target", default="en-IN", help="Target language for final answer (en-IN means no translation)")
    parser.add_argument("--max-secs", type=int, default=6, help="Max record seconds for STT")
    args = parser.parse_args()

    print("[run_all] Recording (STT)... language=", args.stt_lang, "max_secs=", args.max_secs)
    transcript, detected = stt.record_and_transcribe(language=args.stt_lang, seconds=args.max_secs, save_to=LATEST_TRANSCRIPT)
    if not transcript:
        print("[run_all] No transcript returned. Exiting.")
        sys.exit(1)

    print("[run_all] Transcript captured:\n", transcript)
    print(f"[run_all] Saved to {LATEST_TRANSCRIPT}")

    # Decide final-answer target language:
    # - prefer the STT-detected language (if present and not 'unknown')
    # - otherwise use CLI-provided --target
    target_lang = args.target
    if detected and isinstance(detected, str):
        detected_norm = detected.strip()
        # If Sarvam returns short form like 'pa' or full 'pa-IN' handle both
        if detected_norm.lower() != "unknown":
            # map bare codes to regional if needed (optional)
            # If detected is 'pa' or 'pa-IN' we use as-is. Most of your mapping in rag.LANGUAGES uses xx-IN style.
            target_lang = detected_norm

    print(f"[run_all] Using target language for final answer: {target_lang}")

    # Call RAG
    print("[run_all] Querying RAG...")
    final_answer = rag.answer_from_transcript(transcript, target_language_code=target_lang)
    print("\n=== FINAL ANSWER ===\n")
    print(final_answer)
    print("\n(Also saved to {})".format(LATEST_ANSWER))

if __name__ == "__main__":
    main()
