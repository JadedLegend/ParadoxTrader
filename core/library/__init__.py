"""Bounded, local retrieval of the explicitly imported shared source corpus."""
from pathlib import Path
import threading

from .store import LibraryStore, LibraryUnavailable

__all__ = ["LibraryStore", "LibraryUnavailable", "get_library"]

_store = None
_research_store = None
_store_lock = threading.Lock()


def get_library(room: str = "writings") -> LibraryStore:
    """Construct the default store only on demand; index construction is lazy too.

    A cached instance is safe: every retrieval checks the actual corpus hash.
    Importing this package does not initialize application or agent stores.
    """
    if room not in ("writings", "research"):
        raise ValueError("Unknown library room")
    global _store, _research_store
    with _store_lock:
        if room == "research":
            if _research_store is None:
                from core.data_dir import db_path
                corpus_path = Path(__file__).resolve().parents[2] / "library" / "research-corpus.json"
                _research_store = LibraryStore(corpus_path, db_path("library_research.sqlite3"))
            return _research_store
        if _store is None:
            from core.data_dir import db_path
            corpus_path = Path(__file__).resolve().parents[2] / "library" / "corpus.json"
            _store = LibraryStore(corpus_path, db_path("library.sqlite3"))
        return _store
