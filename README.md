# SeaBirdsCloud — Gerador de documentação HTML

Refatoração do gerador original, preservando o fluxo **template HTML → conteúdo Markdown → arquivo .html**, com imagens coladas em uma pasta escolhida. A interface roda no navegador e o processamento continua em Python. O histórico guarda rascunhos; o resultado principal é um arquivo HTML no seu site.

**Versão 3.0.0:** criação guiada, fonte Markdown portátil ao lado do HTML, validação de referências, lixeira integrada ao catálogo, operações acompanháveis, diagnóstico, backups completos e revisor local de português. Veja [Novidades e atualização](docs/STUDIO-3.md), [Revisor](docs/REVISOR.md) e [Backups](docs/BACKUPS.md).

## Usar no Windows

Na pasta da aplicação, abra **`start.cmd`** e acesse **http://127.0.0.1:8000**. O ambiente Python já foi preparado na instalação local desta entrega. Para uma cópia nova, instale Python 3.12/3.13 e execute:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe main.py
```

Ctrl+C no terminal encerra o servidor. No Linux: `bash start.sh`. O iniciador PowerShell também aceita um interpretador específico: `./start.ps1 -Python 'C:\caminho\python.exe'`.

## O mesmo fluxo da aplicação original

Os caminhos e opções ficam em **Configurar arquivos**, também acessível pelos resumos de template, saída e imagens. A área de trabalho oferece os modos **Dividido**, **Editor** e **Prévia**, além de expansão para concentrar a edição. O visual da aplicação é independente do template usado pelo HTML exportado.

1. **Selecionar template:** escolha seu HTML com o marcador `{{content}}`. Na instalação original, `templates/templete.html` é o padrão e foi preservado. Você pode digitar o caminho ou enviar o arquivo pelo navegador.
2. **Título da página:** substitui o `<title>` do template.
3. **Pasta de imagens:** escolha onde os PNG serão gravados.
4. **Caminho das imagens no HTML:** indique o caminho relativo usado pelo site. Ele pode ser diferente do caminho físico.
5. **Próximo índice:** configura a numeração `img-0.png`, `img-1.png` etc. Se o nome já existir, o programa avança para o próximo número livre.
6. **Local de saída:** escolha o arquivo `.html` que deve ser gerado.
7. Edite o conteúdo e use **Ctrl+V** para colar imagens. O programa grava o PNG na pasta selecionada, insere o Markdown, exibe uma miniatura e incrementa o índice.
8. Clique em **Gerar HTML** ou use **Ctrl+S**. O arquivo será escrito diretamente no local indicado. Uma cópia anterior é preservada se o arquivo já existir.

**Baixar HTML** faz o download de um único `.html`. Não exige ZIP nem cadastro de uma documentação interna. **Visualizar** aponta para o arquivo HTML de saída com `target="_blank"`. No Windows local, a aplicação abre o `file:///...` no navegador padrão, porque navegadores bloqueiam a navegação direta de HTTP para arquivos locais. No LXC, a visualização continua pela URL servida pelo aplicativo. Nenhuma dessas ações regenera o arquivo. A prévia ao lado mostra o rascunho atual usando seu template.

Exemplo de configuração no Windows:

```text
Template:                    C:\site\templates\projeto.html
Pasta das imagens:           C:\site\imagens\tutorial
Caminho das imagens no HTML: ../../imagens/tutorial
Arquivo HTML de saída:       C:\site\paginas\guias\tutorial.html
Raiz do site para a prévia:  C:\site
```

O HTML resultante mantém cabeçalho, rodapé, CSS, JavaScript e estrutura do template. A aplicação não substitui o template por um layout próprio. A prévia detecta a **raiz do site automaticamente** a partir do arquivo de saída e dos recursos existentes referenciados pelo template, incluindo caminhos como `../../css/styles.css`. O campo Raiz do site permite ajustar essa detecção manualmente. CSS com imports e imagens relativos à raiz também são resolvidos na prévia. Os arquivos precisam existir nessa estrutura; nenhum desses ajustes altera os caminhos no HTML exportado.

