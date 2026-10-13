"""Fixtures compartilhadas: banco SQLite em memória, isolado por teste."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.estoque.banco import obter_sessao
from app.estoque.modelos import Base
from app.main import app


@pytest.fixture(autouse=True)
def sem_log_da_ia(monkeypatch):
    """Os testes não gravam logs/llm.log; quem testa o log liga explicitamente."""
    monkeypatch.setenv("LLM_LOG_ARQUIVO", "")


@pytest.fixture
def fabrica_sessao():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def sessao(fabrica_sessao):
    with fabrica_sessao() as s:
        yield s


@pytest.fixture
def cliente(fabrica_sessao):
    def _sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    yield TestClient(app)
    app.dependency_overrides.clear()
