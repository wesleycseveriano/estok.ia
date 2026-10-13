"""Transforma texto livre em uma ação validada. Nunca executa a ação."""

import logging
import re

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.estoque import servico
from app.interpretador.acoes import (
    Acao,
    AcaoEntrada,
    AcaoNaoEntendida,
    AcaoSaida,
    validador_acao,
)
from app.interpretador.cliente_llm import ClienteLLM
from app.interpretador.prompt import montar_prompt_sistema

logger = logging.getLogger(__name__)

_CERCA_DE_CODIGO = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _limpar_resposta(texto: str) -> str:
    """Tolera o JSON vir dentro de um bloco ```json ... ```."""
    texto = texto.strip()
    cerca = _CERCA_DE_CODIGO.match(texto)
    return cerca.group(1) if cerca else texto


def interpretar(mensagem: str, sessao: Session, cliente: ClienteLLM) -> Acao:
    """Pede ao modelo uma ação para a mensagem e devolve-a validada.

    Qualquer resposta inválida vira AcaoNaoEntendida. Erros de comunicação com
    o modelo (ErroClienteLLM) são propagados para o canal decidir o que dizer.
    """
    if not mensagem or not mensagem.strip():
        return AcaoNaoEntendida(motivo="mensagem vazia")

    itens = servico.buscar_itens(sessao)
    resposta = cliente.responder(mensagem.strip(), montar_prompt_sistema(itens))

    try:
        acao = validador_acao.validate_json(_limpar_resposta(resposta))
    except ValidationError as erro:
        logger.info("Resposta inválida do modelo: %r (%s)", resposta, erro)
        return AcaoNaoEntendida(motivo="resposta fora do formato esperado")

    if isinstance(acao, (AcaoEntrada, AcaoSaida)):
        if acao.item_id not in {item.id for item in itens}:
            logger.info("Modelo sugeriu item inexistente: %r", resposta)
            return AcaoNaoEntendida(motivo=f"item {acao.item_id} não existe")

    return acao
