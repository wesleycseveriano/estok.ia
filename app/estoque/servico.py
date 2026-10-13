"""Regras de negócio do estoque. Não conhece HTTP, IA nem chat."""

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import obter_limite_estoque_baixo
from app.estoque.excecoes import (
    EstoqueInsuficiente,
    ItemComSaldo,
    ItemDuplicado,
    ItemNaoEncontrado,
    QuantidadeInvalida,
)
from app.estoque.modelos import (
    Item,
    Movimentacao,
    OrigemMovimentacao,
    TipoItem,
    TipoMovimentacao,
)


def _eh_inteiro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_quantidade_movimento(quantidade) -> None:
    if not _eh_inteiro(quantidade) or quantidade <= 0:
        raise QuantidadeInvalida("A quantidade deve ser um número inteiro maior que 0.")


def _garantir_unico(
    sessao: Session,
    tipo: TipoItem,
    marca: str,
    modelo: str,
    ignorar_id: int | None = None,
) -> None:
    consulta = select(Item.id).where(
        Item.tipo == tipo,
        func.lower(Item.marca) == marca.lower(),
        func.lower(Item.modelo) == modelo.lower(),
    )
    if ignorar_id is not None:
        consulta = consulta.where(Item.id != ignorar_id)
    if sessao.scalar(consulta) is not None:
        raise ItemDuplicado(tipo, marca, modelo)


def _salvar(sessao: Session, item: Item) -> None:
    """Commit tratando a restrição de unicidade do banco como ItemDuplicado."""
    try:
        sessao.commit()
    except IntegrityError:
        sessao.rollback()
        raise ItemDuplicado(item.tipo, item.marca, item.modelo)
    sessao.refresh(item)


def obter_item(sessao: Session, item_id: int) -> Item:
    item = sessao.get(Item, item_id)
    if item is None:
        raise ItemNaoEncontrado(item_id)
    return item


def cadastrar_item(
    sessao: Session,
    tipo: TipoItem,
    marca: str,
    modelo: str,
    quantidade: int = 0,
    origem: OrigemMovimentacao = OrigemMovimentacao.MANUAL,
) -> Item:
    if not _eh_inteiro(quantidade) or quantidade < 0:
        raise QuantidadeInvalida(
            "A quantidade inicial deve ser um número inteiro maior ou igual a 0."
        )
    tipo = TipoItem(tipo)
    marca, modelo = marca.strip(), modelo.strip()
    _garantir_unico(sessao, tipo, marca, modelo)

    item = Item(tipo=tipo, marca=marca, modelo=modelo, quantidade=quantidade)
    if quantidade > 0:
        # O saldo inicial fica registrado no histórico como uma entrada.
        item.movimentacoes.append(
            Movimentacao(
                tipo=TipoMovimentacao.ENTRADA, quantidade=quantidade, origem=origem
            )
        )
    sessao.add(item)
    _salvar(sessao, item)
    return item


def editar_item(
    sessao: Session, item_id: int, tipo: TipoItem, marca: str, modelo: str
) -> Item:
    item = obter_item(sessao, item_id)
    tipo = TipoItem(tipo)
    marca, modelo = marca.strip(), modelo.strip()
    _garantir_unico(sessao, tipo, marca, modelo, ignorar_id=item_id)

    item.tipo, item.marca, item.modelo = tipo, marca, modelo
    _salvar(sessao, item)
    return item


def excluir_item(sessao: Session, item_id: int) -> None:
    item = obter_item(sessao, item_id)
    if item.quantidade != 0:
        raise ItemComSaldo(item.quantidade)
    sessao.delete(item)
    sessao.commit()


def _movimentar(
    sessao: Session,
    item_id: int,
    tipo: TipoMovimentacao,
    quantidade: int,
    origem: OrigemMovimentacao,
) -> Item:
    _validar_quantidade_movimento(quantidade)
    item = obter_item(sessao, item_id)

    if tipo == TipoMovimentacao.SAIDA:
        if quantidade > item.quantidade:
            raise EstoqueInsuficiente(item.quantidade, quantidade)
        item.quantidade -= quantidade
    else:
        item.quantidade += quantidade

    item.movimentacoes.append(
        Movimentacao(
            tipo=tipo, quantidade=quantidade, origem=OrigemMovimentacao(origem)
        )
    )
    _salvar(sessao, item)
    return item


def registrar_entrada(
    sessao: Session,
    item_id: int,
    quantidade: int,
    origem: OrigemMovimentacao = OrigemMovimentacao.MANUAL,
) -> Item:
    return _movimentar(sessao, item_id, TipoMovimentacao.ENTRADA, quantidade, origem)


def registrar_saida(
    sessao: Session,
    item_id: int,
    quantidade: int,
    origem: OrigemMovimentacao = OrigemMovimentacao.MANUAL,
) -> Item:
    return _movimentar(sessao, item_id, TipoMovimentacao.SAIDA, quantidade, origem)


def buscar_itens(
    sessao: Session, tipo: TipoItem | None = None, texto: str | None = None
) -> list[Item]:
    consulta = select(Item).order_by(Item.tipo, Item.marca, Item.modelo)
    if tipo is not None:
        consulta = consulta.where(Item.tipo == TipoItem(tipo))
    if texto and texto.strip():
        padrao = f"%{texto.strip()}%"
        consulta = consulta.where(
            or_(Item.marca.ilike(padrao), Item.modelo.ilike(padrao))
        )
    return list(sessao.scalars(consulta))


def listar_estoque_baixo(sessao: Session) -> list[Item]:
    limite = obter_limite_estoque_baixo()
    consulta = (
        select(Item)
        .where(Item.quantidade <= limite)
        .order_by(Item.quantidade, Item.tipo, Item.marca)
    )
    return list(sessao.scalars(consulta))


def listar_movimentacoes(
    sessao: Session, item_id: int | None = None
) -> list[Movimentacao]:
    consulta = select(Movimentacao).order_by(
        Movimentacao.criado_em.desc(), Movimentacao.id.desc()
    )
    if item_id is not None:
        consulta = consulta.where(Movimentacao.item_id == item_id)
    return list(sessao.scalars(consulta))