No acesso local Windows, os botões abrem seletores nativos quando o Tkinter está disponível. No LXC e quando o seletor nativo não está disponível, o aplicativo oferece um seletor de pastas/arquivos do servidor, com navegação e criação de pasta. Também é possível digitar qualquer caminho permitido ao usuário do serviço.

## Recursos preservados

- Markdown, títulos H1–H4, listas, links, imagens, código inline e blocos de código.
- Python-Markdown com `extra`, como no original: tabelas, notas de rodapé, listas de definição, atributos e Markdown dentro de HTML.
- HTML bruto no Markdown, habilitado por padrão, e destaque `| texto`.
- `{{link: URL | Texto}}`, `table`, `tablecard`, Code Card e opções de botão copiar. O HTML dos botões mantém `copiarCodigo(this)` para funcionar com o JavaScript do seu site.
- Construtor visual de tabelas com cabeçalhos, células multilinha, inserção/remoção de linhas e colunas e menu do botão direito.
- Busca no editor, resultados anterior/próximo, desfazer/refazer e atalhos de formatação. Os atalhos e botões estão descritos no Manual do aplicativo. Alguns atalhos reservados pelo navegador podem ser interceptados por ele; todas as ações também têm botão.
- Histórico do projeto atual, abertura de projetos antigos, leitura dos autosaves antigos, frequência em segundos e quantidade máxima de versões.
- Substituidor multilinha e formatador de HTML em pastas e subpastas, com filtro, seleção individual, confirmação e logs. As alterações são aplicadas nos arquivos selecionados. Cópias anteriores ficam em `data/file-backups/`.
- Alternância de tema, importação e download de Markdown.

A [matriz de compatibilidade](docs/COMPATIBILIDADE.md) mostra onde cada recurso foi mantido.

## Corrigir ou remover imagens

- **× na miniatura:** remove as referências da imagem no Markdown; **Ctrl+Z** restaura. O arquivo continua no disco. Apagar o Markdown manualmente também atualiza as miniaturas.
- **Gerenciar imagens → Mover:** escolha a pasta física correta e o caminho correspondente no HTML. As referências serão atualizadas, mantendo o texto alternativo. É possível usar essa pasta nas próximas colagens sem alterar o caminho das outras imagens.
- **Gerenciar imagens → Enviar à lixeira:** retira as referências e move os arquivos para uma lixeira recuperável. Selecione várias imagens para corrigir uma colagem em lote. Arquivos existentes no destino são preservados.
- **Filtro Na lixeira → Restaurar e inserir:** devolve o arquivo à pasta anterior e reinsere a imagem. Se o nome já existir, será escolhido outro nome livre.
- **Filtro Na lixeira → Excluir definitivamente:** apaga uma imagem da lixeira, com confirmação. Também é possível marcar várias e usar **Excluir selecionadas definitivamente**. Essa ação não pode ser desfeita.
- **Ler imagens de uma pasta:** encontra as imagens antigas salvas no local errado, mesmo que suas miniaturas não tenham sido mantidas pela versão anterior.

As miniaturas são associadas ao rascunho e continuam disponíveis ao reabrir o aplicativo. O catálogo fica em `data/image-catalog.json` e a lixeira em `data/image-trash/`; inclua ambos na cópia do diretório de dados. Gere o HTML novamente depois de corrigir as imagens para atualizar a página exportada.

## Excluir uma documentação completa

Em **Site e repositórios → Lixeira de páginas**, use **Excluir definitivamente**. A revisão mostra os cadastros e as imagens exclusivas que serão removidos junto da cópia do HTML. Imagens usadas em outros arquivos do site ou por páginas ainda na lixeira são preservadas. Depois revise e publique as remoções no GitHub. Consulte [Exclusão completa](docs/LIXEIRA-PAGINAS.md).

## Catálogo de documentações

Use **Adicionar ao catálogo** no editor para cadastrar o HTML gerado, com categoria, título, imagem, descrição e link. O título, o link e a primeira imagem do documento são sugeridos. Em **Site e repositórios → Catálogo de documentações**, é possível buscar, editar, mudar a categoria, remover cards e desfazer a última alteração.

