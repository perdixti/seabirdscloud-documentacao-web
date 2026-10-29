# Validação — fluxo de geração HTML

## Ajustes 3.0.2 — 29/10/2026

- Suíte de 203 casos: **195 aprovados e 8 ignorados** no Windows/Python 3.12; **202 aprovados e 1 ignorado** em Linux/Python 3.12 e em Linux/Python 3.13. Os casos ignorados dependem da plataforma/configuração. O aviso do adaptador httpx do TestClient continua sem falha.
- Reproduzidos os textos das capturas: `Meu testo fala sobre cachorro` → `Meu texto fala sobre cachorro.`, início de frase `lápis.` → `Lápis.` e nome próprio preservado. O verbo correto em `Eu testo o servidor.` continua igual. Casos de concordância sobrepostos corrigidos numa passagem.
- Geração com raiz vazia inferida pelo destino do HTML, capa relativa ao Markdown e primeira imagem sem registro de miniatura. Capa ausente/ambígua e raiz incompatível recusadas sem alterar HTML ou catálogo. Seletor de capa filtra imagens.
- Falha simulada na gravação do catálogo recuperou exatamente o HTML anterior em CP1252, sem fonte parcial.
- DOM: contagem e posições das sugestões restantes após correção automática, aprovação posterior e desfazer; capa inválida preservando o formulário, seletor preservando categoria/descrição e campos normalizados. As 23 verificações do editor e regressões de seletor Linux, site, exclusão e GitHub Web passaram.
- Navegador com site sintético: correção automática, desfazer, aprovação manual das três correções das capturas, geração HTML, validação da capa e abertura/salvamento do catálogo sem repetir a raiz; um único card atualizado. Nenhuma publicação real executada.
- Medição Linux final: **274,2 MB de pico residente**, uma CPU disponível, limite de memória virtual de 450 MB, revisão de 49 mil caracteres e criação/restauração de backup com 32 MB de dados; 2,9 segundos no total nesse ambiente. VS Code Web continua fora da medição.

A validação foi feita em dados temporários. Documentos reais, catálogo do site do usuário, credenciais e arquivos do LXC não foram alterados pelos testes.


## Correção visual 3.0.1 — 29/10/2026

- A barra de revisão foi movida para dentro do painel do editor, preservando as quatro linhas do layout principal. Corrigido o alinhamento do seletor, que herdava a direção vertical dos formulários.
- Navegador: 1920 × 1080, 1366 × 768 e 390 × 844, sem rolagem horizontal. Barra com 54 px nas telas maiores; editor e prévia preenchendo o painel. Modo expandido conferido em notebook e celular, com os dois painéis dentro da altura disponível.
- As 23 verificações de integração do editor e os testes DOM de revisão, automático, desfazer e assistente passaram. Não houve alteração no processamento dos documentos.
- O aviso de CSS ausente na prévia de um template sem raiz configurada continua indicando um arquivo do site não localizado; selecione a pasta que contém o index.html para resolver as referências do template.


## Executado na versão 3.0.0 — 29/10/2026

