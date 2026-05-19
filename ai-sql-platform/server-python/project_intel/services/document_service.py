from __future__ import annotations

"""
Document upload pipeline: extract → chunk → embed → store → search.

Supported formats: .txt, .pdf (requires pypdf), .docx (requires python-docx).
Storage backend: ChromaDB if CHROMA_PERSIST_DIR is set, otherwise in-memory.
"""

import io
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_meta(meta: dict) -> dict:
    flat: dict = {}
    for k, v in (meta or {}).items():
        if isinstance(v, bool):
            flat[k] = v
        elif isinstance(v, (int, float)):
            flat[k] = v
        elif v is None:
            flat[k] = ""
        else:
            flat[k] = str(v)
    return flat


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_pages(content: bytes, filename: str) -> list[tuple[str, int]]:
    """
    Returns list of (page_text, page_number) tuples.
    Non-paginated formats return a single entry with page_number=0.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".txt":
        return [(content.decode("utf-8", errors="replace"), 0)]

    if ext == ".pdf":
        try:
            import pypdf  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "pypdf is required for PDF support. Install: pip install 'pypdf>=4.0.0'"
            ) from exc
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages: list[tuple[str, int]] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append((text, i + 1))
        return pages or [("", 0)]

    if ext == ".docx":
        try:
            import docx  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "python-docx is required for DOCX support. Install: pip install 'python-docx>=1.1.0'"
            ) from exc
        doc = docx.Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return [(text, 0)]

    # Unknown type — try UTF-8 decode
    try:
        return [(content.decode("utf-8", errors="replace"), 0)]
    except Exception:
        raise ValueError(f"Unsupported file type: {ext!r}")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", "600") or "600")
_CHUNK_OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", "100") or "100")


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) <= chunk_size:
                tail = chunks[-1][-overlap:] if chunks else ""
                current = (tail + "\n\n" + para).strip() if tail else para
            else:
                # Paragraph itself exceeds chunk_size — hard split
                for i in range(0, len(para), chunk_size - overlap):
                    sub = para[i : i + chunk_size].strip()
                    if sub:
                        chunks.append(sub)
                current = ""

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Document store
# ---------------------------------------------------------------------------

class _DocumentStore:
    """
    Thin wrapper that stores document chunks in ChromaDB (persistent) or
    an in-memory list (fallback). Both expose the same public API.
    """

    _COLLECTION = "documents"

    def __init__(self, embedder: Any):
        self._embedder = embedder
        self._chroma = None
        self._mem: list[dict] = []

        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "").strip()
        if persist_dir:
            try:
                import chromadb  # type: ignore[import]
                client = chromadb.PersistentClient(path=persist_dir)
                self._chroma = client.get_or_create_collection(
                    name=self._COLLECTION,
                    metadata={"hnsw:space": "ip"},
                )
                logger.info("DocumentStore: ChromaDB at %s (chunks=%d)", persist_dir, self._chroma.count())
            except Exception as exc:
                logger.warning("DocumentStore: ChromaDB unavailable (%s), using in-memory", exc)

    # ---- write ----

    def add(self, chunks: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not chunks:
            return
        vectors = self._embedder.embed(chunks)
        if self._chroma is not None:
            self._chroma.upsert(
                ids=ids,
                embeddings=vectors,
                documents=chunks,
                metadatas=[_flatten_meta(m) for m in metadatas],
            )
        else:
            for chunk_id, text, vec, meta in zip(ids, chunks, vectors, metadatas):
                self._mem.append({"id": chunk_id, "text": text, "vector": vec, "meta": meta})

    def delete(self, doc_id: str) -> int:
        if self._chroma is not None:
            raw = self._chroma.get(where={"doc_id": doc_id})
            chunk_ids = raw.get("ids") or []
            if chunk_ids:
                self._chroma.delete(ids=chunk_ids)
            return len(chunk_ids)
        before = len(self._mem)
        self._mem = [i for i in self._mem if i["meta"].get("doc_id") != doc_id]
        return before - len(self._mem)

    # ---- read ----

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self._chroma is not None:
            count = self._chroma.count()
            if count == 0:
                return []
            q_vec = self._embedder.embed([query])[0]
            raw = self._chroma.query(
                query_embeddings=[q_vec],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )
            ids = (raw.get("ids") or [[]])[0]
            docs = (raw.get("documents") or [[]])[0]
            metas = (raw.get("metadatas") or [[]])[0]
            return [{"id": i, "text": t, "meta": m or {}} for i, t, m in zip(ids, docs, metas)]
        if not self._mem:
            return []
        q_vec = self._embedder.embed([query])[0]
        scored = [(sum(a * b for a, b in zip(q_vec, item["vector"])), item) for item in self._mem]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": i["id"], "text": i["text"], "meta": i["meta"]} for _, i in scored[:top_k]]

    def list_documents(self) -> list[dict]:
        if self._chroma is not None:
            raw = self._chroma.get(include=["metadatas"])
            metas = raw.get("metadatas") or []
            ids = raw.get("ids") or []
        else:
            metas = [i["meta"] for i in self._mem]
            ids = [i["id"] for i in self._mem]

        docs: dict[str, dict] = {}
        for _chunk_id, meta in zip(ids, metas):
            doc_id = str(meta.get("doc_id") or "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", ""),
                    "file_type": meta.get("file_type", ""),
                    "uploaded_at": meta.get("uploaded_at", ""),
                    "chunks": 0,
                }
            docs[doc_id]["chunks"] += 1
        return list(docs.values())

    @property
    def total_chunks(self) -> int:
        if self._chroma is not None:
            return self._chroma.count()
        return len(self._mem)


# ---------------------------------------------------------------------------
# Singleton store (lazy-initialised on first use)
# ---------------------------------------------------------------------------

_STORE: _DocumentStore | None = None
_STORE_ERROR: str | None = None


def _get_store() -> _DocumentStore | None:
    global _STORE, _STORE_ERROR
    if _STORE is not None:
        return _STORE
    if _STORE_ERROR:
        return None
    try:
        from project_intel.core.config import EMBEDDING_MODEL_NAME
        from project_intel.services.rag_core import LocalSentenceTransformerEmbedder
        embedder = LocalSentenceTransformerEmbedder(EMBEDDING_MODEL_NAME)
        _STORE = _DocumentStore(embedder)
        return _STORE
    except Exception as exc:
        _STORE_ERROR = str(exc)
        logger.error("DocumentStore init failed: %s", _STORE_ERROR)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_document(filename: str, content: bytes) -> dict:
    """Extract, chunk, embed, and persist a document. Returns upload metadata."""
    store = _get_store()
    if store is None:
        raise RuntimeError(_STORE_ERROR or "Document store unavailable (sentence-transformers not installed?)")

    pages = _extract_pages(content, filename)
    if not any(text.strip() for text, _ in pages):
        raise ValueError("No text could be extracted from the document.")

    doc_id = str(uuid.uuid4())
    uploaded_at = datetime.utcnow().isoformat()
    ext = os.path.splitext(filename)[1].lower().lstrip(".")

    all_chunks: list[str] = []
    all_metas: list[dict] = []
    all_ids: list[str] = []

    for page_text, page_num in pages:
        for i, chunk in enumerate(_chunk_text(page_text)):
            all_chunks.append(chunk)
            all_metas.append({
                "doc_id": doc_id,
                "filename": filename,
                "file_type": ext,
                "page": page_num,
                "chunk_index": i,
                "uploaded_at": uploaded_at,
            })
            all_ids.append(f"{doc_id}:{page_num}:{i}")

    if not all_chunks:
        raise ValueError("Document produced no usable text chunks.")

    store.add(all_chunks, all_metas, all_ids)

    return {
        "ok": True,
        "doc_id": doc_id,
        "filename": filename,
        "file_type": ext,
        "pages": len(pages),
        "chunks": len(all_chunks),
        "uploaded_at": uploaded_at,
    }


def search_documents(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over all uploaded document chunks."""
    store = _get_store()
    if store is None or store.total_chunks == 0:
        return []
    return store.search(query, top_k=top_k)


