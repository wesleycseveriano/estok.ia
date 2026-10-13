import os

from dotenv import load_dotenv

load_dotenv()

LIMITE_ESTOQUE_BAIXO_PADRAO = 3


def obter_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./estok.db")


def obter_limite_estoque_baixo() -> int:
    """Lido a cada chamada, para refletir mudanças no ambiente (e nos testes)."""
    valor = os.getenv("ESTOQUE_BAIXO_LIMITE", str(LIMITE_ESTOQUE_BAIXO_PADRAO))
    try:
        return int(valor)
    except ValueError:
        return LIMITE_ESTOQUE_BAIXO_PADRAO
