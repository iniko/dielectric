"""Shared test fixtures for the backend API tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from backend.app.store import STORE


@pytest.fixture(autouse=True)
def _reset_store() -> Iterator[None]:
    """Isolate every test: the in-memory STORE is a process-global singleton, so leftover sets/
    campaigns from one test would otherwise leak into the next (and, with the batch-name
    disambiguation, change the names a test expects). Clear it before each test."""
    for d in (
        STORE.measurement_sets,
        STORE.validation_sets,
        STORE.campaigns,
        STORE.analyses,
        STORE.fits,
        STORE.screening,
        STORE.validation_config,
    ):
        d.clear()
    yield
