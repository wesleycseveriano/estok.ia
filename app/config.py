import os

from dotenv import load_dotenv

load_dotenv()

LIMITE_ESTOQUE_BAIXO_PADRAO = 3


def obter_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./estok.db")


def obter_config_llm() -> dict[str, str | None]:
    return {
        "api_key": os.getenv("LLM_API_KEY"),
        "base_url": os.getenv("LLM_BASE_URL"),
        "modelo": os.getenv("LLM_MODEL"),
    }


def obter_arquivo_log_llm() -> str:
    """Caminho do log das chamadas à IA; vazio desliga o log."""
    return os.getenv("LLM_LOG_ARQUIVO", "logs/llm.log").strip()


def obter_limite_estoque_baixo() -> int:
    """Lido a cada chamada, para refletir mudanças no ambiente (e nos testes)."""
    valor = os.getenv("ESTOQUE_BAIXO_LIMITE", str(LIMITE_ESTOQUE_BAIXO_PADRAO))
    try:
        return int(valor)
    except ValueError:
        return LIMITE_ESTOQUE_BAIXO_PADRAO
