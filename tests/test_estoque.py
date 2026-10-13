import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.estoque import servico
from app.estoque.banco import obter_sessao
from app.estoque.excecoes import (
    EstoqueInsuficiente,
    ItemComSaldo,
    ItemDuplicado,
    ItemNaoEncontrado,
    QuantidadeInvalida,
)
from app.estoque.modelos import Base, OrigemMovimentacao, TipoItem, TipoMovimentacao
from app.main import app


@pytest.fixture
def fabrica_sessao():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def sessao(fabrica_sessao):
    with fabrica_sessao() as s:
        yield s


@pytest.fixture
def cliente(fabrica_sessao):
    def _sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def _mouse(sessao, quantidade=10):
    return servico.cadastrar_item(sessao, TipoItem.MOUSE, "Logitech", "M90", quantidade)


# ---------------------------------------------------------------- serviço


class TestCadastro:
    def test_cadastra_item(self, sessao):
        item = _mouse(sessao, 5)
        assert item.id is not None
        assert item.tipo == TipoItem.MOUSE
        assert (item.marca, item.modelo, item.quantidade) == ("Logitech", "M90", 5)
        assert item.criado_em is not None and item.atualizado_em is not None

    def test_quantidade_inicial_zero_e_permitida(self, sessao):
        assert _mouse(sessao, 0).quantidade == 0

    def test_quantidade_inicial_gera_movimentacao_de_entrada(self, sessao):
        item = _mouse(sessao, 5)
        [mov] = servico.listar_movimentacoes(sessao, item_id=item.id)
        assert mov.tipo == TipoMovimentacao.ENTRADA
        assert mov.quantidade == 5
        assert mov.origem == OrigemMovimentacao.MANUAL

    def test_quantidade_inicial_zero_nao_gera_movimentacao(self, sessao):
        item = _mouse(sessao, 0)
        assert servico.listar_movimentacoes(sessao, item_id=item.id) == []

    @pytest.mark.parametrize("quantidade", [-1, 1.5, "3", True])
    def test_quantidade_inicial_invalida(self, sessao, quantidade):
        with pytest.raises(QuantidadeInvalida):
            _mouse(sessao, quantidade)

    def test_remove_espacos_de_marca_e_modelo(self, sessao):
        item = servico.cadastrar_item(sessao, TipoItem.MOUSE, "  Logitech ", " M90  ")
        assert (item.marca, item.modelo) == ("Logitech", "M90")

    def test_duplicado_gera_erro(self, sessao):
        _mouse(sessao)
        with pytest.raises(ItemDuplicado):
            _mouse(sessao)

    def test_duplicado_ignora_maiusculas(self, sessao):
        _mouse(sessao)
        with pytest.raises(ItemDuplicado):
            servico.cadastrar_item(sessao, TipoItem.MOUSE, "LOGITECH", "m90")

    def test_mesma_marca_e_modelo_com_tipo_diferente_e_permitido(self, sessao):
        _mouse(sessao)
        item = servico.cadastrar_item(sessao, TipoItem.OUTRO, "Logitech", "M90")
        assert item.id is not None


class TestEdicao:
    def test_edita_item(self, sessao):
        item = _mouse(sessao)
        editado = servico.editar_item(
            sessao, item.id, TipoItem.TECLADO, "Dell", "KB216"
        )
        assert (editado.tipo, editado.marca, editado.modelo) == (
            TipoItem.TECLADO,
            "Dell",
            "KB216",
        )
        assert editado.quantidade == 10

    def test_editar_mantendo_os_mesmos_dados_nao_e_duplicado(self, sessao):
        item = _mouse(sessao)
        editado = servico.editar_item(
            sessao, item.id, TipoItem.MOUSE, "logitech", "M90"
        )
        assert editado.marca == "logitech"

    def test_editar_para_combinacao_existente_gera_erro(self, sessao):
        _mouse(sessao)
        outro = servico.cadastrar_item(sessao, TipoItem.MOUSE, "Dell", "MS116")
        with pytest.raises(ItemDuplicado):
            servico.editar_item(sessao, outro.id, TipoItem.MOUSE, "LOGITECH", "m90")

    def test_editar_item_inexistente(self, sessao):
        with pytest.raises(ItemNaoEncontrado):
            servico.editar_item(sessao, 999, TipoItem.MOUSE, "X", "Y")


