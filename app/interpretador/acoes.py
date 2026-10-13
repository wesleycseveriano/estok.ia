"""Ações estruturadas que o modelo pode sugerir. O código valida antes de usar."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, TypeAdapter

from app.estoque.modelos import TipoItem

TextoOpcional = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=100)
]


class AcaoEntrada(BaseModel):
    acao: Literal["entrada"]
    item_id: int = Field(strict=True)
    quantidade: int = Field(gt=0, strict=True)


class AcaoSaida(BaseModel):
    acao: Literal["saida"]
    item_id: int = Field(strict=True)
    quantidade: int = Field(gt=0, strict=True)


class AcaoConsultar(BaseModel):
    acao: Literal["consultar"]
    tipo: TipoItem | None = None
    texto: TextoOpcional = None


class AcaoListarEstoqueBaixo(BaseModel):
    acao: Literal["listar_estoque_baixo"]


class AcaoEsclarecer(BaseModel):
    acao: Literal["esclarecer"]
    pergunta: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class AcaoForaDoEscopo(BaseModel):
    acao: Literal["fora_do_escopo"]


class AcaoNaoEntendida(BaseModel):
    """Gerada pelo próprio interpretador (nunca aceita do modelo)."""

    acao: Literal["nao_entendido"] = "nao_entendido"
    motivo: str  # para log/depuração; não é mostrado ao usuário


AcaoDoModelo = Annotated[
    AcaoEntrada
    | AcaoSaida
    | AcaoConsultar
    | AcaoListarEstoqueBaixo
    | AcaoEsclarecer
    | AcaoForaDoEscopo,
    Field(discriminator="acao"),
]

Acao = AcaoDoModelo | AcaoNaoEntendida

validador_acao = TypeAdapter(AcaoDoModelo)
