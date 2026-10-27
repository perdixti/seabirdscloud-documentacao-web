# Validação — fluxo de geração HTML

Data: 27/10/2026. A revisão foi orientada pela correção do usuário: preservar o gerador de HTML e as operações em arquivos da aplicação original.

## Executado

- Suíte Python no Windows/Python 3.12.14: **102 testes**, incluindo o fluxo de arquivos, a separação de listas, detecção automática dos recursos CSS na prévia, gerenciamento de imagens, publicação GitHub e gestão do site local.
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

## Limites da validação

O Docker Engine local estava desligado e não havia acesso ao Proxmox/LXC. O Dockerfile, Compose, instalador Debian 13 e serviços systemd estão preparados, mas **a execução real no container/LXC não foi validada aqui**, incluindo o serviço opcional code-server. A matriz CI foi configurada e não foi executada no GitHub durante esta entrega.

O diálogo nativo Windows usa Tkinter e possui alternativa por seletor do servidor. O teste de ponta a ponta utilizou caminhos informados no formulário; não automatizou a janela nativa do sistema operacional. Atalhos reservados pelo navegador continuam dependendo dele.

A prévia isola scripts e bloqueia conexões/formulários; a saída HTML preserva os scripts do template para execução no site. Não foram exercitadas as integrações externas de chatbot do template original nem todos os recursos de todos os sites do usuário.

O código anterior e o template personalizado foram mantidos, sem commit ou push. Nenhuma substituição em lote foi executada nos arquivos reais do usuário: esses testes usaram somente pastas criadas para validação.
