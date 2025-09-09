# server.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import tempfile
import uvicorn
import os
from dotenv import load_dotenv

# Use the actual helper functions from your modules
from chatbot_sih.src import stt as stt_module
from chatbot_sih.src import rag as rag_module

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# load environment variables (keeps same behavior as your project)
# load_dotenv(dotenv_path=os.path.join(BASE_DIR, "chatbot_sih", ".env"))
load_dotenv()
# === Mount static folders (keep your project structure) ===
app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")
app.mount("/img", StaticFiles(directory=os.path.join(BASE_DIR, "img")), name="img")
app.mount("/html", StaticFiles(directory=os.path.join(BASE_DIR, "html")), name="html")

# === Index route (serve main html) ===
@app.get("/")
async def index():
    # serve index1.html if present, else index.html
    for fname in ("index1.html", "index.html"):
        fp = os.path.join(BASE_DIR, "html", fname)
        if os.path.exists(fp):
            return FileResponse(fp)
    raise HTTPException(status_code=404, detail="Main page not found")

# === Dynamic page route ===
@app.get("/{page_name}")
async def serve_page(page_name: str):
    file_path = os.path.join(BASE_DIR, "html", f"{page_name}.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Page not found")

# === Transcribe audio endpoint (STT + RAG) ===
@app.post("/record_and_transcribe/")
async def record_and_transcribe_endpoint(file: UploadFile = File(...)):
    """
    This endpoint expects an UploadFile from the browser (MediaRecorder blob).
    It:
      - saves the uploaded file to a temp path (preserving file extension if possible)
      - calls stt_module.transcribe_with_sarvam(file_like, language_code=...)
      - extracts transcript and detected language using helpers in stt_module
      - if transcript exists: passes it to rag_module.answer_from_transcript(...)
      - returns JSON { transcript, answer, detected_language } OR helpful error info
    """
    try:
        contents = await file.read()
        # preserve extension from uploaded filename (helps with codecs)
        suffix = os.path.splitext(file.filename or "upload")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Debug info: file size + content_type
        print(f"[record_and_transcribe] Saved uploaded file to {tmp_path} (size={os.path.getsize(tmp_path)} bytes, content_type={file.content_type})")

        # Open the uploaded file as binary and call the file-based transcribe function
        # (transcribe_with_sarvam expects a file-like object)
        with open(tmp_path, "rb") as fh:
            sarvam_resp = stt_module.transcribe_with_sarvam(fh, language_code="unknown")

        # Parse transcript and detected language using helpers from stt.py
        transcript = stt_module.extract_transcript(sarvam_resp)
        detected_lang = stt_module.extract_detected_language(sarvam_resp) or "en-IN"

        print(f"[record_and_transcribe] Sarvam raw response: {sarvam_resp}")
        print(f"[record_and_transcribe] Extracted transcript: {repr(transcript)}, detected_lang: {detected_lang}")

        if not transcript:
            # Return raw response to help frontend debug
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return JSONResponse({"error": "No transcript returned by STT", "raw": str(sarvam_resp)})

        # IMPORTANT: call the RAG function with the correct kwarg name
        # rag.answer_from_transcript(transcript_text, target_language_code=...)
        final_answer = rag_module.answer_from_transcript(transcript, target_language_code=detected_lang)

        # cleanup temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return JSONResponse({
            "transcript": transcript,
            "answer": final_answer,
            "detected_language": detected_lang
        })
    except Exception as e:
        print("[record_and_transcribe] ERROR:", e)
        return JSONResponse({"error": str(e)})

# === Chatbot endpoint (RAG-only route) ===
@app.post("/ask_bot/")
async def ask_bot(query: str = Form(...)):
    """
    Existing RAG-only endpoint that accepts text queries (no audio).
    Kept behavior similar to original — uses rag_module.get_answer.
    """
    try:
        print(f"[ask_bot] Query: {query}")
        answer = rag_module.get_answer(query)
        return JSONResponse({"answer": answer})
    except Exception as e:
        print(f"❌ Error in ask_bot: {e}")      # Debug log
        return JSONResponse({"error": str(e)})

# === Download TTS audio (kept for later use) ===
@app.get("/download_audio/{audio_file}")
async def download_audio(audio_file: str):
    file_path = os.path.join(BASE_DIR, "chatbot_sih", "data", "output_audio", audio_file)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/mpeg", filename=audio_file)
    return JSONResponse({"error": "File not found"}, status_code=404)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