- Suíte de 194 casos: Windows/Python 3.12 com **186 aprovados e 8 ignorados**; Linux/Python 3.12 e 3.13 com **193 aprovados e 1 ignorado** em cada execução. Os casos ignorados dependem da plataforma ou de configuração opcional. Há um aviso de depreciação do adaptador httpx do TestClient, sem falha nos testes.
- Criação guiada, geração coordenada de HTML/fonte/card, reabertura portátil, mudança externa no HTML, atualização sem duplicar card e falha no catálogo sem gravação parcial.
- Lixeira/restauração de HTML, fonte e card juntos; exclusão definitiva da fonte e imagens exclusivas. Imagens com o mesmo nome em outras pastas não são confundidas. Casos legados continuam cobertos.
- Verificação de referências locais, diferença de caixa, recursos ausentes, catálogo, páginas sem card e diagnóstico sem devolução de segredos. Nenhum link externo é consultado pela auditoria.
- Backup completo com dados, segredos e sites; migração de caminhos; arquivos adicionais preservados; senha incorreta, caminhos inválidos, retenção de agendados, envio maior que o limite antigo da API e recuperação após falha simulada.
- Fila persistida, operação duplicada, reinício, autenticação, confirmação para restauração e redação de segredos em erros de validação.
- Revisor local: acentos, dicionário, pontuação, concordância simples, palavras ignoradas, proteção de código/URLs, offsets com emoji e limite de texto. API contextual testada somente com respostas simuladas, sem chamadas pagas.
- DOM: sugestões/automático/desfazer/Ctrl+Z, resultado atrasado, segredo mascarado, assistente com campos preservados, geração acompanhável e 23 verificações do editor completo; regressões do seletor Linux, site, publicação e exclusão aprovadas.
- Navegador contra servidor temporário com site sintético: seis correções aplicadas e desfeitas, comandos e imagens preservados, painel de backups e auditoria com zero erros no site de teste. Evidência visual entregue em studio-3-revisor.png.
- Medição Linux: **274,3 MB de pico residente**, afinidade de uma CPU, limite de memória virtual de 450 MB, revisão de 49 mil caracteres, criação e restauração de backup com 32 MB de dados, 6,8 segundos no total. O VS Code Web é separado e não foi incluído. A medição não substitui um teste de carga no servidor final.

Nenhum documento real foi transmitido a um provedor de IA; nenhum push ao GitHub ou deploy S3 foi realizado. A EC2 e o LXC reais não foram atualizados.

## Histórico da versão 2.9.0

Data: 28/10/2026. Versão 2.9.0: exclusão definitiva de uma documentação completa.

## Executado na versão 2.9.0

- Suíte de 170 casos: Windows/Python 3.12 com **162 aprovados e 8 ignorados**; Linux/Python 3.12 com **169 aprovados e 1 ignorado**.
- Exclusão de páginas já na lixeira após reiniciar, remoção de todos os cadastros equivalentes no catálogo, capa e imagens exclusivas. Registros ativos das imagens removidas também saem do catálogo de imagens. Comentários, BOM/CRLF, outros cards e propriedades extras preservados.
- Imagens compartilhadas por HTML, CSS, srcset, cards e outras páginas ainda na lixeira preservadas. Links base, URLs codificadas e arquivos legados CP1252/UTF-16 exercitados. Arquivos externos, imagens sem relação com a página e destinos de links simbólicos mantidos.
- Revisão desatualizada, página recriada no mesmo caminho, arquivo de lixeira alterado, catálogo inválido, outra raiz e tentativa de sair da lixeira bloqueados. Falha simulada de gravação restaurou catálogo, imagens e HTML recuperável.
- API exige autenticação, mesma origem, revisão válida e confirmação explícita. A integração Git publica as remoções de HTML/imagens e a edição do catálogo juntas somente em remoto bare local, com normalização CRLF habilitada.
- DOM: nomes como texto, revisão antes da exclusão, confirmação obrigatória, cancelamento, erro sem fechar a revisão, atualização da lixeira e publicação somente por ação posterior. Regressão de Site e repositórios aprovada.
- Navegador: novo botão na lixeira e revisão real contra servidor temporário Windows com arquivos sintéticos; lista de duas imagens exclusivas e logo compartilhado preservado. A exclusão definitiva foi executada pelos testes de API, sem excluir conteúdo real do usuário pela interface.

Nenhum site real foi excluído, nenhum commit foi enviado ao GitHub e nenhum deploy no S3 foi disparado. O servidor EC2/LXC real não foi atualizado pelo agente.

## Histórico da versão 2.8.0

Data: 28/10/2026. Versão 2.8.0: catálogo das documentações pelo navegador.

## Executado na versão 2.8.0

