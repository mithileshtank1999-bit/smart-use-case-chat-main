"""
Compatibility wrapper for legacy imports.

`main.py` historically imported RAG helpers from a top-level `rag` module.
The implementation now lives under `project_intel.services.rag_core`.
"""

from project_intel.services.rag_core import (  # noqa: F401
    HybridRagIndex,
    LocalSentenceTransformerEmbedder,
    chunk_project_row,
    parse_project_name_from_query,
)

