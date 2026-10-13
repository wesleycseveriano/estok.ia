from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.estoque.modelos import OrigemMovimentacao, TipoItem, TipoMovimentacao

Texto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class ItemCriar(BaseModel):
    tipo: TipoItem
    marca: Texto
    modelo: Texto
    quantidade: int = Field(default=0, ge=0, strict=True)


class ItemEditar(BaseModel):
    tipo: TipoItem
    marca: Texto
    modelo: Texto


class Movimento(BaseModel):
    quantidade: int = Field(gt=0, strict=True)


class ItemSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoItem
    marca: str
    modelo: str
    quantidade: int
    criado_em: datetime
    atualizado_em: datetime


class MovimentacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    tipo: TipoMovimentacao
    quantidade: int
    origem: OrigemMovimentacao
    criado_em: datetime
