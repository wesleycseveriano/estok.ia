from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import obter_database_url
from app.estoque.modelos import Base

_url = obter_database_url()
_conexao_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, connect_args=_conexao_args)
SessaoLocal = sessionmaker(bind=engine, expire_on_commit=False)


def criar_tabelas() -> None:
    Base.metadata.create_all(engine)


def obter_sessao() -> Iterator[Session]:
    """Dependência do FastAPI: abre uma sessão por requisição."""
    with SessaoLocal() as sessao:
        yield sessao