class TestExclusao:
    def test_exclui_item_zerado(self, sessao):
        item = _mouse(sessao, 2)
        servico.registrar_saida(sessao, item.id, 2)
        servico.excluir_item(sessao, item.id)
        with pytest.raises(ItemNaoEncontrado):
            servico.obter_item(sessao, item.id)
        assert servico.listar_movimentacoes(sessao, item_id=item.id) == []

    def test_nao_exclui_item_com_saldo(self, sessao):
        item = _mouse(sessao, 1)
        with pytest.raises(ItemComSaldo):
            servico.excluir_item(sessao, item.id)

    def test_excluir_item_inexistente(self, sessao):
        with pytest.raises(ItemNaoEncontrado):
            servico.excluir_item(sessao, 999)


class TestMovimentacoes:
    def test_entrada_soma_ao_estoque(self, sessao):
        item = _mouse(sessao, 10)
        assert servico.registrar_entrada(sessao, item.id, 5).quantidade == 15

    def test_saida_subtrai_do_estoque(self, sessao):
        item = _mouse(sessao, 10)
        assert servico.registrar_saida(sessao, item.id, 4).quantidade == 6

    def test_saida_pode_zerar_o_estoque(self, sessao):
        item = _mouse(sessao, 3)
        assert servico.registrar_saida(sessao, item.id, 3).quantidade == 0

    def test_saida_nao_deixa_estoque_negativo(self, sessao):
        item = _mouse(sessao, 3)
        with pytest.raises(EstoqueInsuficiente):
            servico.registrar_saida(sessao, item.id, 4)
        assert servico.obter_item(sessao, item.id).quantidade == 3

    @pytest.mark.parametrize("quantidade", [0, -2, 1.5, "2", None, True])
    @pytest.mark.parametrize(
        "operacao", [servico.registrar_entrada, servico.registrar_saida]
    )
    def test_quantidade_invalida(self, sessao, operacao, quantidade):
        item = _mouse(sessao, 10)
        with pytest.raises(QuantidadeInvalida):
            operacao(sessao, item.id, quantidade)
        assert servico.obter_item(sessao, item.id).quantidade == 10

    @pytest.mark.parametrize(
        "operacao", [servico.registrar_entrada, servico.registrar_saida]
    )
    def test_item_inexistente(self, sessao, operacao):
        with pytest.raises(ItemNaoEncontrado):
            operacao(sessao, 999, 1)

    def test_registra_historico_com_origem(self, sessao):
        item = _mouse(sessao, 0)
        servico.registrar_entrada(sessao, item.id, 5)
        servico.registrar_saida(sessao, item.id, 2, origem=OrigemMovimentacao.CHAT)

        saida, entrada = servico.listar_movimentacoes(sessao)  # mais recente primeiro
        assert (entrada.tipo, entrada.quantidade, entrada.origem) == (
            TipoMovimentacao.ENTRADA,
            5,
            OrigemMovimentacao.MANUAL,
        )
        assert (saida.tipo, saida.quantidade, saida.origem) == (
            TipoMovimentacao.SAIDA,
            2,
            OrigemMovimentacao.CHAT,
        )

    def test_listar_movimentacoes_filtra_por_item(self, sessao):
        mouse = _mouse(sessao, 1)
        servico.cadastrar_item(sessao, TipoItem.TECLADO, "Dell", "KB216", 2)
        movs = servico.listar_movimentacoes(sessao, item_id=mouse.id)
        assert [m.item_id for m in movs] == [mouse.id]