- Suíte de 154 casos: Linux/Python 3.12.3 e 3.13.18 com **153 aprovados e 1 ignorado**; Windows/Python 3.12.14 com **147 aprovados e 7 ignorados**. Sintaxe JavaScript e estilo Python conferidos.
- Catálogo: adição em categoria existente/nova, edição/mudança de categoria sem duplicar a página, remoção de card mantendo HTML/imagens, cópia anterior e desfazer depois de reiniciar. Conflitos com edições externas recusam sobrescrever e preservam os campos no formulário.
- Preservação de comentários, BOM/CRLF, nomes com Unicode/emoji, objetos com propriedades extras e código fora dos dados. Casos de listas vazias, numa única linha e com vírgulas finais. A leitura não executa o JavaScript; campos calculados ou sintaxe inválida são recusados.
- URLs: caminhos relativos à página do catálogo, conversão de caminhos físicos Windows/Linux, espaços/acentos codificados, recusa de protocolos externos e de caminhos fora da raiz. Textos novos escapados para o HTML dos cards.
- Git: diferença textual e pré-seleção do catálogo e das capas alteradas. Um teste publica HTML, PNG e catálogo juntos em remoto bare local, preservando README previamente no stage e excluindo outros JavaScript do escopo.
- DOM: prefill, agrupamento/filtro, dados exibidos como texto, confirmação de descarte, erro de conflito sem perda de campos, salvar/editar/desfazer e revisão sem publicação automática.
- Navegador em Linux: cópia do catálogo real com 21 categorias e 179 projetos; inclusão de um card de teste na categoria Linux e reabertura do cadastro após recarregar. A revisão mostrou HTML, capa e catálogo selecionados juntos. O arquivo original do site foi preservado. A interface adaptou o formulário com cabeçalho visível e área de conteúdo com rolagem.

A EC2 e o LXC reais não foram acessados nem atualizados pelo agente. Nenhum commit de teste foi enviado ao GitHub nem disparou deploy no S3. Os testes de publicação usaram remotos bare locais, e a edição do catálogo real foi feita exclusivamente em cópia temporária.

## Histórico da versão 2.7.0

Data: 28/10/2026. Versão 2.7.0: nome, e-mail e token como segredo pelo gerenciamento web.

## Executado na versão 2.7.0

- Suíte de 135 casos: Linux/Python 3.12 com **134 aprovados e 1 ignorado**; Windows/Python 3.12 com **128 aprovados e 7 ignorados**. Estilo Python e sintaxe JavaScript conferidos.
- Gravação do token com Fernet, persistência após reiniciar, permissões 0700/0600 no Linux, campo vazio mantendo o segredo, substituição e remoção sem reativar a variável de ambiente. Perda da chave permite salvar outro token pela própria interface.
- API autenticada e com proteção de origem: segredo ausente das respostas de sucesso e de validação, inclusive entradas com tipo inválido, quebra de linha ou tamanho excessivo. Nenhum texto do token em catálogos de publicação.
- Token e autor salvos pela API são usados imediatamente pelo clone e pela publicação na mesma aplicação. O teste cria um clone e faz commit/push somente num remoto bare local. O autor ausente falha antes de alterar o índice; configurar pela web desbloqueia a mesma revisão.
- DOM isolado confirmou máscara de senha, campo vazio ao reabrir, manutenção sem reenviar o segredo, erro visível, revisão preservando seleção e mensagem, e ausência de publicação automática ao salvar as configurações.
- Navegador contra Linux: abriu Configurar GitHub, salvou nome/e-mail/token sintéticos e confirmou configuração após recarregar. O campo de segredo ficou vazio. O repositório e os arquivos usados eram exclusivamente de teste. O formulário informa a limitação de transporte em HTTP.
- Nova dependência validada: cryptography 50.0.2. A atualização do servidor inclui instalação de dependências com cópia do código anterior; dados, clone e configurações ficam preservados.

O servidor real EC2/LXC não foi acessado nem atualizado pelo agente. Nenhum token real do usuário foi solicitado ou usado na validação e nenhum commit foi enviado ao GitHub/S3. O instalador de atualização completo com pip/systemd ainda não foi executado em uma instalação real; sua sintaxe Bash foi conferida.

