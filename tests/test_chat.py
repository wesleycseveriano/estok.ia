"""Testes do canal de chat. A IA é sempre o ClienteLLMFalso."""

import json

import pytest
from fastapi.testclient import TestClient

from app.canais.chat_web import obter_cliente_llm, obter_pendencias
from app.canais.conversa import MSG_ERRO_INESPERADO, Pendencias
from app.estoque import servico
from app.estoque.banco import obter_sessao
from app.estoque.modelos import OrigemMovimentacao, TipoItem, TipoMovimentacao
from app.interpretador.cliente_falso import ClienteLLMFalso
from app.interpretador.cliente_llm import ErroClienteLLM
from app.main import app


class Chat:
    """Conversa de teste: define as respostas do modelo e envia mensagens."""

    def __init__(self, http: TestClient, sessao):
        self.http = http
        self.sessao = sessao
        self.llm = ClienteLLMFalso()

    def modelo_responde(self, *respostas):
        self.llm = ClienteLLMFalso(
            *(json.dumps(r) if isinstance(r, dict) else r for r in respostas)
        )

    def enviar(self, mensagem, sessao_id="sessao-1"):
        resposta = self.http.post(
            "/api/chat", json={"mensagem": mensagem, "sessao_id": sessao_id}
        )
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def saldo(self, item_id):
        self.sessao.expire_all()
        return servico.obter_item(self.sessao, item_id).quantidade


@pytest.fixture
def chat(fabrica_sessao, sessao):
    def _sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    conversa = Chat(TestClient(app), sessao)
    pendencias = Pendencias()
    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    app.dependency_overrides[obter_cliente_llm] = lambda: conversa.llm
    app.dependency_overrides[obter_pendencias] = lambda: pendencias
    yield conversa
    app.dependency_overrides.clear()


@pytest.fixture
def hd(sessao):
    return servico.cadastrar_item(sessao, TipoItem.HD, "Seagate", "Barracuda 1TB", 4)


@pytest.fixture
def teclados(sessao):
    return [
        servico.cadastrar_item(sessao, TipoItem.TECLADO, "Dell", "KB216", 18),
        servico.cadastrar_item(sessao, TipoItem.TECLADO, "Logitech", "K120", 2),
    ]


def _saida(item, quantidade):
    return {"acao": "saida", "item_id": item.id, "quantidade": quantidade}


def _entrada(item, quantidade):
    return {"acao": "entrada", "item_id": item.id, "quantidade": quantidade}


# ---------------------------------------------------------------- confirmação