class TestConsultas:
    @pytest.fixture
    def itens(self, sessao):
        servico.cadastrar_item(sessao, TipoItem.MOUSE, "Logitech", "M90", 10)
        servico.cadastrar_item(sessao, TipoItem.TECLADO, "Logitech", "K120", 2)
        servico.cadastrar_item(sessao, TipoItem.TECLADO, "Dell", "KB216", 3)
        servico.cadastrar_item(sessao, TipoItem.HD, "Seagate", "Barracuda 1TB", 4)

    def test_buscar_todos(self, sessao, itens):
        assert len(servico.buscar_itens(sessao)) == 4

    def test_buscar_por_tipo(self, sessao, itens):
        resultado = servico.buscar_itens(sessao, tipo=TipoItem.TECLADO)
        assert {i.modelo for i in resultado} == {"K120", "KB216"}

    def test_buscar_por_texto_na_marca_sem_diferenciar_maiusculas(self, sessao, itens):
        resultado = servico.buscar_itens(sessao, texto="logi")
        assert {i.modelo for i in resultado} == {"M90", "K120"}

    def test_buscar_por_texto_no_modelo(self, sessao, itens):
        resultado = servico.buscar_itens(sessao, texto="barracuda")
        assert [i.marca for i in resultado] == ["Seagate"]

    def test_buscar_por_tipo_e_texto(self, sessao, itens):
        resultado = servico.buscar_itens(sessao, tipo=TipoItem.TECLADO, texto="dell")
        assert [i.modelo for i in resultado] == ["KB216"]

    def test_estoque_baixo_usa_limite_padrao_3(self, sessao, itens, monkeypatch):
        monkeypatch.delenv("ESTOQUE_BAIXO_LIMITE", raising=False)
        resultado = servico.listar_estoque_baixo(sessao)
        assert [i.modelo for i in resultado] == ["K120", "KB216"]

    def test_estoque_baixo_respeita_variavel_de_ambiente(
        self, sessao, itens, monkeypatch
    ):
        monkeypatch.setenv("ESTOQUE_BAIXO_LIMITE", "4")
        resultado = servico.listar_estoque_baixo(sessao)
        assert [i.modelo for i in resultado] == ["K120", "KB216", "Barracuda 1TB"]


# ---------------------------------------------------------------- API REST


def _criar_via_api(cliente, **dados):
    corpo = {"tipo": "Mouse", "marca": "Logitech", "modelo": "M90", "quantidade": 5}
    corpo.update(dados)
    return cliente.post("/api/itens", json=corpo)


