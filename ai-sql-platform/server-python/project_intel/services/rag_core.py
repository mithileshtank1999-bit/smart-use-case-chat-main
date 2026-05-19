from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math
import re
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    text: str
    metadata: dict[str, Any]


def make_json_safe(value: Any):
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1]


def parse_project_name_from_query(query: str) -> str:
    try:
        match = re.search(r"for\s+project\s+(.+?)(?:[\.\n\r]|$)", query or "", flags=re.IGNORECASE)
        return (match.group(1) if match else "").strip().strip('"').strip("'")
    except Exception:
        return ""


def safe_get(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return str(row.get(key))
        lower_key = key.lower()
        for actual in row.keys():
            if str(actual).lower() == lower_key and row.get(actual) not in (None, ""):
                return str(row.get(actual))
    return ""


def chunk_project_row(row: dict) -> list[RagDocument]:
    safe_row = make_json_safe(row or {})
    project_id = safe_get(safe_row, "project_id", "projectid")
    project_name = safe_get(safe_row, "project_name", "projectname")
    status = safe_get(safe_row, "status", "statuscode", "statusid", "statuscodeid")
    portfolio = safe_get(safe_row, "portfolio_name", "portfolio")
    owner = safe_get(safe_row, "portfolio_owner")
    pm = safe_get(safe_row, "project_manager", "pm")
    account = safe_get(safe_row, "account_name", "customer_name")

    base_meta = {
        "project_id": project_id,
        "project_name": project_name,
        "status": status,
        "portfolio": portfolio,
        "portfolio_owner": owner,
        "project_manager": pm,
        "account_name": account,
    }

    docs: list[RagDocument] = []

    timeline_lines = [
        f"Project: {project_name} ({project_id})",
        f"Status: {status}" if status else "",
        f"Project Start Date: {safe_get(safe_row, 'start_date', 'startdate') or 'Not available'}",
        f"FSD Sign Off: {safe_get(safe_row, 'fsd_sign_off', 'fsd_signoff', 'fsd_sign_off_date', 'fsd_signoff_date') or 'Not available'}",
        f"Development Phase: {safe_get(safe_row, 'dev_start_date') or 'Not available'} → {safe_get(safe_row, 'dev_end_date') or 'Not available'}",
        f"SIT Phase: {safe_get(safe_row, 'sit_start_date') or 'Not available'} → {safe_get(safe_row, 'sit_end_date') or 'Not available'}",
        f"UAT Phase: {safe_get(safe_row, 'uat_start_date') or 'Not available'} → {safe_get(safe_row, 'uat_end_date') or 'Not available'}",
        f"Go-Live Date: {safe_get(safe_row, 'go_live_date', 'end_date', 'enddate') or 'Not available'}",
    ]
    timeline_text = normalize_text("\n".join([l for l in timeline_lines if l]))
    docs.append(
        RagDocument(
            doc_id=f"{project_id or project_name}:timeline",
            text=timeline_text,
            metadata={**base_meta, "chunk_type": "milestone"},
        )
    )

    risk_statement = safe_get(safe_row, "risk_statement", "risk", "risks")
    severity = safe_get(safe_row, "severity", "risk_level")
    impact = safe_get(safe_row, "impact")
    if any([risk_statement, severity, impact]):
        risk_text = normalize_text(
            "\n".join(
                [
                    f"Project: {project_name} ({project_id})",
                    f"Risk Statement: {risk_statement}" if risk_statement else "",
                    f"Severity: {severity}" if severity else "",
                    f"Impact: {impact}" if impact else "",
                ]
            )
        )
        docs.append(
            RagDocument(
                doc_id=f"{project_id or project_name}:risk",
                text=risk_text,
                metadata={**base_meta, "chunk_type": "risk"},
            )
        )

    schedule = safe_get(safe_row, "schedule_health")
    financial = safe_get(safe_row, "financial_health")
    delivery = safe_get(safe_row, "delivery_progress", "completion")
    overall = safe_get(safe_row, "health", "overall_health")
    if any([schedule, financial, delivery, overall, status]):
        health_text = normalize_text(
            "\n".join(
                [
                    f"Project: {project_name} ({project_id})",
                    f"Status: {status}" if status else "",
                    f"Overall Health: {overall}" if overall else "",
                    f"Schedule Health: {schedule}" if schedule else "",
                    f"Financial Health: {financial}" if financial else "",
                    f"Delivery Progress: {delivery}" if delivery else "",
                ]
            )
        )
        docs.append(
            RagDocument(
                doc_id=f"{project_id or project_name}:health",
                text=health_text,
                metadata={**base_meta, "chunk_type": "health"},
            )
        )

    hod = safe_get(safe_row, "hod")
    svp = safe_get(safe_row, "svp")
    action_owner = safe_get(safe_row, "action_owner")
    if any([pm, hod, svp, owner, action_owner, account, portfolio]):
        gov_text = normalize_text(
            "\n".join(
                [
                    f"Project: {project_name} ({project_id})",
                    f"Account: {account}" if account else "",
                    f"Portfolio: {portfolio}" if portfolio else "",
                    f"Portfolio Owner: {owner}" if owner else "",
                    f"Project Manager: {pm}" if pm else "",
                    f"HOD: {hod}" if hod else "",
                    f"SVP: {svp}" if svp else "",
                    f"Action Owner: {action_owner}" if action_owner else "",
                ]
            )
        )
        docs.append(
            RagDocument(
                doc_id=f"{project_id or project_name}:governance",
                text=gov_text,
                metadata={**base_meta, "chunk_type": "governance"},
            )
        )

    return docs


def _flatten_meta(meta: dict) -> dict:
    """Coerce metadata values to ChromaDB-compatible types (str/int/float/bool)."""
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


class LocalSentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Missing dependency: sentence-transformers. Install it (and a backend like torch) to enable embeddings."
            ) from exc
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def dim(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]


