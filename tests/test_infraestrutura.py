"""Peças que os outros testes substituem: banco real, ciclo de vida, seed e a
fiação do chat. Nada aqui toca o estok.db nem chama a IA de verdade."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

import app.main as modulo_main
from app.canais import chat_web
from app.config import obter_limite_estoque_baixo
from app.estoque import banco, seed, servico
from app.estoque.excecoes import ItemDuplicado
from app.estoque.modelos import TipoItem
from app.interpretador.cliente_llm import ErroClienteLLM

# ---------------------------------------------------------------- banco e app


def test_criar_tabelas_cria_itens_e_movimentacoes(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(banco, "engine", engine)
    banco.criar_tabelas()
    assert set(inspect(engine).get_table_names()) == {"itens", "movimentacoes"}
    engine.dispose()


def test_obter_sessao_entrega_e_fecha_uma_sessao():
    gerador = banco.obter_sessao()
    sessao = next(gerador)
    assert isinstance(sessao, Session)
    with pytest.raises(StopIteration):
        next(gerador)


def test_app_cria_as_tabelas_ao_subir(monkeypatch):
    chamadas = []
    monkeypatch.setattr(modulo_main, "criar_tabelas", lambda: chamadas.append(1))
    with TestClient(modulo_main.app):
        pass
    assert chamadas == [1]


# ---------------------------------------------------------------- configuração


@pytest.mark.parametrize("valor", ["abc", "", "2.5"])
def test_limite_invalido_usa_o_padrao_3(monkeypatch, valor):
    monkeypatch.setenv("ESTOQUE_BAIXO_LIMITE", valor)
    assert obter_limite_estoque_baixo() == 3


# ---------------------------------------------------------------- serviço


def test_banco_recusa_duplicado_mesmo_sem_a_checagem_previa(sessao, monkeypatch):
    """Simula dois cadastros iguais simultâneos: a checagem passa nos dois e
    só a restrição única do banco segura o segundo."""
    servico.cadastrar_item(sessao, TipoItem.MOUSE, "Logitech", "M90")
    monkeypatch.setattr(servico, "_garantir_unico", lambda *args, **kwargs: None)

    with pytest.raises(ItemDuplicado):
        servico.cadastrar_item(sessao, TipoItem.MOUSE, "LOGITECH", "m90")
    assert len(servico.buscar_itens(sessao)) == 1  # sessão segue utilizável


# ---------------------------------------------------------------- seed


def test_seed_cadastra_12_itens_e_nao_duplica(fabrica_sessao, monkeypatch, capsys):
    monkeypatch.setattr(seed, "SessaoLocal", fabrica_sessao)
    monkeypatch.setattr(seed, "criar_tabelas", lambda: None)

    seed.popular()
    assert "12 item(ns) cadastrado(s); 0 já existiam." in capsys.readouterr().out
    seed.popular()
    assert "0 item(ns) cadastrado(s); 12 já existiam." in capsys.readouterr().out

    with fabrica_sessao() as sessao:
        itens = servico.buscar_itens(sessao)
        baixos = servico.listar_estoque_baixo(sessao)
    assert len(itens) == 12
    assert len({i.tipo for i in itens}) >= 10  # variedade de tipos
    assert baixos  # alguns itens começam abaixo do limite


# ---------------------------------------------------------------- chat web


def test_dependencias_do_chat_sao_unicas_por_processo():
    assert chat_web.obter_pendencias() is chat_web.obter_pendencias()
    assert chat_web.obter_memoria() is chat_web.obter_memoria()
    assert chat_web.obter_cliente_llm() is chat_web.obter_cliente_llm()


def test_cliente_real_so_e_criado_na_primeira_mensagem(monkeypatch):
    criados = []

    class ClienteDeMentira:
        def __init__(self):
            criados.append(self)

        def responder(self, mensagem, prompt_sistema, historico=()):
            return f"{mensagem}|{len(historico)}"

    monkeypatch.setattr(chat_web, "ClienteOpenAICompativel", ClienteDeMentira)
    cliente = chat_web._ClienteSobDemanda()
    assert criados == []

    assert cliente.responder("oi", "P") == "oi|0"
    assert cliente.responder("de novo", "P", [{"role": "user", "content": "x"}]) == (
        "de novo|1"
    )
    assert len(criados) == 1


def test_configuracao_incompleta_vira_erro_na_mensagem_e_nao_na_subida(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    cliente = chat_web._ClienteSobDemanda()  # não falha ao criar
    with pytest.raises(ErroClienteLLM, match="LLM_API_KEY"):
        cliente.responder("oi", "P")