class TestApi:
    def test_listar_tipos(self, cliente):
        resposta = cliente.get("/api/tipos")
        assert resposta.status_code == 200
        assert resposta.json() == [t.value for t in TipoItem]
        assert "Memória RAM" in resposta.json()

    def test_criar_item_retorna_201(self, cliente):
        resposta = _criar_via_api(cliente, tipo="Memória RAM")
        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["tipo"] == "Memória RAM"
        assert corpo["quantidade"] == 5
        assert {"id", "criado_em", "atualizado_em"} <= corpo.keys()

    def test_criar_duplicado_retorna_409(self, cliente):
        _criar_via_api(cliente)
        resposta = _criar_via_api(cliente, marca="logitech")
        assert resposta.status_code == 409
        assert "Já existe" in resposta.json()["detail"]

    @pytest.mark.parametrize(
        "dados",
        [
            {"tipo": "Impressora"},
            {"marca": "   "},
            {"modelo": ""},
            {"quantidade": -1},
            {"quantidade": 1.5},
            {"quantidade": "3"},
        ],
    )
    def test_criar_com_dados_invalidos_retorna_422(self, cliente, dados):
        assert _criar_via_api(cliente, **dados).status_code == 422

    def test_obter_item(self, cliente):
        item_id = _criar_via_api(cliente).json()["id"]
        resposta = cliente.get(f"/api/itens/{item_id}")
        assert resposta.status_code == 200
        assert resposta.json()["modelo"] == "M90"

    def test_obter_item_inexistente_retorna_404(self, cliente):
        resposta = cliente.get("/api/itens/999")
        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "Item 999 não encontrado."

    def test_listar_com_filtros(self, cliente):
        _criar_via_api(cliente)
        _criar_via_api(cliente, tipo="Teclado", marca="Dell", modelo="KB216")
        assert len(cliente.get("/api/itens").json()) == 2
        por_tipo = cliente.get("/api/itens", params={"tipo": "Teclado"}).json()
        assert [i["modelo"] for i in por_tipo] == ["KB216"]
        por_texto = cliente.get("/api/itens", params={"texto": "logi"}).json()
        assert [i["modelo"] for i in por_texto] == ["M90"]

    def test_listar_com_tipo_invalido_retorna_422(self, cliente):
        assert cliente.get("/api/itens", params={"tipo": "Xpto"}).status_code == 422

    def test_editar_item(self, cliente):
        item_id = _criar_via_api(cliente).json()["id"]
        resposta = cliente.put(
            f"/api/itens/{item_id}",
            json={"tipo": "Teclado", "marca": "Dell", "modelo": "KB216"},
        )
        assert resposta.status_code == 200
        assert resposta.json()["tipo"] == "Teclado"

    def test_editar_para_duplicado_retorna_409(self, cliente):
        _criar_via_api(cliente)
        outro_id = _criar_via_api(cliente, modelo="M100").json()["id"]
        resposta = cliente.put(
            f"/api/itens/{outro_id}",
            json={"tipo": "Mouse", "marca": "Logitech", "modelo": "m90"},
        )
        assert resposta.status_code == 409

    def test_editar_inexistente_retorna_404(self, cliente):
        resposta = cliente.put(
            "/api/itens/999", json={"tipo": "Mouse", "marca": "X", "modelo": "Y"}
        )
        assert resposta.status_code == 404

    def test_excluir_item_zerado_retorna_204(self, cliente):
        item_id = _criar_via_api(cliente, quantidade=0).json()["id"]
        assert cliente.delete(f"/api/itens/{item_id}").status_code == 204
        assert cliente.get(f"/api/itens/{item_id}").status_code == 404

    def test_excluir_item_com_saldo_retorna_409(self, cliente):
        item_id = _criar_via_api(cliente).json()["id"]
        resposta = cliente.delete(f"/api/itens/{item_id}")
        assert resposta.status_code == 409
        assert "quantidade 0" in resposta.json()["detail"]

    def test_excluir_inexistente_retorna_404(self, cliente):
        assert cliente.delete("/api/itens/999").status_code == 404

    def test_entrada_e_saida(self, cliente):
        item_id = _criar_via_api(cliente, quantidade=5).json()["id"]
        entrada = cliente.post(f"/api/itens/{item_id}/entrada", json={"quantidade": 3})
        assert entrada.status_code == 200
        assert entrada.json()["quantidade"] == 8
        saida = cliente.post(f"/api/itens/{item_id}/saida", json={"quantidade": 8})
        assert saida.status_code == 200
        assert saida.json()["quantidade"] == 0

    def test_saida_maior_que_estoque_retorna_409(self, cliente):
        item_id = _criar_via_api(cliente, quantidade=2).json()["id"]
        resposta = cliente.post(f"/api/itens/{item_id}/saida", json={"quantidade": 3})
        assert resposta.status_code == 409
        assert "Estoque insuficiente" in resposta.json()["detail"]

    @pytest.mark.parametrize("operacao", ["entrada", "saida"])
    @pytest.mark.parametrize("quantidade", [0, -1, 1.5, "2"])
    def test_movimento_com_quantidade_invalida_retorna_422(
        self, cliente, operacao, quantidade
    ):
        item_id = _criar_via_api(cliente).json()["id"]
        resposta = cliente.post(
            f"/api/itens/{item_id}/{operacao}", json={"quantidade": quantidade}
        )
        assert resposta.status_code == 422

    @pytest.mark.parametrize("operacao", ["entrada", "saida"])
    def test_movimento_em_item_inexistente_retorna_404(self, cliente, operacao):
        resposta = cliente.post(f"/api/itens/999/{operacao}", json={"quantidade": 1})
        assert resposta.status_code == 404

    def test_estoque_baixo(self, cliente, monkeypatch):
        monkeypatch.setenv("ESTOQUE_BAIXO_LIMITE", "3")
        _criar_via_api(cliente, quantidade=10)
        _criar_via_api(cliente, modelo="M100", quantidade=3)
        _criar_via_api(cliente, modelo="M200", quantidade=0)
        resposta = cliente.get("/api/itens/estoque-baixo")
        assert resposta.status_code == 200
        assert [i["modelo"] for i in resposta.json()] == ["M200", "M100"]

    def test_listar_movimentacoes(self, cliente):
        item_id = _criar_via_api(cliente, quantidade=5).json()["id"]
        cliente.post(f"/api/itens/{item_id}/saida", json={"quantidade": 2})
        resposta = cliente.get("/api/movimentacoes")
        assert resposta.status_code == 200
        assert [(m["tipo"], m["quantidade"], m["origem"]) for m in resposta.json()] == [
            ("saida", 2, "manual"),
            ("entrada", 5, "manual"),
        ]