O formulário altera o `js/projetos-conteudo.js` do próprio site, mantendo `dadosCategorias`, comentários e os demais cadastros. A configuração da página que exibe o catálogo fica salva por site; no seu caso é `paginas/projetos.html`. As URLs são calculadas em relação a essa página. O catálogo e as capas alteradas entram na revisão junto do HTML, sem incluir outros JavaScript. Consulte [Catálogo pelo navegador](docs/CATALOGO.md).

## Histórico e recuperação

O padrão é salvar o histórico a cada **60 segundos**, mantendo **10 versões**, configurável pela interface. O agendamento é periódico, inclusive durante edição contínua. O histórico não grava HTML automaticamente: gerar o arquivo continua sendo uma ação explícita.

As configurações de caminhos são preservadas por projeto. O SQLite em `data/seabirds.sqlite3` mantém rascunhos e revisões; os autosaves Markdown novos ficam em `data/historico/<projeto>/`. A pasta `historico/` antiga é lida sem apagar seus arquivos. Rascunhos da primeira versão web também são mantidos pela migração do banco.

Um rascunho local no navegador ajuda na recuperação se a conexão cair. Antes de sair com alterações pendentes, o navegador pede confirmação. Conflitos de gravação entre abas são detectados. Em caso de conflito, salve seu Markdown e reabra o projeto antes de continuar.

O botão **Backups** cria cópias completas protegidas por senha dos dados e sites cadastrados, com agendamento, download e restauração pelo navegador. Confira as pastas incluídas no painel. Consulte [Backups](docs/BACKUPS.md). Como alternativa, pare a aplicação e copie `data/` e as pastas externas onde guardou os HTML, templates e imagens. As imagens e páginas não ficam obrigatoriamente dentro do diretório de dados.

## Publicar no GitHub e executar o deploy no S3

Em **Site e repositórios → Configurar GitHub**, salve o nome, o e-mail e o token como segredo. A configuração também está acessível no clone e na revisão de publicação. O token é criptografado no servidor e não é devolvido ao navegador; campo vazio mantém o valor salvo. As próximas operações já usam a configuração, sem reiniciar o serviço. Consulte [Gerenciamento web do GitHub](docs/GITHUB-WEB.md) para atualização, remoção do token, prioridades e backup da chave.

O botão **Publicar** usa um clone local do repositório, como `perdixti/SeaBirdsCloud-site`. O workflow `deploy.yml` deste site já responde ao push na `main`, sincroniza o bucket S3 e invalida o CloudFront. As credenciais AWS continuam nos secrets do GitHub Actions.

1. Clique em **Publicar**, confira a **raiz do site (pasta do index.html)** e use **Gerar HTML e revisar**. A busca inclui HTML e imagens recursivamente, em todas as subpastas dessa raiz. O repositório é localizado pelo HTML de saída; caminhos antigos apontando para o gerador são corrigidos automaticamente. A pasta pode ser salva em Configurar arquivos → Publicação no GitHub.
2. Confira o repositório, o autor, os arquivos e a mensagem de commit. O HTML atual e as imagens associadas são pré-selecionados, incluindo imagens referenciadas no HTML gerado que ainda não estavam no catálogo. Outros HTML e imagens alterados dentro do site aparecem para seleção. Abra cada linha para consultar a diferença textual. As exclusões selecionadas também entram no commit.
3. Se a main local estiver atrás da remota, use **Atualizar main local**. A atualização usa somente avanço direto e preserva edições locais; havendo conflito ou divergência, resolva pelo Git e faça uma nova revisão.
4. Use **Fazer commit e publicar na main**. Apenas os arquivos selecionados entram no commit. Alterações já preparadas de outros arquivos permanecem no índice.
5. Abra o commit ou o GitHub Actions e use **Atualizar pipeline** para consultar a execução daquele commit. O sucesso do push e o resultado da pipeline são mostrados separadamente.

Revisões expiram em 15 minutos. Mudanças nos arquivos, no remoto ou na main invalidam a revisão. O envio não usa force push. Se o commit local for criado e o push falhar, use **Reenviar este commit**; não será criado um commit duplicado. O registro fica em `data/github-publications.json` e sobrevive ao reinício.

