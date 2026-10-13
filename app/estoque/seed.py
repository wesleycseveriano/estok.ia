"""Cadastra itens de exemplo. Uso: python -m app.estoque.seed (ou make seed).

Pode ser executado mais de uma vez: itens já cadastrados são ignorados.
"""

from app.estoque import servico
from app.estoque.banco import SessaoLocal, criar_tabelas
from app.estoque.excecoes import ItemDuplicado
from app.estoque.modelos import TipoItem

ITENS_INICIAIS = [
    (TipoItem.MOUSE, "Logitech", "M90", 25),
    (TipoItem.TECLADO, "Dell", "KB216", 18),
    (TipoItem.MONITOR, "Dell", "P2422H", 6),
    (TipoItem.HEADSET, "JBL", "Quantum 100", 2),
    (TipoItem.HD, "Seagate", "Barracuda 1TB", 4),
    (TipoItem.SSD, "Kingston", "A400 480GB", 1),
    (TipoItem.MEMORIA_RAM, "Kingston", "Fury Beast 8GB DDR4", 10),
    (TipoItem.PLACA_MAE, "ASUS", "Prime H510M", 3),
    (TipoItem.PROCESSADOR, "Intel", "Core i5-12400", 0),
    (TipoItem.FONTE, "Corsair", "CV550", 5),
    (TipoItem.CABO_DE_REDE, "Furukawa", "Cat6", 40),
    (TipoItem.LICENCA_DE_SOFTWARE, "Microsoft", "Windows 11 Pro", 2),
]


def popular() -> None:
    criar_tabelas()
    cadastrados = 0
    with SessaoLocal() as sessao:
        for tipo, marca, modelo, quantidade in ITENS_INICIAIS:
            try:
                servico.cadastrar_item(sessao, tipo, marca, modelo, quantidade)
                cadastrados += 1
            except ItemDuplicado:
                pass
    print(
        f"{cadastrados} item(ns) cadastrado(s); "
        f"{len(ITENS_INICIAIS) - cadastrados} já existiam."
    )


if __name__ == "__main__":
    popular()
