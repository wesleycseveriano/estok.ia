from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.canais.chat_web import router as rotas_chat
from app.estoque.banco import criar_tabelas
from app.estoque.excecoes import ErroEstoque
from app.estoque.rotas import router as rotas_estoque
from app.estoque.rotas import tratar_erro_estoque

VERSAO = "0.1.0"
PAGINA_INICIAL = Path(__file__).parent / "static" / "index.html"


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    criar_tabelas()
    yield


app = FastAPI(title="estok.ia", version=VERSAO, lifespan=ciclo_de_vida)
app.add_exception_handler(ErroEstoque, tratar_erro_estoque)
app.include_router(rotas_estoque)
app.include_router(rotas_chat)


@app.get("/", include_in_schema=False)
def raiz():
    return FileResponse(PAGINA_INICIAL)


@app.get("/health")
def health():
    return {"status": "ok", "versao": VERSAO}
