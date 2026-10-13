from fastapi.testclient import TestClient

from app.main import VERSAO, app

cliente = TestClient(app)


def test_raiz_responde():
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert resposta.json() == {"mensagem": "estok.ia no ar"}


def test_health_retorna_status_e_versao():
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "versao": VERSAO}