## Histórico da versão 2.6.0

Data: 28/10/2026. Versão 2.6.0: editor hospedado no servidor, com acesso pelo navegador no mesmo endereço do gerador.

## Executado na versão 2.6.0

- Suíte de 123 casos: Linux/Python 3.12 com **122 aprovados e 1 ignorado**; Windows/Python 3.12 com **116 aprovados e 7 ignorados**. Verificações de estilo Python e sintaxe JavaScript aprovadas.
- URL de editor relativa e absoluta, pasta com espaços/Unicode, persistência após reinício e recusa de URLs ambíguas, credenciais e portas inválidas. A conexão gerenciada pelo servidor substitui a URL antiga de loopback sem apagar as preferências do usuário; a API impede sobrescrever essa conexão pela interface.
- DOM isolado: o botão Editor do site usa o mesmo host e porta, abre nova aba com a pasta correta e mostra os controles de configuração gerenciada. A regressão existente de listagem, edição, conflitos, exclusão/restauração, clone e publicação também passou.
- code-server oficial 4.143.1 e Caddy oficial 2.11.7 executados em pasta Linux temporária. O navegador acessou HTTP pelo IP do Linux, autenticou no editor, abriu uma pasta de teste com espaços, alterou o index.html e salvou com Ctrl+S. A gravação foi confirmada no disco e pela leitura da mesma página na API do gerador. A sessão de edição exercitou a conexão do editor através de `/editor/` e do proxy.
- HTTP real: gerador exige autenticação (401), editor redireciona para login, `/editor` redireciona para `/editor/`, login funciona no subcaminho e as duas aplicações compartilham a mesma porta externa.
- Três unidades systemd transitórias sob usuário comum, em árvore temporária de `/opt`, validaram gerador, editor e proxy com `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes` e escrita restrita ao estado e site de teste. Os três serviços responderam corretamente e foram removidos ao terminar.
- Caddy validou as configurações geradas para portas 8000/8001 e 80/9001. A sintaxe dos instaladores foi conferida em Bash; os argumentos de portas conflitantes, inválidas e com caracteres de comando foram recusados.

Os testes usaram apenas arquivos, senhas e pastas sintéticas. O instalador completo com apt e a transição de porta no servidor real da EC2 não foram executados pelo agente; não houve acesso remoto autenticado à EC2. Nenhum commit foi enviado ao GitHub nem publicação ao S3. A configuração HTTP solicitada não oferece criptografia de transporte e limita recursos do navegador que exigem contexto seguro, como webviews de algumas extensões.

## Histórico da validação 2.5.0

Versão 2.5.0: revisão de compatibilidade Linux, preservando o gerador de HTML e as operações em arquivos da aplicação original.

## Executado anteriormente

