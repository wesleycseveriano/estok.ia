"""Fluxo de conversa comum a todos os canais (web hoje, Telegram no futuro).

Consultas são respondidas na hora. Entradas e saídas ficam pendentes até o
usuário responder "sim"; só então o núcleo de estoque é chamado.
"""

import logging
import re
import threading
import unicodedata
from collections import deque
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import obter_limite_estoque_baixo
from app.estoque import servico
from app.estoque.excecoes import (
    ErroEstoque,
    EstoqueInsuficiente,
    ItemNaoEncontrado,
)
from app.estoque.modelos import Item, OrigemMovimentacao
from app.interpretador.acoes import (
    AcaoConsultar,
    AcaoEntrada,
    AcaoEsclarecer,
    AcaoForaDoEscopo,
    AcaoListarEstoqueBaixo,
    AcaoSaida,
)
from app.interpretador.cliente_llm import ClienteLLM, ErroClienteLLM
from app.interpretador.interpretador import interpretar

logger = logging.getLogger(__name__)

AcaoMovimento = AcaoEntrada | AcaoSaida

PALAVRAS_SIM = {"sim", "s", "confirmo", "confirmar", "pode", "ok"}
PALAVRAS_NAO = {"nao", "n", "cancela", "cancelar", "cancelo"}

MSG_FORA_DO_ESCOPO = (
    "Só consigo ajudar com o estoque do almoxarifado de TI: registrar entradas "
    'e saídas e consultar itens. Ex.: "chegaram 10 mouses Logitech M90" ou '
    '"o que está acabando?".'
)
MSG_NAO_ENTENDI = (
    'Não entendi. Tente algo como "saiu 1 HD Seagate 1TB" ou '
    '"quantos teclados temos?".'
)
MSG_SEM_PENDENCIA = "Não há nenhuma ação aguardando confirmação."
MSG_ERRO_INESPERADO = "Ocorreu um erro inesperado. Nada foi alterado no estoque."

TROCAS_DE_CONTEXTO = 3  # pares (usuário, assistente) enviados à IA


@dataclass
class RespostaConversa:
    resposta: str
    acao_pendente: bool = False
    estoque_alterado: bool = False


class Pendencias:
    """Ações aguardando confirmação, por sessão. Em memória, por enquanto."""

    def __init__(self):
        self._acoes: dict[str, AcaoMovimento] = {}
        self._trava = threading.Lock()

    def guardar(self, sessao_id: str, acao: AcaoMovimento) -> None:
        with self._trava:
            self._acoes[sessao_id] = acao

    def retirar(self, sessao_id: str) -> AcaoMovimento | None:
        with self._trava:
            return self._acoes.pop(sessao_id, None)


class MemoriaConversa:
    """Últimas trocas de cada sessão, enviadas à IA como contexto.

    Permite responder "10" a "Quantas unidades chegaram?". Em memória e curta
    de propósito: poucas trocas bastam e cada uma custa tokens.
    """

    def __init__(self, trocas: int = TROCAS_DE_CONTEXTO):
        self._trocas = trocas
        self._historicos: dict[str, deque] = {}
        self._trava = threading.Lock()

    def obter(self, sessao_id: str) -> list[dict[str, str]]:
        with self._trava:
            return list(self._historicos.get(sessao_id, ()))

    def registrar(self, sessao_id: str, mensagem: str, resposta: str) -> None:
        with self._trava:
            historico = self._historicos.setdefault(
                sessao_id, deque(maxlen=2 * self._trocas)
            )
            historico.append({"role": "user", "content": mensagem})
            historico.append({"role": "assistant", "content": resposta})


# ---------------------------------------------------------------- textos


def _unidades(quantidade: int) -> str:
    return f"{quantidade} unidade" if quantidade == 1 else f"{quantidade} unidades"


def _nome(item: Item) -> str:
    return f"{item.tipo.value} {item.marca} {item.modelo}"


def _verbo(acao: AcaoMovimento) -> str:
    return "entrada" if isinstance(acao, AcaoEntrada) else "saída"


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", sem_acento).strip()


def _lista_de_itens(itens: list[Item]) -> str:
    return "\n".join(f"- {_nome(i)}: {_unidades(i.quantidade)}" for i in itens)


# ---------------------------------------------------------------- ações


def _responder_consulta(sessao: Session, acao: AcaoConsultar) -> RespostaConversa:
    itens = servico.buscar_itens(sessao, tipo=acao.tipo, texto=acao.texto)
    filtro = " ".join(p for p in (acao.tipo and acao.tipo.value, acao.texto) if p)
    descricao = f' para "{filtro}"' if filtro else ""
    if not itens:
        return RespostaConversa(f"Não encontrei itens{descricao} no estoque.")

    quantos = "1 item" if len(itens) == 1 else f"{len(itens)} itens"
    texto = f"Encontrei {quantos}{descricao}:\n{_lista_de_itens(itens)}"
    if len(itens) > 1:
        total = sum(i.quantidade for i in itens)
        texto += f"\nTotal: {_unidades(total)}."
    return RespostaConversa(texto)


