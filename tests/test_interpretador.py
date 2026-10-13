"""Testes do interpretador. Nenhum teste chama a IA de verdade."""

import json
from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.estoque import servico
from app.estoque.modelos import TipoItem
from app.interpretador.acoes import (
    AcaoConsultar,
    AcaoEntrada,
    AcaoEsclarecer,
    AcaoForaDoEscopo,
    AcaoListarEstoqueBaixo,
    AcaoNaoEntendida,
    AcaoSaida,
)
from app.interpretador.cliente_falso import ClienteLLMFalso
from app.interpretador.cliente_llm import ClienteOpenAICompativel, ErroClienteLLM
from app.interpretador.interpretador import interpretar
from app.interpretador.prompt import montar_prompt_sistema
from app.interpretador.registro_llm import registrar_chamada


@pytest.fixture
def itens(sessao):
    """Estoque de exemplo; devolve os itens por apelido."""
    return {
        "mouse_m90": servico.cadastrar_item(
            sessao, TipoItem.MOUSE, "Logitech", "M90", 10
        ),
        "mouse_ms116": servico.cadastrar_item(
            sessao, TipoItem.MOUSE, "Dell", "MS116", 4
        ),
        "hd": servico.cadastrar_item(
            sessao, TipoItem.HD, "Seagate", "Barracuda 1TB", 2
        ),
    }


def _interpretar(sessao, resposta_do_modelo, mensagem="mensagem qualquer"):
    if isinstance(resposta_do_modelo, dict):
        resposta_do_modelo = json.dumps(resposta_do_modelo)
    return interpretar(mensagem, sessao, ClienteLLMFalso(resposta_do_modelo))


# ---------------------------------------------------------------- JSON válido


class TestRespostasValidas:
    def test_entrada(self, sessao, itens):
        item_id = itens["mouse_m90"].id
        acao = _interpretar(
            sessao, {"acao": "entrada", "item_id": item_id, "quantidade": 10}
        )
        assert acao == AcaoEntrada(acao="entrada", item_id=item_id, quantidade=10)

    def test_saida(self, sessao, itens):
        item_id = itens["hd"].id
        acao = _interpretar(
            sessao, {"acao": "saida", "item_id": item_id, "quantidade": 1}
        )
        assert acao == AcaoSaida(acao="saida", item_id=item_id, quantidade=1)

    def test_consultar_por_tipo(self, sessao, itens):
        acao = _interpretar(
            sessao, {"acao": "consultar", "tipo": "Mouse", "texto": None}
        )
        assert isinstance(acao, AcaoConsultar)
        assert acao.tipo == TipoItem.MOUSE and acao.texto is None

    def test_consultar_por_texto_sem_tipo(self, sessao, itens):
        acao = _interpretar(
            sessao, {"acao": "consultar", "tipo": None, "texto": "dell"}
        )
        assert isinstance(acao, AcaoConsultar)
        assert acao.tipo is None and acao.texto == "dell"

    def test_listar_estoque_baixo(self, sessao, itens):
        acao = _interpretar(sessao, {"acao": "listar_estoque_baixo"})
        assert isinstance(acao, AcaoListarEstoqueBaixo)

    def test_pedido_de_esclarecimento(self, sessao, itens):
        pergunta = "Qual mouse: Logitech M90 ou Dell MS116?"
        acao = _interpretar(sessao, {"acao": "esclarecer", "pergunta": pergunta})
        assert acao == AcaoEsclarecer(acao="esclarecer", pergunta=pergunta)

    def test_fora_do_escopo(self, sessao, itens):
        acao = _interpretar(sessao, {"acao": "fora_do_escopo"})
        assert isinstance(acao, AcaoForaDoEscopo)

    def test_aceita_json_dentro_de_bloco_de_codigo(self, sessao, itens):
        resposta = '```json\n{"acao": "listar_estoque_baixo"}\n```'
        assert isinstance(_interpretar(sessao, resposta), AcaoListarEstoqueBaixo)


# ---------------------------------------------------------------- respostas inválidas


