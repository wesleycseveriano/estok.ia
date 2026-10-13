Você vai me ajudar a construir um MVP chamado estok.ia (repositório
"estok-ia"), um sistema simples de controle de estoque para o almoxarifado
de TI de uma empresa.

O estoque pode ser controlado de duas formas, que usam as mesmas regras:
1. Interface manual: cadastrar itens, dar entrada, dar saída, editar e
   excluir, por formulários e botões.
2. Chat dentro da própria aplicação: o usuário escreve em linguagem natural
   ("chegaram 10 mouses Logitech M90", "saiu 1 HD Seagate 1TB",
   "o que está acabando?", "quantos teclados temos?") e o sistema executa
   a ação correspondente.

Modelo de dados propositalmente simples. Cada item tem apenas:
- tipo: um destes valores fixos: Mouse, Teclado, Monitor, Headset, HD, SSD,
  Memória RAM, Placa-mãe, Processador, Fonte, Cabo de rede, Switch,
  Roteador, Licença de software, Outro
- marca (ex.: Logitech, Dell, Seagate, Microsoft)
- modelo (ex.: M90, KB216, Barracuda 1TB, Windows 11 Pro)
- quantidade

Stack obrigatória:
- Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 com SQLite
- pytest para testes
- Front-end: uma única página HTML com JavaScript puro, servida pelo FastAPI
  (sem React ou build de front-end)
- LLM: xAI (Grok), usando o SDK oficial "openai" para Python apontando para
  a base URL da xAI. Base URL, modelo e chave vêm de variáveis de ambiente,
  para ser possível trocar de provedor compatível com OpenAI sem alterar
  código.

Arquitetura em três camadas (respeite essa separação):
1. Núcleo de estoque (app/estoque/): regras de negócio e banco de dados.
   Não conhece a IA nem o chat. A interface manual e o chat usam este
   mesmo núcleo.
2. Interpretador (app/interpretador/): recebe texto, usa a IA para gerar uma
   ação estruturada, valida e chama o núcleo. A IA NUNCA executa nada
   diretamente; ela só sugere uma ação, e o código valida e executa.
3. Canais (app/canais/): adaptadores de entrada. O primeiro é o chat web.
   No futuro pode existir um canal Telegram reaproveitando as camadas 1 e 2.

Regras gerais:
- Nunca coloque segredos no código. Use .env (fora do Git) e .env.example.
- Toda chamada à IA deve ficar atrás de uma interface, para ser substituída
  por um mock nos testes. Os testes nunca chamam a IA de verdade.
- Código e mensagens ao usuário em português; nomes de variáveis podem ser
  em português, de forma consistente.
- Mantenha tudo simples. Não adicione campos ou funcionalidades além do que
  a etapa pedir. Se algo estiver ambíguo, pergunte antes.
- Ao terminar, liste os arquivos criados/alterados e como testar.