def _responder_estoque_baixo(sessao: Session) -> RespostaConversa:
    limite = obter_limite_estoque_baixo()
    itens = servico.listar_estoque_baixo(sessao)
    if not itens:
        return RespostaConversa(
            f"Nenhum item com estoque baixo (até {_unidades(limite)})."
        )
    return RespostaConversa(
        f"Itens com estoque baixo (até {_unidades(limite)}):\n{_lista_de_itens(itens)}"
    )


def _pedir_confirmacao(
    sessao: Session, sessao_id: str, acao: AcaoMovimento, pendencias: Pendencias
) -> RespostaConversa:
    item = servico.obter_item(sessao, acao.item_id)
    if isinstance(acao, AcaoSaida) and acao.quantidade > item.quantidade:
        erro = EstoqueInsuficiente(item.quantidade, acao.quantidade)
        return RespostaConversa(f"{erro.mensagem} Item: {_nome(item)}.")

    pendencias.guardar(sessao_id, acao)
    return RespostaConversa(
        f"Confirmar {_verbo(acao)} de {acao.quantidade} {_nome(item)}? "
        f"Saldo atual: {_unidades(item.quantidade)}. Responda sim ou não.",
        acao_pendente=True,
    )


def _executar(sessao: Session, acao: AcaoMovimento) -> RespostaConversa:
    registrar = (
        servico.registrar_entrada
        if isinstance(acao, AcaoEntrada)
        else servico.registrar_saida
    )
    try:
        item = registrar(
            sessao, acao.item_id, acao.quantidade, origem=OrigemMovimentacao.CHAT
        )
    except ItemNaoEncontrado:
        return RespostaConversa(
            "Não foi possível registrar: o item não existe mais no estoque."
        )
    except ErroEstoque as erro:
        return RespostaConversa(f"Não foi possível registrar. {erro.mensagem}")

    return RespostaConversa(
        f"Feito! {_verbo(acao).capitalize()} de {acao.quantidade} {_nome(item)} "
        f"registrada. Saldo atual: {_unidades(item.quantidade)}.",
        estoque_alterado=True,
    )


def _descrever_pendencia(sessao: Session, acao: AcaoMovimento) -> str:
    try:
        nome = _nome(servico.obter_item(sessao, acao.item_id))
    except ItemNaoEncontrado:
        nome = "item"
    return f"{_verbo(acao)} de {acao.quantidade} {nome}"


# ---------------------------------------------------------------- entrada


def processar_mensagem(
    mensagem: str,
    sessao_id: str,
    sessao: Session,
    cliente: ClienteLLM,
    pendencias: Pendencias,
    memoria: MemoriaConversa,
) -> RespostaConversa:
    try:
        resposta = _processar(
            mensagem, sessao_id, sessao, cliente, pendencias, memoria.obter(sessao_id)
        )
    except ErroClienteLLM as erro:
        return RespostaConversa(str(erro))
    except ErroEstoque as erro:
        return RespostaConversa(erro.mensagem)
    except Exception:
        logger.exception("Erro inesperado no chat")
        sessao.rollback()
        return RespostaConversa(MSG_ERRO_INESPERADO)

    # Só trocas bem-sucedidas viram contexto; erros da IA não ajudam o modelo.
    memoria.registrar(sessao_id, mensagem, resposta.resposta)
    return resposta


def _processar(
    mensagem, sessao_id, sessao, cliente, pendencias, historico
) -> RespostaConversa:
    palavra = _normalizar(mensagem)
    pendente = pendencias.retirar(sessao_id)

    if palavra in PALAVRAS_SIM or palavra in PALAVRAS_NAO:
        if pendente is None:
            return RespostaConversa(MSG_SEM_PENDENCIA)
        if palavra in PALAVRAS_SIM:
            return _executar(sessao, pendente)
        return RespostaConversa(
            f"Ok, cancelei a {_descrever_pendencia(sessao, pendente)}. "
            "Nada foi alterado."
        )

    try:
        resposta = _interpretar_e_responder(
            mensagem, sessao_id, sessao, cliente, pendencias, historico
        )
    except ErroClienteLLM:
        # A IA falhou: a ação anterior continua aguardando confirmação.
        if pendente is not None:
            pendencias.guardar(sessao_id, pendente)
        raise
    if pendente is not None:
        aviso = f"(Descartei a {_descrever_pendencia(sessao, pendente)} que aguardava confirmação.)"
        resposta.resposta = f"{aviso}\n{resposta.resposta}"
    return resposta


def _interpretar_e_responder(
    mensagem, sessao_id, sessao, cliente, pendencias, historico
) -> RespostaConversa:
    acao = interpretar(mensagem, sessao, cliente, historico)

    if isinstance(acao, (AcaoEntrada, AcaoSaida)):
        return _pedir_confirmacao(sessao, sessao_id, acao, pendencias)
    if isinstance(acao, AcaoConsultar):
        return _responder_consulta(sessao, acao)
    if isinstance(acao, AcaoListarEstoqueBaixo):
        return _responder_estoque_baixo(sessao)
    if isinstance(acao, AcaoEsclarecer):
        return RespostaConversa(acao.pergunta)
    if isinstance(acao, AcaoForaDoEscopo):
        return RespostaConversa(MSG_FORA_DO_ESCOPO)
    return RespostaConversa(MSG_NAO_ENTENDI)
