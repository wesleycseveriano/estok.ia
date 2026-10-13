"""Canal de chat web: adapta o fluxo de conversa para HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.canais.conversa import MemoriaConversa, Pendencias, processar_mensagem
from app.estoque.banco import obter_sessao
from app.interpretador.cliente_llm import (
    ClienteLLM,
    ClienteOpenAICompativel,
    Historico,
)

router = APIRouter(prefix="/api")


class MensagemChat(BaseModel):
    mensagem: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    sessao_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class RespostaChat(BaseModel):
    resposta: str
    acao_pendente: bool
    estoque_alterado: bool


class _ClienteSobDemanda(ClienteLLM):
    """Cria o cliente real só na primeira mensagem.

    Assim, uma configuração incompleta da IA vira uma resposta amigável no chat
    (ErroClienteLLM) em vez de impedir a aplicação de subir.
    """

    def __init__(self):
        self._cliente: ClienteLLM | None = None

    def responder(
        self, mensagem: str, prompt_sistema: str, historico: Historico = ()
    ) -> str:
        if self._cliente is None:
            self._cliente = ClienteOpenAICompativel()
        return self._cliente.responder(mensagem, prompt_sistema, historico)


_cliente_llm = _ClienteSobDemanda()
_pendencias = Pendencias()
_memoria = MemoriaConversa()


def obter_cliente_llm() -> ClienteLLM:
    return _cliente_llm


def obter_pendencias() -> Pendencias:
    return _pendencias


def obter_memoria() -> MemoriaConversa:
    return _memoria


@router.post("/chat", response_model=RespostaChat)
def conversar(
    dados: MensagemChat,
    sessao: Session = Depends(obter_sessao),
    cliente: ClienteLLM = Depends(obter_cliente_llm),
    pendencias: Pendencias = Depends(obter_pendencias),
    memoria: MemoriaConversa = Depends(obter_memoria),
):
    return processar_mensagem(
        dados.mensagem, dados.sessao_id, sessao, cliente, pendencias, memoria
    )
