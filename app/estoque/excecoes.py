class ErroEstoque(Exception):
    """Base para todos os erros de regra de negócio do estoque."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class ItemNaoEncontrado(ErroEstoque):
    def __init__(self, item_id: int):
        super().__init__(f"Item {item_id} não encontrado.")
        self.item_id = item_id


class ItemDuplicado(ErroEstoque):
    def __init__(self, tipo: str, marca: str, modelo: str):
        super().__init__(f"Já existe um item {tipo} {marca} {modelo} cadastrado.")


class EstoqueInsuficiente(ErroEstoque):
    def __init__(self, disponivel: int, solicitado: int):
        super().__init__(
            f"Estoque insuficiente: há {disponivel} unidade(s) e foram "
            f"solicitadas {solicitado}."
        )
        self.disponivel = disponivel
        self.solicitado = solicitado


class ItemComSaldo(ErroEstoque):
    def __init__(self, quantidade: int):
        super().__init__(
            f"Só é possível excluir itens com quantidade 0 "
            f"(quantidade atual: {quantidade})."
        )
        self.quantidade = quantidade


class QuantidadeInvalida(ErroEstoque):
    pass
