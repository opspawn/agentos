"""Shared test configuration.

Forces mock model provider for all tests so integration tests
don't depend on Ollama or Azure being available.

Uses a temporary SQLite database for each test session so tests
don't pollute the production database.
"""

import os
import tempfile

import pytest

# Force mock provider before any module imports config
os.environ["MODEL_PROVIDER"] = "mock"

# Use a temporary database for tests
_test_db_dir = tempfile.mkdtemp()
_test_db_path = os.path.join(_test_db_dir, "test_hirewire.db")
os.environ["HIREWIRE_DB_PATH"] = _test_db_path


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear cached settings so each test gets fresh config."""
    from src.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_storage():
    """Reset the SQLite storage between tests to prevent cross-contamination."""
    import src.storage as storage_mod

    # Reset the global storage singleton with a fresh temp DB per test
    test_db = os.path.join(_test_db_dir, f"test_{os.getpid()}.db")
    storage_mod._storage = storage_mod.SQLiteStorage(test_db)
    yield
    # Clean up after test
    storage_mod._storage = storage_mod.SQLiteStorage(test_db)
