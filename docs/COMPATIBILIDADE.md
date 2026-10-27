# Funcionalidades do gerador original

O fluxo principal voltou a ser selecionar template e caminhos, editar o conteúdo e gerar um arquivo HTML. SQLite e rascunhos são suporte ao histórico; não são o produto final.

| Recurso original                               | Onde está na versão refatorada                                                                               |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Selecionar template HTML                       | Campo Template, seletor nativo/local ou seletor de arquivos do servidor; também aceita envio pelo navegador  |
| Usar o template original                       | Padrão `templates/templete.html`; cópia compatível distribuída em `seabirds/templates/legacy.html`           |
| Título da página                               | Campo Título, aplicado ao `<title>` do template                                                              |
| Local de saída                                 | Campo Arquivo HTML de saída e botão Local de saída                                                           |
| Gerar HTML                                     | Botão Gerar HTML e Ctrl+S, gravando diretamente no caminho escolhido                                         |
| Publicação GitHub                              | Botão Publicar: gerar, revisar arquivos/diferenças, commit e push na main, retry e consulta da pipeline      |
| Páginas existentes                             | Lista recursiva do site, edição do HTML completo com backup e proteção contra alterações externas        |
| Exclusão de páginas                            | Confirmação individual/em lote, lixeira persistente, restauração e revisão das remoções sem regeneração   |
| Clone de repositórios                          | URL GitHub HTTPS/SSH, destino novo e identidade opcional por clone                                       |
| Editor Web local                               | Pasta compartilhada com code-server no LXC ou iniciador VS Code serve-web no Windows com aceite de termos |
| Visualizar                                     | Lê o HTML já gerado, sem substituir o arquivo                                                                |
| Pasta física das imagens                       | Campo Pasta onde as imagens serão salvas                                                                     |
| Caminho das imagens no HTML                    | Campo separado do caminho físico, aplicado a `img-N.png`                                                     |
| Índice manual da imagem                        | Campo Próximo índice, atualizado após cada gravação                                                          |
| Ctrl+V com imagem                              | Grava PNG numerado no diretório escolhido e insere o Markdown                                                |
| Miniatura da imagem                            | Galeria persistente abaixo do editor, ampliação, remoção com × e desfazer com Ctrl+Z                          |
| Corrigir imagens coladas                        | Gerenciar imagens: mover, seleção em lote, lixeira recuperável e leitura de pasta com imagens antigas        |
| Área de trabalho                                | Editor e prévia lado a lado, modos individuais, expansão e caminhos em Configurar arquivos                   |
| Upload de imagem                               | Botão Imagem, usando a mesma gravação e numeração                                                            |
| Markdown com Extra                             | Python-Markdown com `extra`, incluindo HTML, notas, atributos, listas de definição e Markdown dentro de HTML |
| `{{link: URL \| Texto}}`                       | Conversão em link/botão, com a opção original                                                                |
| `table` e `tablecard`                          | Conversão e construtores de tabela/card                                                                      |
| Editor visual de tabela                        | Cabeçalhos/células, dimensões, inserir acima/abaixo/esquerda/direita, remover linha/coluna e botão direito   |
| Code Card e copiar                             | Classes do site e chamada `copiarCodigo(this)` mantidas                                                      |
| Destaque com pipe                              | `\| texto` fora de tabelas Markdown                                                                          |
| Opções de geração                              | Link, TableCard, Table, copiar e Code Card; HTML bruto é habilitado por padrão                               |
| H1/H2/H3/H4, negrito, itálico, código e listas | Barra de ferramentas e atalhos do editor                                                                     |
| Ctrl+A, Ctrl+Z, Ctrl+Y                         | Seleção de texto e histórico de desfazer/refazer                                                             |
| Busca por texto                                | Ctrl+F ou Buscar, contagem e navegação anterior/próxima                                                      |
| Tema claro/escuro                              | Botão Tema                                                                                                   |
| Histórico do projeto atual                     | Botão correspondente, restauração em nova versão                                                             |
| Históricos de outros projetos                  | Botão Históricos de projetos, filtro e projetos recentes                                                     |
| Abrir autosaves antigos                        | Lista dos Markdown em `historico/*/autosave_*.md`, preservando os arquivos                                   |
| Frequência e máximo de históricos              | Configurar histórico; agendamento periódico e limite por projeto                                             |
| Substituição multilinha em pasta               | Aba Substituidor, busca recursiva, filtro, seleção, confirmação e alteração dos originais escolhidos         |
| Formatador em pasta                            | Aba Formatador, seleção/filtro, preservação de blocos de código e logs                                       |
| Manual                                         | Aba Manual, com fluxo e atalhos                                                                              |

No navegador, alguns atalhos de sistema são reservados e podem não chegar ao editor. A ação equivalente está disponível na barra. Seletores e gravações referem-se à máquina onde o backend roda: Windows local ou diretórios Linux/montados no LXC. A interface Tkinter original continua em `legacy/` para uso com a integração nativa anterior.

Correções em relação a falhas do legado: o contador de imagens evita sobrescrever um nome já existente, as revisões têm numeração consistente, a geração protege o arquivo de template e as ferramentas preservam cópias dos arquivos que alteram. Os limites de arquivo e as permissões do usuário do servidor continuam valendo.
