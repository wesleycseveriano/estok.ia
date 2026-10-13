from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TipoItem(StrEnum):
    MOUSE = "Mouse"
    TECLADO = "Teclado"
    MONITOR = "Monitor"
    HEADSET = "Headset"
    HD = "HD"
    SSD = "SSD"
    MEMORIA_RAM = "Memória RAM"
    PLACA_MAE = "Placa-mãe"
    PROCESSADOR = "Processador"
    FONTE = "Fonte"
    CABO_DE_REDE = "Cabo de rede"
    SWITCH = "Switch"
    ROTEADOR = "Roteador"
    LICENCA_DE_SOFTWARE = "Licença de software"
    OUTRO = "Outro"


class TipoMovimentacao(StrEnum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class OrigemMovimentacao(StrEnum):
    MANUAL = "manual"
    CHAT = "chat"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _enum_por_valor(enum_cls, tamanho: int) -> SAEnum:
    """Grava o valor do enum (ex.: "Memória RAM") em vez do nome do membro."""
    return SAEnum(
        enum_cls,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,
        length=tamanho,
    )


class Item(Base):
    __tablename__ = "itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoItem] = mapped_column(_enum_por_valor(TipoItem, 30))
    marca: Mapped[str] = mapped_column(String(100))
    modelo: Mapped[str] = mapped_column(String(100))
    quantidade: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )

    movimentacoes: Mapped[list["Movimentacao"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


# tipo + marca + modelo é único, sem diferenciar maiúsculas de minúsculas.
Index(
    "uq_itens_tipo_marca_modelo",
    Item.tipo,
    func.lower(Item.marca),
    func.lower(Item.modelo),
    unique=True,
)


class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("itens.id"))
    tipo: Mapped[TipoMovimentacao] = mapped_column(
        _enum_por_valor(TipoMovimentacao, 10)
    )
    quantidade: Mapped[int] = mapped_column(Integer)
    origem: Mapped[OrigemMovimentacao] = mapped_column(
        _enum_por_valor(OrigemMovimentacao, 10)
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    item: Mapped[Item] = relationship(back_populates="movimentacoes")
