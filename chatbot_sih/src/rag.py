#!/usr/bin/env python3
"""
rag.py — RAG logic without Streamlit.
- get_answer(user_question): unchanged semantics (uses Google embeddings & Gemini).
- translate_text(text, target_language_code): uses Sarvam translate (same as before).
- answer_from_transcript(transcript_text, target_lang_code='en-IN'):
    runs get_answer() and then translates if requested.
"""
import os
import io
import json
import asyncio
from dotenv import load_dotenv

# Langchain & Google imports (same as before)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate

# Sarvam (for translation)
from sarvamai import SarvamAI

# -------------------- Load API Keys & event loop fix --------------------
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Ensure asyncio loop exists in this thread (fix for grpc.aio)
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Configure clients (no direct google.generativeai import/config needed)
client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

# Language map (same mapping as your old UI)
LANGUAGES = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Gujarati": "gu-IN",
    "Bengali": "bn-IN",
    "Kannada": "kn-IN",
    "Punjabi": "pa-IN"
}

# -------------------- RAG functions (keep logic unchanged) --------------------
def get_conversational_chain():
    prompt_template = """
    Answer the question as detailed as possible from the provided context. 
    If the answer is not in context, just say "answer is not available in the context".
    
    Context:\n{context}\n
    Question:\n{question}\n
    Answer:
    """
    model = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)
    prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
    chain = load_qa_chain(model, chain_type="stuff", prompt=prompt)
    return chain

def get_answer(user_question):
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    # safest and OS-independent
    index_path = os.path.join("chatbot_sih", "faiss_index")

    # Check if FAISS index exists
    if not os.path.exists(index_path) or not os.path.exists(os.path.join(index_path, "index.faiss")):
        return "⚠️ No knowledge base found. Please upload and process PDFs first."

    try:
        db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        docs = db.similarity_search(user_question)
        if not docs:
            return "⚠️ No relevant information found in the knowledge base."
        chain = get_conversational_chain()
        response = chain({"input_documents": docs, "question": user_question}, return_only_outputs=True)
        return response.get("output_text", "⚠️ No answer generated.")
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg and "quota" in error_msg:
            return ("⚠️ Gemini API quota exceeded. Please wait for your quota to reset or add a new API key. "
                    "See https://ai.google.dev/gemini-api/docs/rate-limits for details.")
        return f"⚠️ Error retrieving answer: {e}"

# -------------------- Translation helper (Sarvam) --------------------
def translate_text(text: str, target_language_code: str, source_language_code: str = "en-IN"):
    if not text:
        return text
    if not SARVAM_API_KEY:
        # no API key; return original
        return text
    try:
        # Keep same call pattern as your original UI
        translation = client.text.translate(
            input=text,
            source_language_code=source_language_code,
            target_language_code=target_language_code,
            speaker_gender="Male"
        )
        # translation may be object-like; handle safely
        return getattr(translation, "translated_text", translation if isinstance(translation, str) else str(translation))
    except Exception as e:
        # If translation fails, return original text
        print("[rag] Translation failed:", e)
        return text

# -------------------- High-level: answer from transcript --------------------
TRANSCRIPTS_DIR = os.path.join(os.getcwd(), "transcripts")
LATEST_ANSWER_PATH = os.path.join(TRANSCRIPTS_DIR, "latest_answer.txt")
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def answer_from_transcript(transcript_text: str, target_language_code: str = "en-IN") -> str:
    """
    Run get_answer(transcript_text), then translate the answer into target_language_code
    if requested (target != 'en-IN'). Save final answer to transcripts/latest_answer.txt.
    """
    if not transcript_text:
        msg = "⚠️ Empty transcript."
        with open(LATEST_ANSWER_PATH, "w", encoding="utf-8") as f:
            f.write(msg)
        return msg

    answer_en = get_answer(transcript_text)
    final_answer = answer_en
    if answer_en and not answer_en.startswith("⚠️") and target_language_code != "en-IN":
        final_answer = translate_text(answer_en, target_language_code, source_language_code="en-IN")

    # Save answer
    try:
        with open(LATEST_ANSWER_PATH, "w", encoding="utf-8") as f:
            f.write(final_answer)
    except Exception as e:
        print("[rag] Could not save answer:", e)

    return final_answer

# CLI for direct usage of rag.py (optional)
if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser(description="rag.py (no UI) — process a transcript file")
    parser.add_argument("--file", "-f", default=os.path.join(TRANSCRIPTS_DIR, "latest_transcript.txt"), help="Transcript file path")
    parser.add_argument("--target", "-t", default="en-IN", help="Target language code for final answer (e.g., hi-IN). Default en-IN (no translation).")
    parser.add_argument("--mode", choices=("once","watch"), default="once", help="once=process once; watch=poll file")
    parser.add_argument("--poll", type=float, default=1.0, help="poll interval when watch mode")
    args = parser.parse_args()

    def process_once(path, target):
        if not os.path.exists(path):
            print("Transcript file not found:", path)
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        print("Transcript read (len={}):".format(len(txt)))
        ans = answer_from_transcript(txt, target_language_code=args.target)
        print("Answer:\n", ans)

    if args.mode == "once":
        process_once(args.file, args.target)
    else:
        last_mtime = None
        print("Watching", args.file)
        try:
            while True:
                if os.path.exists(args.file):
                    mtime = os.path.getmtime(args.file)
                    if last_mtime is None or mtime != last_mtime:
                        last_mtime = mtime
                        process_once(args.file, args.target)
                import time; time.sleep(args.poll)
        except KeyboardInterrupt:
            print("Stopped.")