- Suíte de 113 casos: Linux/Python 3.12.3 e 3.13.18 com **112 aprovados e 1 ignorado** (abertura nativa Windows); Windows/Python 3.12.14 com **106 aprovados e 7 ignorados** (permissões e preparador Linux). Inclui arquivos, listas, prévia, imagens, publicação e gestão do site.
- Compatibilidade Linux: testes reais de permissões sob usuário comum, diretórios absolutos com espaços/acentos/aspas, URI file, rejeição de caminho Windows, inexistente sem retorno silencioso à pasta pai, navegação com entradas inacessíveis, arquivo HTML sem leitura, preservação de modos POSIX ao gravar e arquivos privados novos com modo 0600.
- Serviços Linux transitórios: reprodução em `/opt` de clone pertencente ao root, bloqueio por `ProtectSystem=strict` mesmo após corrigir o dono e liberação do diretório exato. Com UID 1000, passaram geração/recursos CSS, duas imagens, edição com backup, lixeira/restauração e commit/push apenas para um remoto bare local. O preparador foi verificado em árvore isolada, sem percorrer links/mounts e com recusa de hard links antes de mudar o dono.
- Navegador conectado ao Linux: autenticação HTTP Basic, seleção digitada e confirmada diretamente após navegar para outra pasta, Ctrl+V de PNG sintético, miniatura e prévia com CSS, listas separadas e geração do HTML no disco Linux. Integração JavaScript isolada verifica também resposta atrasada, caminho inexistente, Enter na raiz, limpeza da listagem anterior e ações desabilitadas em pasta somente leitura.
- Site local: 16 testes adicionais verificam listagem recursiva/títulos, edição do HTML completo com backup, conflitos por alteração externa, exclusão individual/em lote com confirmação e pré-validação, lixeira persistente, restauração sem sobrescrita, exclusão/restauração do index, confinamento dos caminhos e prévia com CSS. Clones são feitos somente para remotos bare locais de teste, com identidade e limpeza de falha. A revisão/push de uma página removida é exercitada sem regenerá-la.
- Editor Web local: links code-server/serve-web apontam para a mesma pasta. A inicialização nativa foi simulada com processo/socket substituídos, verificando aceitação explícita de termos, restrição de acesso local, token fora dos argumentos/configuração e escuta em loopback. O VS Code instalado foi consultado somente com `--version`/`serve-web --help`; nenhum servidor VS Code foi iniciado nem licença aceita durante a validação.
- Integração JavaScript adicional em DOM isolado: seleção/filtro sem interpretar títulos HTML, salvar código, preservar edição em conflito, confirmação antes da exclusão, restauração, clone, configurações e link do editor. Atualização da main/revisão de remoções não chamam geração ou gravação do rascunho antigo. A aceitação dos termos só aciona uma API simulada no teste.
- Navegador real em ambiente de teste local: a nova aba listou os HTML, abriu/salvou o código completo com backup, moveu uma página para a lixeira, mostrou essa página como **Removido** na revisão e a restaurou para o caminho original. A lixeira voltou a ficar vazia. Nenhuma publicação foi acionada nesse fluxo e nenhum HTML real do usuário foi excluído.
- Integração Git: 23 testes com repositórios e remotos bare locais. Foram verificados seleção de arquivos, nomes Unicode/espaços, preservação de outros arquivos no stage, remoções, mudanças após a revisão, avanço da main remota, atualização por avanço direto, preservação de edições conflitantes, retry após reinício sem duplicar commits, expiração, destino único, autenticação/origem da API, persistência da pasta e helper de token sem rede.
- Regressão do repositório incorreto: uma configuração salva apontando para outro gerador Git é corrigida para o site do HTML de saída. A raiz usa o index.html do site; a listagem percorre suas subpastas, respeita o escopo em monorepos e pré-seleciona imagens pelos caminhos relativos/absolutos do HTML. Também foram verificados índice em subpasta, saída ausente e bloqueio de saída dentro do próprio gerador.
- Fluxo da nova interface no navegador: gerar HTML, revisar a seleção, alternar checkbox, fazer commit e push de HTML/PNG para um remoto **bare local de teste**, verificando os objetos gravados. O painel de pipeline deste ambiente de QA usou uma resposta simulada identificada como tal.
- Consulta autenticada de leitura ao GitHub Actions de `perdixti/SeaBirdsCloud-site`, usando a autenticação Git existente em memória. Foi encontrada a execução da main com sucesso. **Nenhum commit de teste foi enviado ao GitHub e nenhum deploy novo no S3 foi disparado durante a validação.**
- Exclusão definitiva testada somente em diretórios temporários: exige confirmação, bloqueia imagens fora da lixeira, preserva arquivos externos ou modificados, recusa origens externas e remove o catálogo após reiniciar. O DOM isolado verifica exclusão individual/em lote, cancelamento, limpeza da seleção ao filtrar e sincronização sem reapresentar itens excluídos.
- Novas regressões de imagem: mover preservando arquivos existentes, lixeira/restauração após reiniciar, recuperação com colisão de nomes, proteção de arquivos modificados externamente, caminhos distintos entre pastas, importação de imagens antigas e bloqueio de saída da pasta selecionada.
- **23 verificações de integração JavaScript em DOM isolado com API simulada**: remoção individual, Ctrl+Z, edição manual, colagem dupla, movimentação com atualização do Markdown, exclusão em lote, restauração, importação de pasta, configurações, modos de visualização e geração. Não dependem de arquivos reais do usuário.
- Inspeção visual do novo layout em 1280 × 720 com duas miniaturas e prévia renderizada. No navegador, foram acionados o ×, desfazer, envio à lixeira e restauração, usando somente imagens de teste. A imagem removida saiu do Markdown e da galeria; a restauração devolveu o arquivo e a referência. As verificações de navegador restantes abaixo foram feitas antes desta revisão visual.
- Geração efetiva de um HTML com nome e local escolhidos, sem substituir cabeçalho, rodapé, CSS e scripts do template.
- Download direto de `.html`, comprovando que o conteúdo não é um ZIP.
- Ctrl+V real no Chrome usando uma imagem na área de transferência, verificando o PNG na pasta especificada, Markdown relativo e incremento do índice.
- Prévia carregando CSS, JavaScript e imagem nos caminhos `../../...` de uma estrutura de site. O botão copiar foi acionado usando a função do JavaScript do template de teste.
- Construtor de tabela, inserção/remoção de linha, busca no editor, configuração/retorno do histórico e persistência dos caminhos ao recarregar.
- Substituição real apenas nos arquivos marcados em uma pasta, mantendo os não selecionados e guardando cópias anteriores.
- Testes de formatação preservando `<pre>` e espaçamento inline, proteção contra arquivos alterados após a busca e seleção de caminhos fora da lista de resultados.
- Testes das extensões Python-Markdown Extra, HTML bruto, imagens com caminho web separado e `copiarCodigo(this)`.
- Migração de banco da primeira versão web sem perder rascunhos.
- Visualização do HTML salvo sem regenerar o arquivo.
- Seleção de arquivos/pastas do servidor e criação de uma pasta pelo endpoint correspondente.
- Verificação de sintaxe/estilo Python e JavaScript, sintaxe Bash/PowerShell, empacotamento dos recursos web e configuração Compose.

