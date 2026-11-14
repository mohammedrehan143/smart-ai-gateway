"""Shared test configuration and fixtures."""

import os
import tempfile
from httpx import ASGITransport, AsyncClient
import pytest_asyncio

from app.api.deps import get_orchestrator, get_repository
from app.main import app
from app.repositories.sqlite import SqliteTraceRepository
from app.services.orchestrator import ChatOrchestrator


@pytest_asyncio.fixture
async def test_repo():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    repo = SqliteTraceRepository(f"sqlite:///{temp_path}")
    await repo.initialize()
    yield repo
    await repo.close()
    try:
        os.remove(temp_path)
    except OSError:
        pass


@pytest_asyncio.fixture
async def async_client(test_repo):
    orchestrator = ChatOrchestrator(repository=test_repo)
    app.dependency_overrides[get_repository] = lambda: test_repo
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
