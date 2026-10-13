"""Acesso ao modelo de linguagem, sempre atrás da interface ClienteLLM."""

import logging
from abc import ABC, abstractmethod

import openai

from app.config import obter_config_llm

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 15.0
TEMPERATURA = 0.0


class ErroClienteLLM(Exception):
    """O modelo não pôde ser consultado (configuração, rede, timeout, etc.)."""


class ClienteLLM(ABC):
    @abstractmethod
    def responder(self, mensagem: str, prompt_sistema: str) -> str:
        """Envia a mensagem do usuário com o prompt de sistema e devolve o texto."""


class ClienteOpenAICompativel(ClienteLLM):
    """Cliente para qualquer API compatível com OpenAI (hoje, a Groq)."""

    def __init__(self, cliente_openai=None):
        config = obter_config_llm()
        faltando = [
            nome
            for nome, chave in (
                ("LLM_API_KEY", "api_key"),
                ("LLM_BASE_URL", "base_url"),
                ("LLM_MODEL", "modelo"),
            )
            if not config[chave]
        ]
        if faltando:
            raise ErroClienteLLM(
                f"Configuração da IA incompleta: defina {', '.join(faltando)} no .env."
            )

        self.modelo = config["modelo"]
        self._cliente = cliente_openai or openai.OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=TIMEOUT_SEGUNDOS,
            max_retries=0,  # o timeout de 15 s vale para a chamada inteira
        )
        self._usar_json = True

    def responder(self, mensagem: str, prompt_sistema: str) -> str:
        parametros = {
            "model": self.modelo,
            "temperature": TEMPERATURA,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensagem},
            ],
        }
        try:
            if self._usar_json:
                try:
                    resposta = self._cliente.chat.completions.create(
                        **parametros, response_format={"type": "json_object"}
                    )
                except openai.BadRequestError as erro:
                    # Alguns provedores devolvem 400 para outros problemas
                    # (ex.: a xAI com chave inválida); só recua se o erro
                    # for mesmo sobre a saída JSON.
                    if "response_format" not in str(erro).lower():
                        raise
                    self._usar_json = False
                    resposta = self._cliente.chat.completions.create(**parametros)
            else:
                resposta = self._cliente.chat.completions.create(**parametros)
        except openai.APITimeoutError as erro:
            raise ErroClienteLLM("A IA demorou demais para responder.") from erro
        except openai.RateLimitError as erro:
            logger.warning("Limite de uso da IA atingido: %s", erro)
            raise ErroClienteLLM(
                "A IA atingiu o limite de uso. Aguarde alguns segundos e tente de novo."
            ) from erro
        except openai.OpenAIError as erro:
            # O detalhe (que pode conter dados da conta) vai só para o log.
            logger.warning("Falha ao consultar a IA: %s", erro)
            raise ErroClienteLLM("Não foi possível consultar a IA.") from erro

        return resposta.choices[0].message.content or ""
