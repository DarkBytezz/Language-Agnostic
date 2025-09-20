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
load_dotenv(dotenv_path=os.path.join(BASE_DIR, "chatbot_sih", ".env"))

# === Mount static folders ===
app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")
app.mount("/img", StaticFiles(directory=os.path.join(BASE_DIR, "img")), name="img")
app.mount("/html", StaticFiles(directory=os.path.join(BASE_DIR, "html")), name="html")

# simple logger helper
def _log(msg: str):
    print(f"[server] {msg}")

# === Index route (serve main html) ===
@app.get("/")
async def index():
    """
    Serve the main UI. Default to index1.html (your actual front page).
    Falls back to index2.html and index.html if index1 is missing.
    """
    try_names = ("index1.html", "index2.html", "index.html")
    for fname in try_names:
        fp = os.path.join(BASE_DIR, "html", fname)
        if os.path.exists(fp):
            _log(f"Serving homepage file: html/{fname}")
            return FileResponse(fp)
    _log("No homepage file found under html/ (tried index1, index2, index).")
    raise HTTPException(status_code=404, detail="Main page not found")

# === Dynamic page route ===
@app.get("/{page_name}")
async def serve_page(page_name: str):
    """
    Serve pages from html/<page_name>.html.
    Accepts both /mba and /mba.html requests.
    """
    if page_name.endswith(".html"):
        page_name = page_name[:-5]
    file_path = os.path.join(BASE_DIR, "html", f"{page_name}.html")
    if os.path.exists(file_path):
        _log(f"Serving page: html/{page_name}.html")
        return FileResponse(file_path)
    _log(f"Page not found requested: {page_name}")
    raise HTTPException(status_code=404, detail="Page not found")

# === Keyword → page mapping ===
KEYWORD_ROUTES = {
    "mba": "mba.html",
    "mca": "mca.html",
    "bba": "bba.html",
    "bca": "bca.html",
    "ma": "ma.html",
    "ba": "ba.html",
    "scholarship": "index4.html",
    "courses": "index3.html"
}

def check_keywords_and_redirect(query: str):
    """
    Check if query contains any keyword and return a canonical redirect URL.
    Returns e.g. "/mba" (NOT "/mba.html").
    """
    q_lower = (query or "").lower()
    for key, page in KEYWORD_ROUTES.items():
        if key in q_lower:
            return f"/{page.replace('.html', '')}"
    return None

# === Transcribe audio endpoint (STT + RAG) ===
@app.post("/record_and_transcribe/")
async def record_and_transcribe_endpoint(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        suffix = os.path.splitext(file.filename or "upload")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as fh:
            sarvam_resp = stt_module.transcribe_with_sarvam(fh, language_code="unknown")

        transcript = stt_module.extract_transcript(sarvam_resp)
        detected_lang = stt_module.extract_detected_language(sarvam_resp) or "en-IN"

        if not transcript:
            os.remove(tmp_path)
            return JSONResponse({"error": "No transcript returned by STT", "raw": str(sarvam_resp)})

        final_answer = rag_module.answer_from_transcript(transcript, target_language_code=detected_lang)
        os.remove(tmp_path)

        redirect_url = check_keywords_and_redirect(transcript)
        if redirect_url:
            return JSONResponse({
                "transcript": transcript,
                "answer": final_answer,
                "redirect": redirect_url,
                "detected_language": detected_lang
            })

        return JSONResponse({
            "transcript": transcript,
            "answer": final_answer,
            "detected_language": detected_lang
        })
    except Exception as e:
        _log(f"Error in record_and_transcribe: {e}")
        return JSONResponse({"error": str(e)})

# === Chatbot endpoint (RAG-only route) ===
@app.post("/ask_bot/")
async def ask_bot(query: str = Form(...)):
    try:
        _log(f"[ask_bot] Query: {query}")
        answer = rag_module.get_answer(query)

        redirect_url = check_keywords_and_redirect(query)
        if redirect_url:
            return JSONResponse({"answer": answer, "redirect": redirect_url})

        return JSONResponse({"answer": answer})
    except Exception as e:
        _log(f"Error in ask_bot: {e}")
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