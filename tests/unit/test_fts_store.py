"""Tests for SQLite FTS5 Memory Store."""
import pytest
from agent.memory.fts_store import SQLiteFTSStore, SearchResult


def test_fts_store_basic_add_and_search():
    store = SQLiteFTSStore(db_path=":memory:")
    store.add_entry(category="fact", title="Python Version", content="Project requires Python 3.11 or higher")
    store.add_entry(category="bugfix", title="Timeout Fix", content="Increased connect timeout to 60 seconds")

    results = store.search("Python")
    assert len(results) >= 1
    assert "Python Version" in [r.title for r in results]

    results_timeout = store.search("timeout")
    assert len(results_timeout) >= 1
    assert "Timeout Fix" in [r.title for r in results_timeout]
    store.close()


def test_fts_store_interaction_indexing():
    store = SQLiteFTSStore(db_path=":memory:")
    store.add_interaction("bagaimana cara deploy aplikasi?", "Gunakan perintah git push dan jalankan server.")

    results = store.search("deploy")
    assert len(results) >= 1
    assert "deploy" in results[0].content.lower()
    store.close()


def test_fts_store_recent_and_count():
    store = SQLiteFTSStore(db_path=":memory:")
    store.add_fact("key1", "val1")
    store.add_fact("key2", "val2")
    assert store.count() == 2

    recent = store.get_recent(limit=10)
    assert len(recent) == 2
    store.close()