O Git precisa estar instalado e autenticado **na máquina/usuário do servidor**. No Windows, a autenticação HTTPS já configurada no Git Credential Manager pode ser reutilizada. No LXC, use SSH ou um token restrito ao repositório em `SEABIRDS_GITHUB_TOKEN`; para HTTPS com esse token, o aplicativo usa um helper de processo, sem colocar a credencial na URL, no histórico do documento ou no navegador. O lançador `data/.github-askpass.sh` contém apenas os caminhos do Python e do helper; o token é lido do ambiente do processo. A consulta ao Actions também tenta usar o helper Git existente. Um token fine-grained precisa de **Contents: write** para publicar e **Actions: read** para consultar a pipeline. Consulte a documentação de [tokens GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) e [execuções de workflows](https://docs.github.com/en/rest/actions/workflow-runs?apiVersion=2026-03-10).

Como alternativa à configuração pela interface, é possível preparar o clone manualmente:

```bash
git clone git@github.com:perdixti/SeaBirdsCloud-site.git /srv/seabirds/site
git -C /srv/seabirds/site config user.name "Seu nome"
git -C /srv/seabirds/site config user.email "seu-email-de-commit"
```

No LXC, faça isso como o usuário `seabirds` (por exemplo, `runuser -u seabirds -- git ...`) e mantenha os arquivos do site dentro de `/srv/seabirds`, autorizado no serviço. Configure as variáveis opcionais em `/etc/seabirds/seabirds.env` e reinicie o serviço. No Docker, o Git e o cliente SSH estão incluídos; o clone precisa estar no volume `/workspace` ou em uma pasta montada gravável pelo usuário do container. O clone, a identidade e as credenciais do Windows não são transferidos automaticamente para o LXC/container.

O workflow pode ser ajustado por `SEABIRDS_GITHUB_WORKFLOW` (padrão `deploy.yml`). A publicação aceita até 100 arquivos por commit, cada um até 10 MB; a revisão lista até 300 alterações/100 MB. A integração não altera o workflow nem configura recursos AWS.

## Editar o site e clonar repositórios

A aba **Site e repositórios** trabalha na cópia local do site. Selecione a pasta do `index.html`; a listagem inclui os HTML de suas subpastas e pode ser filtrada por título ou caminho. Os clones usados recentemente ficam disponíveis no seletor.

- **Editar HTML** abre o código completo da página existente. **Salvar HTML** e `Ctrl+S` gravam esse arquivo, preservando uma cópia anterior. Alterações externas desde a abertura bloqueiam a gravação; copie sua edição antes de recarregar o disco. O editor não reconverte o HTML para Markdown nem troca o template existente.
- **Excluir página** e **Excluir selecionadas** pedem confirmação e movem os HTML para uma lixeira privada em `data/page-trash`. É possível restaurá-los, inclusive depois de reiniciar a aplicação. Imagens e outros recursos compartilhados permanecem no site. A restauração recusa sobrescrever um arquivo existente.
- **Publicar alterações do site** abre a revisão dos HTML e imagens alterados ou removidos. Essa ação não gera novamente o documento aberto no editor Markdown. Confira a seleção e confirme o commit/push na `main`; a pipeline existente aplicará as remoções ao S3. Restaurar depois de publicar exige uma nova publicação para devolver a página ao site online.
- **Clonar repositório** aceita uma URL GitHub HTTPS ou SSH e uma pasta de destino nova. A autenticação é a do Git do servidor. A interface também permite configurar nome/email de commit apenas nesse clone. Uma pasta existente nunca é substituída.

O fluxo é: **clone local → editar/salvar → revisar → commit/push → GitHub Actions → S3**. O aplicativo não precisa baixar os arquivos do S3 para editar: os arquivos versionados no GitHub são a origem da cópia local. Na máquina atual, selecione `C:/Users/lucas/Desktop/Lucas/Estudos/seabirdscloud/SeaBirdsCloud-site`.

## VS Code Web na mesma cópia local

Em **Site e repositórios → Configurar editor**, conecte um editor que execute na mesma máquina do gerador. **Editor do site** abre uma nova aba com a pasta selecionada. Após salvar no editor, use **Atualizar páginas** e **Publicar alterações do site** no gerador.

No Windows, com VS Code instalado e disponível no PATH, use **Iniciar VS Code Web neste computador**. A interface apresenta os [termos do Visual Studio Code Server](https://aka.ms/vscode-server-license); só inicia após sua aceitação. O processo usa `127.0.0.1:8765`, autenticação por token e dados separados em `data/vscode-*`. A primeira execução pode baixar componentes do VS Code. A API de inicialização só aceita acesso pela própria máquina. O gerador exige VS Code 1.128.1 ou mais recente; mantenha-o atualizado. Fechar a aba do navegador mantém o processo em execução; reiniciar o computador o encerra, e o botão pode iniciá-lo novamente. Os testes desta entrega simularam a inicialização, sem aceitar os termos por você.

No Debian/LXC ou na EC2, o editor pode ficar hospedado junto do gerador. Atualize para a versão 3.0.0 e execute `bash deploy/install-web.sh` no servidor. Depois, use **Site e repositórios → Editor do site**. O editor abre no mesmo endereço, em `/editor/`, acessando a pasta selecionada do servidor. Ele inicia automaticamente com o servidor e usa senha própria; o computador do usuário só precisa do navegador.

O modo de desenvolvimento mantém HTTP e a porta pública 8000. O proxy encaminha o gerador para a porta interna 8001 e o editor para 8765, ambas em loopback. O link é relativo e também funciona no IP do LXC, sem fixar o DNS da EC2. A configuração de publicação Git continua sendo feita no gerador, com revisão antes do commit/push.

Veja [instalação e atualização do editor Web](docs/EDITOR-WEB.md), incluindo senhas, serviços, portas, migração para LXC e limites do HTTP. Para integrar um editor já existente, informe uma URL HTTP/HTTPS ou um caminho como `/editor/` em **Configurar editor**. `SEABIRDS_EDITOR_URL` permite administrar essa conexão no servidor e substitui uma URL antiga salva pela interface enquanto estiver definido.

## LXC Debian 13 no Proxmox

Na versão 2.5.0, caminhos absolutos digitados no seletor são confirmados diretamente e as permissões do servidor são exibidas na aba do site. Para atualizar um LXC ou usar um clone existente em `/opt`, consulte [Linux e LXC](docs/LINUX.md). Após instalar, prepare esse clone como root com `seabirds-configure-site '/opt/caminho-do-site'` e atualize a listagem na aplicação.

Crie um LXC Debian 13 não privilegiado. Um ponto inicial para uso pessoal é 1 vCPU, 512 MB–1 GB de RAM e espaço de disco proporcional às imagens; não é um dimensionamento medido. Copie o código para `/root/seabirds-src` dentro do LXC e execute como root **no LXC**:

```bash
cd /root/seabirds-src
bash deploy/install-debian.sh
systemctl status seabirds
journalctl -u seabirds -n 50 --no-pager
```

O instalador prepara o serviço, cria o usuário `seabirds`, gera uma senha e inicia a aplicação. Acesse `http://IP-DO-LXC:8000`, usuário `admin`. Consulte a senha em `/etc/seabirds/seabirds.env`. Os dados ficam em `/var/lib/seabirds` e a pasta **`/srv/seabirds`** é criada para seus templates, HTML e imagens.

Exemplo no LXC:

```text
Template:                    /srv/seabirds/templates/projeto.html
Pasta das imagens:           /srv/seabirds/imagens/tutorial
Caminho das imagens no HTML: ../../imagens/tutorial
Arquivo HTML de saída:       /srv/seabirds/paginas/guias/tutorial.html
Raiz do site para a prévia:  /srv/seabirds
```

**Os caminhos pertencem à máquina que executa o aplicativo.** Um servidor LXC não grava diretamente em `C:\...` do computador que abriu o navegador. Para usar um site compartilhado, monte a pasta dentro do LXC e dê acesso ao usuário `seabirds`. Ao usar uma pasta diferente de `/srv/seabirds`, autorize-a no serviço:

```ini
# systemctl edit seabirds
[Service]
ReadWritePaths=/caminho/do/site
```

Depois, rode `systemctl daemon-reload` e `systemctl restart seabirds`. Ajuste a propriedade/permissão da pasta para permitir escrita ao usuário do serviço. A instalação preserva a configuração e os dados existentes ao atualizar. Faça cópia dos dados e do site antes de uma atualização.

Para acesso público, use HTTPS no proxy reverso. `deploy/Caddyfile.example` contém um exemplo. A autenticação é HTTP Basic, de usuário único; não há permissões separadas por projeto.

## Docker Compose

```bash
docker compose up -d --build
```

Acesse http://127.0.0.1:8000. O volume `seabirds_data` fica em `/data`; o volume `seabirds_site` fica em **`/workspace`**, onde o programa pode gravar os arquivos do site. Use caminhos `/workspace/...` na interface.

Para trabalhar no site da sua máquina, troque o volume do site por um bind mount no Compose, por exemplo `./meu-site:/workspace`. No Linux, dê permissão de escrita ao UID/GID **10001**. No Windows com Docker Desktop, a pasta deve estar disponível para compartilhamento com o Docker.

Copie `.env.example` para `.env` para configurar porta, IP publicado e senha do Compose. Esse arquivo não é carregado pela execução Python direta. `docker compose down` preserva os volumes; **`down -v` apaga os volumes**. O build/execução do container e a instalação real no Debian ainda dependem de validação nesses destinos.

## Configuração

| Variável                 | Padrão Python | Uso                                                                             |
| ------------------------ | ------------- | ------------------------------------------------------------------------------- |
| `SEABIRDS_DATA_DIR`      | `./data`      | Banco, históricos e cópias anteriores                                           |
| `SEABIRDS_HOST`          | `127.0.0.1`   | Endereço de escuta                                                              |
| `SEABIRDS_PORT`          | `8000`        | Porta                                                                           |
| `SEABIRDS_USERNAME`      | `admin`       | Usuário HTTP Basic                                                              |
| `SEABIRDS_PASSWORD`      | vazio         | Senha; obrigatória para operações de arquivos por acesso remoto                 |
| `SEABIRDS_HISTORY_LIMIT` | `50`          | Limite para clientes antigos da API; a interface usa a configuração por projeto |
| `SEABIRDS_BIND`          | `127.0.0.1`   | Endereço publicado pelo Compose                                                 |

Limites: imagem até 10 MB/25 MP; Markdown até 1 milhão de caracteres; template enviado pelo navegador até 250 mil caracteres; operações em pasta até 5000 arquivos por busca e 10 MB por arquivo. Use pastas menores quando necessário. SQLite deve ficar em disco local, em uma instância do serviço.

A prévia é isolada do editor e não permite que scripts do template acessem a aplicação ou enviem formulários. O HTML gravado preserva os scripts originais sem essa política de prévia. Integrações que fazem chamadas de rede, como chatbots, devem ser verificadas no site publicado. Imagens coladas dependem do evento de colagem do navegador; o envio pelo botão Imagem é uma alternativa.

## Código e testes

```text
seabirds/
  renderer.py        Markdown e extensões compatíveis com o gerador
  filesystem.py      HTML, imagens numeradas, autosaves e ferramentas em pastas
  image_store.py     Catálogo persistente, movimentação e lixeira de imagens
  generator_api.py   Seletores, geração e visualização dos arquivos
  storage.py         Rascunhos, revisões e migração SQLite
  static/            Interface, editor e construtor de tabelas, sem build Node
  templates/         Cópia do template original e template independente opcional
legacy/              Código Tkinter original preservado
deploy/              Instalador Debian, systemd e proxy de exemplo
tests/               Regressões da conversão e dos fluxos em arquivos
```

```bash
python -m pip install -r requirements.lock
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check seabirds tests main.py
python -m ruff format --check seabirds tests main.py
```

O código antigo, o template personalizado e a pasta histórica original permanecem preservados. Para abrir a interface Tkinter antiga como alternativa, instale `ttkbootstrap`, `pillow`, `markdown`, `beautifulsoup4` e Tkinter no sistema e execute `python legacy/main.py`.

Veja o [relatório de validação](docs/VALIDACAO.md) para os testes executados e os limites da validação.
