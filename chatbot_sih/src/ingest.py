#!/usr/bin/env python3
"""
ingest.py — process all PDFs into a FAISS vectorstore
Usage:
  python ingest.py
"""

import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise SystemExit("⚠ Set GOOGLE_API_KEY in your .env")

PDF_DIR = os.path.join(os.getcwd(), "chatbot_sih", "pdfs")

INDEX_DIR = os.path.join(os.getcwd(), "chatbot_sih","faiss_index")

def ingest_pdfs():
    all_docs = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    for fname in os.listdir(PDF_DIR):
        if fname.lower().endswith(".pdf"):
            path = os.path.join(PDF_DIR, fname)
            print(f"[ingest] Loading {path} ...")
            loader = PyPDFLoader(path)
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            all_docs.extend(chunks)

    if not all_docs:
        print("⚠ No PDFs found.")
        return

    print(f"[ingest] Total chunks: {len(all_docs)}")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

    db = FAISS.from_documents(all_docs, embeddings)
    db.save_local(INDEX_DIR)
    print(f"[ingest] Saved FAISS index to {INDEX_DIR}")

if __name__ == "__main__":
    ingest_pdfs()