class TestRespostasInvalidas:
    @pytest.mark.parametrize(
        "resposta",
        [
            '{"acao": "entrada", "item_id": 1, "quantidade": ',
            "Claro! Vou registrar a entrada de 10 mouses.",
            "",
            "[]",
            "null",
        ],
    )
    def test_json_quebrado_ou_sem_objeto(self, sessao, itens, resposta):
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    @pytest.mark.parametrize(
        "resposta",
        [
            {"acao": "excluir", "item_id": 1},
            {"acao": "cadastrar", "tipo": "Mouse", "marca": "HP", "modelo": "X"},
            {"acao": "nao_entendido", "motivo": "o modelo não pode gerar esta"},
            {"item_id": 1, "quantidade": 2},
        ],
    )
    def test_acao_desconhecida(self, sessao, itens, resposta):
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    @pytest.mark.parametrize("operacao", ["entrada", "saida"])
    def test_item_id_inexistente(self, sessao, itens, operacao):
        acao = _interpretar(sessao, {"acao": operacao, "item_id": 999, "quantidade": 1})
        assert isinstance(acao, AcaoNaoEntendida)
        assert "999" in acao.motivo

    @pytest.mark.parametrize("quantidade", [-3, 0, 1.5, "2", None])
    @pytest.mark.parametrize("operacao", ["entrada", "saida"])
    def test_quantidade_invalida(self, sessao, itens, operacao, quantidade):
        resposta = {
            "acao": operacao,
            "item_id": itens["mouse_m90"].id,
            "quantidade": quantidade,
        }
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    @pytest.mark.parametrize("item_id", ["1", 1.0, None])
    def test_item_id_de_tipo_errado(self, sessao, itens, item_id):
        resposta = {"acao": "entrada", "item_id": item_id, "quantidade": 1}
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    def test_quantidade_ausente(self, sessao, itens):
        resposta = {"acao": "saida", "item_id": itens["hd"].id}
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    def test_consultar_com_tipo_fora_da_lista(self, sessao, itens):
        resposta = {"acao": "consultar", "tipo": "Impressora", "texto": None}
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)

    def test_esclarecer_sem_pergunta(self, sessao, itens):
        resposta = {"acao": "esclarecer", "pergunta": "   "}
        assert isinstance(_interpretar(sessao, resposta), AcaoNaoEntendida)


# ---------------------------------------------------------------- comportamento


class TestComportamento:
    def test_interpretar_nao_executa_a_acao(self, sessao, itens):
        item = itens["mouse_m90"]
        _interpretar(sessao, {"acao": "saida", "item_id": item.id, "quantidade": 5})
        assert servico.obter_item(sessao, item.id).quantidade == 10
        assert len(servico.listar_movimentacoes(sessao, item_id=item.id)) == 1

    def test_envia_mensagem_e_prompt_com_itens_cadastrados(self, sessao, itens):
        cliente = ClienteLLMFalso('{"acao": "listar_estoque_baixo"}')
        interpretar("  o que está acabando?  ", sessao, cliente)

        [(mensagem, prompt)] = cliente.chamadas
        assert mensagem == "o que está acabando?"
        for item in itens.values():
            linha = f"{item.id} | {item.tipo.value} | {item.marca} | {item.modelo}"
            assert linha in prompt

    def test_repassa_o_historico_ao_modelo(self, sessao, itens):
        historico = [
            {"role": "user", "content": "chegou mais JBL"},
            {"role": "assistant", "content": "Quantas unidades chegaram?"},
        ]
        cliente = ClienteLLMFalso('{"acao": "fora_do_escopo"}')
        interpretar("10", sessao, cliente, historico)
        assert cliente.historicos == [historico]

    @pytest.mark.parametrize("mensagem", ["", "   "])
    def test_mensagem_vazia_nao_chama_o_modelo(self, sessao, mensagem):
        cliente = ClienteLLMFalso()
        acao = interpretar(mensagem, sessao, cliente)
        assert isinstance(acao, AcaoNaoEntendida)
        assert cliente.chamadas == []

    def test_erro_do_cliente_e_propagado(self, sessao, itens):
        cliente = ClienteLLMFalso(ErroClienteLLM("A IA demorou demais para responder."))
        with pytest.raises(ErroClienteLLM):
            interpretar("saiu 1 HD", sessao, cliente)


class TestPrompt:
    def test_prompt_vem_de_arquivo_e_tem_os_marcadores_preenchidos(self, sessao, itens):
        prompt = montar_prompt_sistema(servico.buscar_itens(sessao))
        assert "{{" not in prompt
        assert "Memória RAM" in prompt  # lista de tipos
        assert "Seagate | Barracuda 1TB" in prompt

    def test_prompt_cita_sinonimos_e_proibe_cadastro(self):
        prompt = montar_prompt_sistema([])
        assert "(nenhum item cadastrado)" in prompt
        assert '"cabo UTP"' in prompt and "Cabo de rede" in prompt
        assert '"chave do Windows"' in prompt
        assert "não cadastra itens novos" in prompt
        assert "nunca ofereça cadastrar" in prompt