def list_documents() -> list[dict]:
    """Return one entry per uploaded document with its chunk count."""
    store = _get_store()
    if store is None:
        return []
    return store.list_documents()


def delete_document(doc_id: str) -> int:
    """Delete all chunks for a document. Returns number of chunks removed."""
    store = _get_store()
    if store is None:
        return 0
    return store.delete(doc_id)


def answer_from_documents(query: str, hits: list[dict]) -> str | None:
    """Ask the LLM to answer a question using document chunks as context."""
    if not hits:
        return None
    try:
        from project_intel.core.config import OPENAI_MODEL
        from project_intel.core.openai_client import get_openai_clients
        clients = get_openai_clients()
        if not clients:
            return None

        context = "\n\n---\n\n".join(
            f"[{h['meta'].get('filename', '')} p.{h['meta'].get('page', '')}]\n{h['text']}"
            for h in hits
        )
        prompt = (
            "You are a helpful assistant. Answer the user's question using ONLY the document excerpts below. "
            "If the answer is not in the excerpts, say so clearly.\n\n"
            f"Document excerpts:\n{context}\n\n"
            f"Question: {query}"
        )

        for client in clients:
            try:
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}],
                )
                return (resp.choices[0].message.content or "").strip() or None
            except Exception:
                continue
    except Exception as exc:
        logger.warning("answer_from_documents failed: %s", exc)
    return None