class TestFluxoDeConfirmacao:
    def test_saida_pede_confirmacao_sem_alterar_o_estoque(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1))
        r = chat.enviar("saiu 1 HD Seagate 1TB")

        assert r["resposta"] == (
            "Confirmar saída de 1 HD Seagate Barracuda 1TB? "
            "Saldo atual: 4 unidades. Responda sim ou não."
        )
        assert r["acao_pendente"] is True
        assert r["estoque_alterado"] is False
        assert chat.saldo(hd.id) == 4

    def test_sim_executa_a_saida_e_informa_o_saldo(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD Seagate 1TB")
        r = chat.enviar("sim")

        assert r == {
            "resposta": "Feito! Saída de 1 HD Seagate Barracuda 1TB registrada. "
            "Saldo atual: 3 unidades.",
            "acao_pendente": False,
            "estoque_alterado": True,
        }
        assert chat.saldo(hd.id) == 3
        assert len(chat.llm.chamadas) == 1  # "sim" não passa pela IA

    def test_movimentacao_registrada_com_origem_chat(self, chat, hd):
        chat.modelo_responde(_saida(hd, 2))
        chat.enviar("saíram 2 HDs Seagate")
        chat.enviar("sim")

        ultima = servico.listar_movimentacoes(chat.sessao, item_id=hd.id)[0]
        assert ultima.tipo == TipoMovimentacao.SAIDA
        assert ultima.quantidade == 2
        assert ultima.origem == OrigemMovimentacao.CHAT

    def test_entrada_completa(self, chat, hd):
        chat.modelo_responde(_entrada(hd, 10))
        r = chat.enviar("chegaram 10 HDs Seagate")
        assert r["resposta"].startswith("Confirmar entrada de 10 HD Seagate")
        assert r["acao_pendente"] is True

        r = chat.enviar("sim")
        assert "Entrada de 10 HD Seagate Barracuda 1TB registrada" in r["resposta"]
        assert "Saldo atual: 14 unidades." in r["resposta"]
        assert r["estoque_alterado"] is True
        assert chat.saldo(hd.id) == 14

    @pytest.mark.parametrize("resposta", ["Sim", "SIM!", "s", "confirmo", " ok. "])
    def test_variacoes_de_sim(self, chat, hd, resposta):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD")
        assert chat.enviar(resposta)["estoque_alterado"] is True
        assert chat.saldo(hd.id) == 3

    def test_confirmacao_vale_uma_vez_so(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD")
        chat.enviar("sim")
        r = chat.enviar("sim")
        assert r["resposta"] == "Não há nenhuma ação aguardando confirmação."
        assert r["estoque_alterado"] is False
        assert chat.saldo(hd.id) == 3

    def test_pendencia_e_separada_por_sessao(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD", sessao_id="ana")

        r = chat.enviar("sim", sessao_id="bruno")
        assert r["resposta"] == "Não há nenhuma ação aguardando confirmação."
        assert chat.saldo(hd.id) == 4

        assert chat.enviar("sim", sessao_id="ana")["estoque_alterado"] is True
        assert chat.saldo(hd.id) == 3

    def test_nova_mensagem_descarta_a_pendencia_anterior(self, chat, hd, teclados):
        chat.modelo_responde(
            _saida(hd, 1), {"acao": "consultar", "tipo": "Teclado", "texto": None}
        )
        chat.enviar("saiu 1 HD")
        r = chat.enviar("quantos teclados temos?")

        assert r["resposta"].startswith(
            "(Descartei a saída de 1 HD Seagate Barracuda 1TB que aguardava "
            "confirmação.)\n"
        )
        assert "Teclado Dell KB216" in r["resposta"]
        assert r["acao_pendente"] is False
        assert chat.enviar("sim")["resposta"] == (
            "Não há nenhuma ação aguardando confirmação."
        )
        assert chat.saldo(hd.id) == 4

    def test_nova_movimentacao_substitui_a_pendente(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1), _entrada(hd, 5))
        chat.enviar("saiu 1 HD")
        r = chat.enviar("na verdade chegaram 5 HDs")
        assert r["acao_pendente"] is True
        assert "Confirmar entrada de 5" in r["resposta"]

        chat.enviar("sim")
        assert chat.saldo(hd.id) == 9


# ---------------------------------------------------------------- recusa


class TestRecusa:
    @pytest.mark.parametrize("resposta", ["não", "Não.", "nao", "N", "cancelar"])
    def test_nao_descarta_a_acao(self, chat, hd, resposta):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD")
        r = chat.enviar(resposta)

        assert r == {
            "resposta": "Ok, cancelei a saída de 1 HD Seagate Barracuda 1TB. "
            "Nada foi alterado.",
            "acao_pendente": False,
            "estoque_alterado": False,
        }
        assert chat.saldo(hd.id) == 4
        assert len(servico.listar_movimentacoes(chat.sessao, item_id=hd.id)) == 1

    def test_sim_depois_de_nao_nao_executa(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1))
        chat.enviar("saiu 1 HD")
        chat.enviar("não")
        assert chat.enviar("sim")["estoque_alterado"] is False
        assert chat.saldo(hd.id) == 4

    def test_nao_sem_pendencia(self, chat):
        r = chat.enviar("não")
        assert r["resposta"] == "Não há nenhuma ação aguardando confirmação."
        assert chat.llm.chamadas == []


# ---------------------------------------------------------------- consultas


class TestConsultas:
    def test_consulta_por_tipo_com_total(self, chat, teclados):
        chat.modelo_responde({"acao": "consultar", "tipo": "Teclado", "texto": None})
        r = chat.enviar("quantos teclados temos?")
        assert r == {
            "resposta": 'Encontrei 2 itens para "Teclado":\n'
            "- Teclado Dell KB216: 18 unidades\n"
            "- Teclado Logitech K120: 2 unidades\n"
            "Total: 20 unidades.",
            "acao_pendente": False,
            "estoque_alterado": False,
        }

    def test_consulta_por_texto(self, chat, teclados, hd):
        chat.modelo_responde({"acao": "consultar", "tipo": None, "texto": "seagate"})
        r = chat.enviar("tem HD seagate?")
        assert r["resposta"] == (
            'Encontrei 1 item para "seagate":\n'
            "- HD Seagate Barracuda 1TB: 4 unidades"
        )

    def test_consulta_sem_resultado(self, chat, teclados):
        chat.modelo_responde({"acao": "consultar", "tipo": "Monitor", "texto": None})
        r = chat.enviar("tem monitor?")
        assert r["resposta"] == 'Não encontrei itens para "Monitor" no estoque.'

    def test_estoque_baixo(self, chat, teclados, hd, monkeypatch):
        monkeypatch.setenv("ESTOQUE_BAIXO_LIMITE", "3")
        chat.modelo_responde({"acao": "listar_estoque_baixo"})
        r = chat.enviar("o que está acabando?")
        assert r["resposta"] == (
            "Itens com estoque baixo (até 3 unidades):\n"
            "- Teclado Logitech K120: 2 unidades"
        )

    def test_nenhum_item_com_estoque_baixo(self, chat, hd, monkeypatch):
        monkeypatch.setenv("ESTOQUE_BAIXO_LIMITE", "3")
        chat.modelo_responde({"acao": "listar_estoque_baixo"})
        r = chat.enviar("o que está acabando?")
        assert r["resposta"] == "Nenhum item com estoque baixo (até 3 unidades)."

    def test_esclarecimento(self, chat, hd):
        pergunta = "Quantas unidades do HD Seagate Barracuda 1TB saíram?"
        chat.modelo_responde({"acao": "esclarecer", "pergunta": pergunta})
        r = chat.enviar("saiu HD")
        assert r == {
            "resposta": pergunta,
            "acao_pendente": False,
            "estoque_alterado": False,
        }

    def test_fora_do_escopo(self, chat):
        chat.modelo_responde({"acao": "fora_do_escopo"})
        r = chat.enviar("qual a previsão do tempo?")
        assert r["resposta"].startswith("Só consigo ajudar com o estoque")


# ---------------------------------------------------------------- erros


class TestErros:
    def test_saida_maior_que_o_saldo_nem_pede_confirmacao(self, chat, hd):
        chat.modelo_responde(_saida(hd, 10))
        r = chat.enviar("saíram 10 HDs")
        assert r == {
            "resposta": "Estoque insuficiente: há apenas 4 unidades (solicitado: 10). "
            "Item: HD Seagate Barracuda 1TB.",
            "acao_pendente": False,
            "estoque_alterado": False,
        }

    def test_saldo_mudou_antes_da_confirmacao(self, chat, hd):
        chat.modelo_responde(_saida(hd, 3))
        chat.enviar("saíram 3 HDs")
        servico.registrar_saida(chat.sessao, hd.id, 2)  # alguém mexeu pela tela

        r = chat.enviar("sim")
        assert r["resposta"] == (
            "Não foi possível registrar. Estoque insuficiente: há apenas "
            "2 unidades (solicitado: 3)."
        )
        assert r["estoque_alterado"] is False
        assert chat.saldo(hd.id) == 2

    def test_item_excluido_antes_da_confirmacao(self, chat, sessao):
        item = servico.cadastrar_item(sessao, TipoItem.SSD, "Kingston", "A400", 0)
        chat.modelo_responde(_entrada(item, 5))
        chat.enviar("chegaram 5 SSDs")
        servico.excluir_item(sessao, item.id)

        r = chat.enviar("sim")
        assert r["resposta"] == (
            "Não foi possível registrar: o item não existe mais no estoque."
        )
        assert r["estoque_alterado"] is False

    def test_resposta_invalida_do_modelo(self, chat, hd):
        chat.modelo_responde('{"acao": "saida", "item_id": ')
        r = chat.enviar("saiu 1 HD")
        assert r["resposta"].startswith("Não entendi.")
        assert r["acao_pendente"] is False
        assert chat.saldo(hd.id) == 4

    def test_item_inexistente_sugerido_pelo_modelo(self, chat, hd):
        chat.modelo_responde({"acao": "saida", "item_id": 999, "quantidade": 1})
        r = chat.enviar("saiu 1 HD")
        assert r["resposta"].startswith("Não entendi.")
        assert r["acao_pendente"] is False

    def test_falha_da_ia_vira_mensagem_amigavel(self, chat):
        chat.modelo_responde(ErroClienteLLM("A IA demorou demais para responder."))
        r = chat.enviar("saiu 1 HD")
        assert r == {
            "resposta": "A IA demorou demais para responder.",
            "acao_pendente": False,
            "estoque_alterado": False,
        }

    def test_falha_da_ia_mantem_a_pendencia(self, chat, hd):
        chat.modelo_responde(_saida(hd, 1), ErroClienteLLM("IA fora do ar."))
        chat.enviar("saiu 1 HD")
        assert chat.enviar("e os teclados?")["resposta"] == "IA fora do ar."
        assert chat.enviar("sim")["estoque_alterado"] is True
        assert chat.saldo(hd.id) == 3

    def test_erro_inesperado_nao_vaza_detalhes(self, chat):
        chat.modelo_responde(RuntimeError("segredo interno: tabela xyz"))
        r = chat.enviar("saiu 1 HD")
        assert r["resposta"] == MSG_ERRO_INESPERADO
        assert "segredo" not in r["resposta"]
        assert "Traceback" not in r["resposta"]


# ---------------------------------------------------------------- validação


class TestValidacao:
    @pytest.mark.parametrize(
        "corpo",
        [
            {"mensagem": "", "sessao_id": "s"},
            {"mensagem": "    ", "sessao_id": "s"},
            {"mensagem": "x" * 501, "sessao_id": "s"},
            {"mensagem": "oi"},
            {"mensagem": "oi", "sessao_id": ""},
            {"sessao_id": "s"},
        ],
    )
    def test_entrada_invalida_retorna_422(self, chat, corpo):
        resposta = chat.http.post("/api/chat", json=corpo)
        assert resposta.status_code == 422
        assert chat.llm.chamadas == []

    def test_mensagem_com_500_caracteres_e_aceita(self, chat):
        chat.modelo_responde({"acao": "fora_do_escopo"})
        assert chat.enviar("x" * 500)["resposta"].startswith("Só consigo")
