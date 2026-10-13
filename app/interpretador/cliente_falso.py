from app.interpretador.cliente_llm import ClienteLLM


class ClienteLLMFalso(ClienteLLM):
    """Devolve respostas pré-definidas, em ordem. Usado nos testes."""

    def __init__(self, *respostas: str | Exception):
        self._respostas = list(respostas)
        self.chamadas: list[tuple[str, str]] = []  # (mensagem, prompt_sistema)

    def responder(self, mensagem: str, prompt_sistema: str) -> str:
        self.chamadas.append((mensagem, prompt_sistema))
        if not self._respostas:
            raise AssertionError("ClienteLLMFalso sem respostas pré-definidas.")
        resposta = self._respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