class HybridRagIndex:
    def __init__(self, embedder: LocalSentenceTransformerEmbedder):
        self._embedder = embedder
        self._docs: list[RagDocument] = []
        self._doc_vectors: list[list[float]] = []
        self._token_sets: list[set[str]] = []
        self._faiss_index = None

    @property
    def size(self) -> int:
        return len(self._docs)

    def clear(self):
        self._docs = []
        self._doc_vectors = []
        self._token_sets = []
        self._faiss_index = None

    def add_documents(self, docs: list[RagDocument]):
        docs = [d for d in docs if d and d.text and d.text.strip()]
        if not docs:
            return

        vectors = self._embedder.embed([d.text for d in docs])
        self._docs.extend(docs)
        self._doc_vectors.extend(vectors)
        self._token_sets.extend([set(tokenize(d.text)) for d in docs])
        self._rebuild_faiss_if_available()

    def _rebuild_faiss_if_available(self):
        try:
            import faiss  # type: ignore
        except Exception:
            self._faiss_index = None
            return

        if not self._doc_vectors:
            self._faiss_index = None
            return

        import numpy as np  # type: ignore

        mat = np.array(self._doc_vectors, dtype="float32")
        index = faiss.IndexFlatIP(mat.shape[1])
        index.add(mat)
        self._faiss_index = index

    def _vector_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        if not self._docs:
            return []
        q_vec = self._embedder.embed([query])[0]

        if self._faiss_index is not None:
            import numpy as np  # type: ignore

            q = np.array([q_vec], dtype="float32")
            scores, indices = self._faiss_index.search(q, top_k)
            results: list[tuple[int, float]] = []
            for idx, score in zip(indices[0].tolist(), scores[0].tolist()):
                if idx < 0:
                    continue
                results.append((int(idx), float(score)))
            return results

        results: list[tuple[int, float]] = []
        for i, v in enumerate(self._doc_vectors):
            score = sum((a * b) for a, b in zip(q_vec, v))
            results.append((i, float(score)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _keyword_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        q_tokens = set(tokenize(query))
        if not q_tokens or not self._docs:
            return []
        scored: list[tuple[int, float]] = []
        for i, doc_tokens in enumerate(self._token_sets):
            overlap = len(q_tokens.intersection(doc_tokens))
            if overlap <= 0:
                continue
            score = 1.0 - math.exp(-overlap)
            scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        project_name: str | None = None,
        project_id: str | None = None,
        chunk_types: set[str] | None = None,
    ) -> list[RagDocument]:
        query = normalize_text(query)
        if not query:
            return []

        project_name = (project_name or "").strip()
        project_id = (project_id or "").strip()

        vec_hits = self._vector_search(query, top_k=top_k * 4)
        kw_hits = self._keyword_search(query, top_k=top_k * 4)

        combined_scores: dict[int, float] = {}
        for idx, score in vec_hits:
            combined_scores[idx] = max(combined_scores.get(idx, 0.0), score)
        for idx, score in kw_hits:
            combined_scores[idx] = max(combined_scores.get(idx, 0.0), 0.35 + 0.65 * score)

        ranked = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)

        results: list[RagDocument] = []
        for idx, _score in ranked:
            doc = self._docs[idx]
            meta = doc.metadata or {}
            if project_id and str(meta.get("project_id") or "").strip() != project_id:
                continue
            if project_name and project_name.lower() not in str(meta.get("project_name") or "").lower():
                continue
            if chunk_types and str(meta.get("chunk_type") or "") not in chunk_types:
                continue
            results.append(doc)
            if len(results) >= top_k:
                break
        return results


