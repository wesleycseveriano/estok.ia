# estok.ia

Sistema simples de controle de estoque para o almoxarifado de TI.
Permite gerenciar itens por uma interface manual ou por um chat em linguagem natural com IA.

## Requisitos

- Python 3.11+

## Como instalar

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
make install            # ou: pip install -r requirements.txt
cp .env.example .env    # depois edite o .env com seus valores reais
```

## Como rodar

```bash
make run                # ou: uvicorn app.main:app --reload --port 8080
```

Acesse http://127.0.0.1:8080 (documentação da API em http://127.0.0.1:8080/docs).

> No Windows, a porta 8000 costuma estar reservada (Hyper-V/WSL/Docker) e gera
> `WinError 10013`. Por isso usamos 8080. Para usar outra: `make run PORT=9000`.

## Testes

```bash
make test               # ou: pytest --cov=app
```

Use `make help` para listar todos os comandos.
