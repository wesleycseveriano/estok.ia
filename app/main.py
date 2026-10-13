from fastapi import FastAPI

VERSAO = "0.1.0"

app = FastAPI(title="estok.ia", version=VERSAO)


@app.get("/")
def raiz():
    return {"mensagem": "estok.ia no ar"}


@app.get("/health")
def health():
    return {"status": "ok", "versao": VERSAO}
