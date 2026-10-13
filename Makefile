.PHONY: help install run seed test format

# 8000 costuma ser reservada pelo Windows (Hyper-V/WSL); troque com: make run PORT=9000
PORT ?= 8080

help: ## Lista todos os comandos disponíveis
	@echo "Comandos disponíveis:"
	@echo "  make install  Instala as dependências"
	@echo "  make run      Sobe a aplicação em modo desenvolvimento"
	@echo "  make seed     Cadastra itens de exemplo no banco"
	@echo "  make test     Roda os testes com cobertura"
	@echo "  make format   Formata o código com isort e black"
	@echo "  make help     Lista todos os comandos disponíveis"

install: ## Instala as dependências
	pip install -r requirements.txt

run: ## Sobe a aplicação em modo desenvolvimento
	uvicorn app.main:app --reload --port $(PORT)

seed: ## Cadastra itens de exemplo no banco
	python -m app.estoque.seed

test: ## Roda os testes com cobertura
	pytest --cov=app --cov-report=term-missing

format: ## Formata o código com isort e black
	isort app tests
	black app tests