# ---------------------------------------------------------------- cliente real (sem rede)


class _OpenAIDeMentira:
    """Imita client.chat.completions.create sem fazer chamada de rede."""

    def __init__(self, *respostas):
        self._respostas = list(respostas)
        self.chamadas = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **parametros):
        self.chamadas.append(parametros)
        resposta = self._respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        mensagem = SimpleNamespace(content=resposta)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])


def _erro_http(classe, status, mensagem="erro simulado"):
    requisicao = httpx2.Request("POST", "https://exemplo.invalid/v1/chat/completions")
    resposta = httpx2.Response(status, request=requisicao)
    return classe(mensagem, response=resposta, body=None)


@pytest.fixture
def ambiente_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "chave-de-teste")
    monkeypatch.setenv("LLM_BASE_URL", "https://exemplo.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "modelo-de-teste")


class TestClienteOpenAICompativel:
    def test_configuracao_vem_do_ambiente(self, ambiente_llm):
        cliente = ClienteOpenAICompativel()
        assert cliente.modelo == "modelo-de-teste"
        assert str(cliente._cliente.base_url).startswith("https://exemplo.invalid/v1")
        assert cliente._cliente.timeout == 15.0
        assert cliente._cliente.max_retries == 0

    @pytest.mark.parametrize("variavel", ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"])
    def test_configuracao_incompleta(self, ambiente_llm, monkeypatch, variavel):
        monkeypatch.delenv(variavel)
        with pytest.raises(ErroClienteLLM, match=variavel):
            ClienteOpenAICompativel()

    def test_envia_parametros_com_saida_json(self, ambiente_llm):
        falso = _OpenAIDeMentira('{"acao": "fora_do_escopo"}')
        resposta = ClienteOpenAICompativel(falso).responder("oi", "PROMPT")

        assert resposta == '{"acao": "fora_do_escopo"}'
        [parametros] = falso.chamadas
        assert parametros["model"] == "modelo-de-teste"
        assert 0 <= parametros["temperature"] <= 0.2
        assert parametros["response_format"] == {"type": "json_object"}
        assert parametros["messages"] == [
            {"role": "system", "content": "PROMPT"},
            {"role": "user", "content": "oi"},
        ]

    def test_historico_vai_entre_o_sistema_e_a_mensagem_atual(self, ambiente_llm):
        falso = _OpenAIDeMentira("{}")
        historico = [
            {"role": "user", "content": "chegou mais JBL"},
            {"role": "assistant", "content": "Quantas?"},
        ]
        ClienteOpenAICompativel(falso).responder("10", "PROMPT", historico)
        assert falso.chamadas[0]["messages"] == [
            {"role": "system", "content": "PROMPT"},
            *historico,
            {"role": "user", "content": "10"},
        ]

    def test_sem_suporte_a_json_tenta_de_novo_sem_response_format(self, ambiente_llm):
        falso = _OpenAIDeMentira(
            _erro_http(
                openai.BadRequestError, 400, "response_format json_object not supported"
            ),
            '{"acao": "fora_do_escopo"}',
            '{"acao": "listar_estoque_baixo"}',
        )
        cliente = ClienteOpenAICompativel(falso)
        assert cliente.responder("oi", "P") == '{"acao": "fora_do_escopo"}'
        assert cliente.responder("oi", "P") == '{"acao": "listar_estoque_baixo"}'
        assert "response_format" in falso.chamadas[0]
        assert "response_format" not in falso.chamadas[1]
        assert "response_format" not in falso.chamadas[2]  # lembra da decisão

    def test_outro_erro_400_nao_desliga_a_saida_json(self, ambiente_llm):
        # A xAI responde chave inválida com 400, não 401.
        falso = _OpenAIDeMentira(
            _erro_http(openai.BadRequestError, 400, "Incorrect API key provided."),
            '{"acao": "fora_do_escopo"}',
        )
        cliente = ClienteOpenAICompativel(falso)
        with pytest.raises(ErroClienteLLM) as erro:
            cliente.responder("oi", "P")
        assert "Incorrect API key" in str(erro.value.__cause__)
        assert len(falso.chamadas) == 1  # não tentou de novo sem JSON
        cliente.responder("oi", "P")
        assert falso.chamadas[1]["response_format"] == {"type": "json_object"}

    def test_timeout_vira_erro_do_cliente(self, ambiente_llm):
        requisicao = httpx2.Request("POST", "https://exemplo.invalid")
        falso = _OpenAIDeMentira(openai.APITimeoutError(request=requisicao))
        with pytest.raises(ErroClienteLLM, match="demorou"):
            ClienteOpenAICompativel(falso).responder("oi", "P")

    def test_erro_de_autenticacao_nao_expoe_detalhes(self, ambiente_llm):
        falso = _OpenAIDeMentira(
            _erro_http(openai.AuthenticationError, 401, "org_123 chave inválida")
        )
        with pytest.raises(ErroClienteLLM) as erro:
            ClienteOpenAICompativel(falso).responder("oi", "P")
        assert str(erro.value) == "Não foi possível consultar a IA."

    def test_limite_de_uso_tem_mensagem_propria(self, ambiente_llm):
        falso = _OpenAIDeMentira(_erro_http(openai.RateLimitError, 429))
        with pytest.raises(ErroClienteLLM, match="limite de uso"):
            ClienteOpenAICompativel(falso).responder("oi", "P")

    def test_conteudo_vazio_vira_texto_vazio(self, ambiente_llm):
        falso = _OpenAIDeMentira(None)
        assert ClienteOpenAICompativel(falso).responder("oi", "P") == ""


# ---------------------------------------------------------------- log das chamadas


class TestLogDaIA:
    def test_grava_requisicao_e_resposta(self, ambiente_llm, monkeypatch, tmp_path):
        arquivo = tmp_path / "logs" / "llm.log"
        monkeypatch.setenv("LLM_LOG_ARQUIVO", str(arquivo))
        uso = SimpleNamespace(prompt_tokens=1400, completion_tokens=80)
        falso = _OpenAIDeMentira('{"acao": "fora_do_escopo"}')
        falso.chat.completions.create = _com_uso(falso, uso)

        ClienteOpenAICompativel(falso).responder(
            "qual a previsão?", "PROMPT DE SISTEMA"
        )

        log = arquivo.read_text(encoding="utf-8")
        assert "modelo: modelo-de-teste" in log
        assert "tokens: entrada 1400, saída 80" in log
        assert '"response_format": {"type": "json_object"}' in log
        assert "--- system\nPROMPT DE SISTEMA" in log
        assert "--- user\nqual a previsão?" in log
        assert '--- resposta do modelo\n{"acao": "fora_do_escopo"}' in log
        assert "chave-de-teste" not in log  # a chave da API nunca vai para o log

    def test_grava_erros(self, ambiente_llm, monkeypatch, tmp_path):
        arquivo = tmp_path / "llm.log"
        monkeypatch.setenv("LLM_LOG_ARQUIVO", str(arquivo))
        falso = _OpenAIDeMentira(_erro_http(openai.RateLimitError, 429, "limite"))
        with pytest.raises(ErroClienteLLM):
            ClienteOpenAICompativel(falso).responder("oi", "P")
        assert "--- ERRO\nRateLimitError: limite" in arquivo.read_text(encoding="utf-8")

    def test_acumula_chamadas(self, ambiente_llm, monkeypatch, tmp_path):
        arquivo = tmp_path / "llm.log"
        monkeypatch.setenv("LLM_LOG_ARQUIVO", str(arquivo))
        falso = _OpenAIDeMentira("{}", "{}")
        cliente = ClienteOpenAICompativel(falso)
        cliente.responder("um", "P")
        cliente.responder("dois", "P")
        assert arquivo.read_text(encoding="utf-8").count("=" * 80) == 2

    def test_vazio_desliga_o_log(self, ambiente_llm, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ClienteOpenAICompativel(_OpenAIDeMentira("{}")).responder("oi", "P")
        assert not (tmp_path / "logs").exists()

    def test_falha_ao_gravar_nao_quebra_a_chamada(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LLM_LOG_ARQUIVO", str(tmp_path))  # é uma pasta
        registrar_chamada({"model": "m", "messages": []}, 0.1, texto="{}")


def _com_uso(falso, uso):
    criar_original = falso.chat.completions.create

    def criar(**parametros):
        resposta = criar_original(**parametros)
        resposta.usage = uso
        return resposta

    return criar
