from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.estoque import servico
from app.estoque.banco import obter_sessao
from app.estoque.excecoes import (
    ErroEstoque,
    EstoqueInsuficiente,
    ItemComSaldo,
    ItemDuplicado,
    ItemNaoEncontrado,
    QuantidadeInvalida,
)
from app.estoque.modelos import TipoItem
from app.estoque.schemas import (
    ItemCriar,
    ItemEditar,
    ItemSaida,
    MovimentacaoSaida,
    Movimento,
)

router = APIRouter(prefix="/api")

_STATUS_POR_ERRO = {
    ItemNaoEncontrado: status.HTTP_404_NOT_FOUND,
    ItemDuplicado: status.HTTP_409_CONFLICT,
    EstoqueInsuficiente: status.HTTP_409_CONFLICT,
    ItemComSaldo: status.HTTP_409_CONFLICT,
    QuantidadeInvalida: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def tratar_erro_estoque(_: Request, erro: ErroEstoque) -> JSONResponse:
    codigo = _STATUS_POR_ERRO.get(type(erro), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(status_code=codigo, content={"detail": erro.mensagem})


@router.get("/tipos", response_model=list[str])
def listar_tipos():
    return [tipo.value for tipo in TipoItem]


@router.get("/itens", response_model=list[ItemSaida])
def listar_itens(
    tipo: TipoItem | None = None,
    texto: str | None = None,
    sessao: Session = Depends(obter_sessao),
):
    return servico.buscar_itens(sessao, tipo=tipo, texto=texto)


@router.post("/itens", response_model=ItemSaida, status_code=status.HTTP_201_CREATED)
def criar_item(dados: ItemCriar, sessao: Session = Depends(obter_sessao)):
    return servico.cadastrar_item(sessao, **dados.model_dump())


# Declarada antes de /itens/{item_id} para não ser capturada por ela.
@router.get("/itens/estoque-baixo", response_model=list[ItemSaida])
def estoque_baixo(sessao: Session = Depends(obter_sessao)):
    return servico.listar_estoque_baixo(sessao)


@router.get("/itens/{item_id}", response_model=ItemSaida)
def obter_item(item_id: int, sessao: Session = Depends(obter_sessao)):
    return servico.obter_item(sessao, item_id)


@router.put("/itens/{item_id}", response_model=ItemSaida)
def editar_item(
    item_id: int, dados: ItemEditar, sessao: Session = Depends(obter_sessao)
):
    return servico.editar_item(sessao, item_id, **dados.model_dump())


@router.delete("/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_item(item_id: int, sessao: Session = Depends(obter_sessao)):
    servico.excluir_item(sessao, item_id)


@router.post("/itens/{item_id}/entrada", response_model=ItemSaida)
def registrar_entrada(
    item_id: int, dados: Movimento, sessao: Session = Depends(obter_sessao)
):
    return servico.registrar_entrada(sessao, item_id, dados.quantidade)


@router.post("/itens/{item_id}/saida", response_model=ItemSaida)
def registrar_saida(
    item_id: int, dados: Movimento, sessao: Session = Depends(obter_sessao)
):
    return servico.registrar_saida(sessao, item_id, dados.quantidade)


@router.get("/movimentacoes", response_model=list[MovimentacaoSaida])
def listar_movimentacoes(
    item_id: int | None = None, sessao: Session = Depends(obter_sessao)
):
    return servico.listar_movimentacoes(sessao, item_id=item_id)