A interface foi inspecionada em tela de desktop e em 390 px de largura. A gravação de arquivos foi verificada por leitura dos caminhos reais no disco, além das mensagens da interface.

O TestClient da Starlette emite um aviso de depreciação sobre `httpx`; isso não impede os testes nem afeta o servidor em execução.

## Limites da validação anterior

Revisão de instalação LXC r1: uma captura do usuário mostrou `useradd: command not found` após instalar os pacotes. O instalador agora define um PATH administrativo, instala explicitamente `passwd` e verifica a disponibilidade de `useradd` antes de criar a conta do serviço. A sintaxe Bash e o conteúdo do ZIP foram conferidos; não foi executado um provisionamento completo de LXC pelo agente.

O Linux foi validado em Ubuntu 24.04/WSL com systemd e Python 3.12/3.13. Não houve acesso remoto ao LXC do usuário. O Docker Engine local estava desligado; o build/execução Docker, o provisionamento completo do Debian 13 no Proxmox e o serviço opcional code-server não foram executados neste ambiente. A matriz CI foi atualizada e não foi disparada no GitHub durante esta entrega.

O diálogo nativo Windows usa Tkinter e possui alternativa por seletor do servidor. O teste de ponta a ponta utilizou caminhos informados no formulário; não automatizou a janela nativa do sistema operacional. Atalhos reservados pelo navegador continuam dependendo dele.

A prévia isola scripts e bloqueia conexões/formulários; a saída HTML preserva os scripts do template para execução no site. Não foram exercitadas as integrações externas de chatbot do template original nem todos os recursos de todos os sites do usuário.

O código anterior e o template personalizado foram mantidos, sem commit ou push. Nenhuma substituição em lote foi executada nos arquivos reais do usuário: esses testes usaram somente pastas criadas para validação.
