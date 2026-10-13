"""Grava cada chamada à IA em um arquivo legível, para inspeção.

Nunca grava a chave da API. Falhas ao escrever o log não afetam o chat.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from app.config import obter_arquivo_log_llm

logger = logging.getLogger(__name__)

_trava = threading.Lock()


def _formatar(parametros: dict, duracao: float, texto, uso, erro) -> str:
    cabecalho = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"modelo: {parametros.get('model')}",
        f"{duracao:.2f}s",
    ]
    if uso is not None:
        cabecalho.append(
            f"tokens: entrada {getattr(uso, 'prompt_tokens', '?')}, "
            f"saída {getattr(uso, 'completion_tokens', '?')}"
        )
    opcoes = {
        chave: valor
        for chave, valor in parametros.items()
        if chave not in ("model", "messages")
    }

    partes = [
        "=" * 80,
        " | ".join(cabecalho),
        f"parâmetros: {json.dumps(opcoes, ensure_ascii=False)}",
    ]
    for mensagem in parametros.get("messages", []):
        partes += [f"--- {mensagem['role']}", mensagem["content"]]
    if erro is not None:
        partes += ["--- ERRO", f"{type(erro).__name__}: {erro}"]
    else:
        partes += ["--- resposta do modelo", texto if texto else "(vazia)"]
    return "\n".join(partes) + "\n\n"


def registrar_chamada(
    parametros: dict,
    duracao: float,
    texto: str | None = None,
    uso=None,
    erro: Exception | None = None,
) -> None:
    caminho = obter_arquivo_log_llm()
    if not caminho:
        return
    try:
        bloco = _formatar(parametros, duracao, texto, uso, erro)
        arquivo = Path(caminho)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        with _trava, arquivo.open("a", encoding="utf-8") as saida:
            saida.write(bloco)
    except Exception:
        logger.warning("Não foi possível gravar o log da IA em %s", caminho)
