from pathlib import Path

from app.estoque.modelos import Item, TipoItem

ARQUIVO_PROMPT = Path(__file__).parent / "prompt_sistema.md"


def montar_prompt_sistema(itens: list[Item]) -> str:
    modelo = ARQUIVO_PROMPT.read_text(encoding="utf-8")
    tipos = ", ".join(tipo.value for tipo in TipoItem)
    if itens:
        linhas = "\n".join(
            f"{item.id} | {item.tipo.value} | {item.marca} | {item.modelo}"
            for item in itens
        )
    else:
        linhas = "(nenhum item cadastrado)"
    return modelo.replace("{{TIPOS}}", tipos).replace("{{ITENS}}", linhas)
