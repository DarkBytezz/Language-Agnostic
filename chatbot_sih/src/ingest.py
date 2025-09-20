#!/usr/bin/env python3
"""
Local ingest -> FAISS using sentence-transformers (no external APIs).
This version uses the langchain_community SentenceTransformerEmbeddings wrapper and
FAISS.from_documents(..., embedding=...) so it is compatible with your langchain_community version.
"""

import os
import json
from typing import List
from pathlib import Path

# sentence-transformers will be used via the langchain wrapper (no manual encode needed)
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

# === CONFIG ===
BASE_DIR = Path.cwd()
PDF_DIR = BASE_DIR / "chatbot_sih" / "pdfs"
INDEX_DIR = BASE_DIR / "chatbot_sih" / "faiss_index"

# model choices: small -> fast, larger -> better quality (more RAM/time)
MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"   # you used this and it works for you
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120
BATCH_SIZE = 64   # used by the wrapper internally (if supported)

def find_pdfs(pdf_dir: Path) -> List[Path]:
    return sorted([p for p in pdf_dir.iterdir() if p.suffix.lower() == ".pdf"])

def load_and_split(pdf_path: Path, splitter: RecursiveCharacterTextSplitter) -> List[Document]:
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    chunks = splitter.split_documents(pages)
    # attach source filename in metadata for traceability
    for c in chunks:
        c.metadata = dict(c.metadata or {})
        c.metadata["source_file"] = pdf_path.name
    return chunks

def save_metadata_docs(docs: List[Document], meta_path: Path):
    meta_list = [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta_list, f, ensure_ascii=False)

def main():
    print("[ingest] Using local embeddings via SentenceTransformerEmbeddings (langchain_community).")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = find_pdfs(PDF_DIR)
    if not pdfs:
        print(f"[ingest] No PDFs found in {PDF_DIR}. Place files there and re-run.")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    all_chunks: List[Document] = []
    for p in pdfs:
        print(f"[ingest] Loading {p} ...")
        chunks = load_and_split(p, splitter)
        all_chunks.extend(chunks)

    print(f"[ingest] Total chunks: {len(all_chunks)}")

    # Create the langchain/community wrapper that internally uses sentence-transformers
    print(f"[ingest] Creating embeddings wrapper using model: {MODEL_NAME} ...")
    emb_wrapper = SentenceTransformerEmbeddings(model_name=MODEL_NAME)

    # Build FAISS index; LangChain will compute embeddings in a memory-friendly way internally.
    print("[ingest] Building FAISS index (LangChain will compute embeddings)...")
    faiss_db = FAISS.from_documents(all_chunks, embedding=emb_wrapper)

    # Save index and metadata
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss_db.save_local(str(INDEX_DIR))
    print(f"[ingest] FAISS index saved to {INDEX_DIR}")

    meta_path = INDEX_DIR / "docs_metadata.json"
    save_metadata_docs(all_chunks, meta_path)
    print(f"[ingest] Saved docs metadata to {meta_path}")
    print("[ingest] Done.")

if __name__ == "__main__":
    main()