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
from functools import lru_cache
from dotenv import load_dotenv
from typing import List, Tuple, Dict, Any

# Langchain & Google imports (same as before)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
try:
    from sentence_transformers import CrossEncoder  # optional reranker
except Exception:  # pragma: no cover
    CrossEncoder = None

# Sarvam (for translation)
from sarvamai import SarvamAI

# -------------------- Load API Keys & event loop fix --------------------
load_dotenv()
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("openai_api_key")

# Ensure asyncio loop exists in this thread (fix for grpc.aio)
try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Configure clients (no direct google.generativeai import/config needed)
client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

# -------------------- Globals for reused models/index --------------------
_EMBEDDINGS = None  # type: Any
_DB = None  # type: Any
_CROSS = None  # type: Any
INDEX_PATH = os.path.join("chatbot_sih", "faiss_index")

# Language map (same mapping as your old UI)
LANGUAGES = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Gujarati": "gu-IN",
    "Bengali": "bn-IN",
    "Kannada": "kn-IN",
    "Punjabi": "pa-IN"
}

# Light-weight synonyms to improve recall (can be extended)
SYNONYMS = {
    "mba": ["master of business administration", "mba program"],
    "bba": ["bachelor of business administration", "bba program"],
    "bca": ["bachelor of computer applications", "bca program"],
    "mca": ["master of computer applications", "mca program"],
    "fees": ["fee", "tuition", "fee structure", "tuition fees"],
    "scholarship": ["scholarships", "financial aid", "fee waiver"],
}

# -------------------- RAG functions (keep logic unchanged) --------------------
def get_conversational_chain():
    prompt_template = ChatPromptTemplate.from_template("""
    You are a helpful university information assistant.
    Use the provided context to answer the user's question concisely and helpfully.
    If the context partially answers the question, synthesize the best possible answer and say what is unknown.
    Only if nothing relevant is in context, reply exactly: "answer is not available in the context".

    Include a short Sources: section listing source_file names you used if available.

    Context:\n{context}\n
    Question:\n{question}\n
    Answer:
    """)
    model = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)
    chain = prompt_template | model | StrOutputParser()
    return chain

def _format_context(docs: List):
    # Concatenate top documents into a single context string with source hints
    joined = []
    for d in docs[:4]:
        try:
            src = None
            try:
                src = d.metadata.get("source_file") if hasattr(d, "metadata") else None
            except Exception:
                src = None
            prefix = f"[source: {src}]\n" if src else ""
            joined.append(prefix + d.page_content)
        except Exception:
            joined.append(str(d))
    return "\n\n".join(joined)


def _doc_sources(docs: List) -> List[Dict[str, Any]]:
    sources = []
    seen = set()
    for d in docs:
        try:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source_file") or meta.get("source") or None
            if not src:
                continue
            if src in seen:
                continue
            seen.add(src)
            sources.append({"file": src})
        except Exception:
            continue
    return sources


def _load_embeddings_and_index():
    global _EMBEDDINGS, _DB
    if _EMBEDDINGS is None:
        _EMBEDDINGS = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-mpnet-base-v2")
    if _DB is None and os.path.exists(INDEX_PATH) and os.path.exists(os.path.join(INDEX_PATH, "index.faiss")):
        _DB = FAISS.load_local(INDEX_PATH, _EMBEDDINGS, allow_dangerous_deserialization=True)
    return _EMBEDDINGS, _DB


def _expand_queries(user_question: str) -> List[str]:
    q = (user_question or "").strip()
    if not q:
        return [q]
    variants = {q}
    q_lower = q.lower()
    for key, syns in SYNONYMS.items():
        if key in q_lower:
            for s in syns:
                variants.add(q_lower.replace(key, s))
    # basic punctuation/whitespace normalization
    variants.add(" ".join(q_lower.split()))
    return list(variants)[:6]


def _retrieve_documents(user_question: str) -> List:
    embeddings, db = _load_embeddings_and_index()
    if db is None:
        raise RuntimeError("No knowledge base found. Please upload and process PDFs first.")

    # Multi-query retrieval with diversity
    queries = _expand_queries(user_question)
    gathered: List = []
    for q in queries:
        try:
            gathered.extend(db.max_marginal_relevance_search(q, k=6, fetch_k=18))
        except Exception:
            gathered.extend(db.similarity_search(q, k=6))

    # Deduplicate by page content hash to avoid repeats
    seen = set()
    docs = []
    for d in gathered:
        key = getattr(d, "page_content", str(d))[:256]
        if key in seen:
            continue
        seen.add(key)
        docs.append(d)

    # Optional cross-encoder reranking (if available)
    global _CROSS
    if CrossEncoder is not None and docs:
        try:
            if _CROSS is None:
                _CROSS = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            pairs = [(user_question, getattr(d, "page_content", "")) for d in docs]
            scores = _CROSS.predict(pairs)
            docs = [d for _, d in sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)]
        except Exception:
            pass

    return docs[:10]


def _normalize_query_for_cache(q: str) -> str:
    return " ".join((q or "").strip().lower().split())


@lru_cache(maxsize=128)
def get_answer_with_sources(user_question: str) -> Tuple[str, List[Dict[str, Any]]]:
    try:
        docs = _retrieve_documents(user_question)
        if not docs:
            return "⚠ No relevant information found in the knowledge base.", []

        sources = _doc_sources(docs)

        # Primary path: Gemini via LangChain
        try:
            chain = get_conversational_chain()
            context_text = _format_context(docs)
            response = chain.invoke({"context": context_text, "question": user_question})
            return (response if response else "⚠ No answer generated.", sources)
        except Exception as gemini_err:
            gemini_msg = str(gemini_err)
            # Quota or missing key → fall back to OpenAI if configured
            if ("429" in gemini_msg or "quota" in gemini_msg.lower() or not GOOGLE_API_KEY) and OPENAI_API_KEY:
                try:
                    from openai import OpenAI
                    oai = OpenAI()
                    context_text = _format_context(docs)
                    system_prompt = (
                        "You are a helpful assistant. Answer the user's question using only the given context. "
                        "If the answer is not present, reply exactly: 'answer is not available in the context'."
                    )
                    user_prompt = f"Context:\n{context_text}\n\nQuestion:\n{user_question}\n\nAnswer:"
                    chat = oai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.3,
                    )
                    return (chat.choices[0].message.content.strip(), sources)
                except Exception as openai_err:
                    return ("⚠ Gemini unavailable and OpenAI fallback failed: " + str(openai_err), sources)

            # Otherwise, surface the Gemini error
            if "429" in gemini_msg and "quota" in gemini_msg.lower():
                return (
                    "⚠ Gemini API quota exceeded. Please wait for your quota to reset or add a new API key. See https://ai.google.dev/gemini-api/docs/rate-limits for details.",
                    sources,
                )
            return (f"⚠ Error from Gemini: {gemini_err}", sources)
    except Exception as e:
        return (f"⚠ Error retrieving answer: {e}", [])


def get_answer(user_question: str) -> str:
    # Backward-compatible wrapper that drops sources
    answer, _ = get_answer_with_sources(user_question)
    return answer

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
        msg = "⚠ Empty transcript."
        with open(LATEST_ANSWER_PATH, "w", encoding="utf-8") as f:
            f.write(msg)
        return msg

    answer_en = get_answer(transcript_text)
    final_answer = answer_en
    if answer_en and not answer_en.startswith("⚠") and target_language_code != "en-IN":
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