# ---------------------------------------------------------------------------
# ChromaDB persistent index (used when CHROMA_PERSIST_DIR is set)
# ---------------------------------------------------------------------------

class ChromaRagIndex:
    """
    Persistent RAG index backed by ChromaDB.
    Implements the same interface as HybridRagIndex so rag_service.py can
    swap between the two without any other changes.

    Activate by setting the CHROMA_PERSIST_DIR environment variable to a
    writable directory path (e.g. /data/chroma or ./chroma_store).
    """

    _COLLECTION_NAME = "project_rag"

    def __init__(self, persist_dir: str, embedder: LocalSentenceTransformerEmbedder):
        try:
            import chromadb  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: chromadb. "
                "Install it with: pip install 'chromadb>=0.5.0'"
            ) from exc

        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self._COLLECTION_NAME,
            # "ip" (inner product) matches cosine similarity when vectors are
            # L2-normalised — which SentenceTransformer does by default.
            metadata={"hnsw:space": "ip"},
        )

    @property
    def size(self) -> int:
        return self._collection.count()

    def clear(self):
        self._client.delete_collection(self._COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self._COLLECTION_NAME,
            metadata={"hnsw:space": "ip"},
        )

    def add_documents(self, docs: list[RagDocument]):
        docs = [d for d in docs if d and d.text and d.text.strip()]
        if not docs:
            return
        vectors = self._embedder.embed([d.text for d in docs])
        self._collection.upsert(
            ids=[d.doc_id for d in docs],
            embeddings=vectors,
            documents=[d.text for d in docs],
            metadatas=[_flatten_meta(d.metadata) for d in docs],
        )

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        project_name: str | None = None,
        project_id: str | None = None,
        chunk_types: set[str] | None = None,
    ) -> list[RagDocument]:
        query = normalize_text(query)
        if not query or self.size == 0:
            return []

        q_vec = self._embedder.embed([query])[0]

        where: dict | None = None
        if chunk_types:
            types = list(chunk_types)
            where = {"chunk_type": types[0]} if len(types) == 1 else {"chunk_type": {"$in": types}}

        n_results = min(top_k * 4, self.size)
        kwargs: dict = dict(
            query_embeddings=[q_vec],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        ids_list = (raw.get("ids") or [[]])[0]
        docs_list = (raw.get("documents") or [[]])[0]
        metas_list = (raw.get("metadatas") or [[]])[0]

        results: list[RagDocument] = []
        for doc_id, text, meta in zip(ids_list, docs_list, metas_list):
            meta = meta or {}
            if project_id and str(meta.get("project_id") or "").strip() != project_id:
                continue
            if project_name and project_name.lower() not in str(meta.get("project_name") or "").lower():
                continue
            results.append(RagDocument(doc_id=doc_id, text=text or "", metadata=meta))
            if len(results) >= top_k:
                break
        return results
