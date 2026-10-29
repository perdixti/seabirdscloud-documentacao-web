# Novidades da versão 3.0.0

O gerador continua usando seu template, Markdown, imagens coladas e HTML no site. Os recursos abaixo complementam esse fluxo e funcionam no Windows e no Linux.

## Criação guiada

Em **Nova documentação**, informe a raiz do site, título, categoria, descrição, capa e template. O assistente sugere uma saída em `projetos/<categoria>/<titulo>.html` e uma pasta em `imagens/projetos/<categoria>/<titulo>`. Os caminhos podem ser ajustados antes da geração.

Em **Dados da documentação**, mantenha habilitadas as opções de guardar a fonte e atualizar o catálogo para gerar o HTML, a fonte e o card juntos. Falhas na geração ou no catálogo restauram os arquivos anteriores. O gerador não publica no GitHub automaticamente.

## Fonte portátil ao lado do HTML

O arquivo `tutorial.documentacao.json` guarda Markdown, template e opções necessários para reabrir `tutorial.html`. Os caminhos são relativos à raiz do site quando possível. Em **Site e repositórios**, o botão de editar a fonte abre esse conteúdo no gerador. HTML antigos continuam disponíveis para edição direta.

A fonte aparece na revisão de publicação junto do HTML e das imagens. Ela contém o texto e o template do documento; selecione-a somente se quiser disponibilizar esses materiais no repositório e no destino atendido pela sua pipeline. Tokens e chaves da aplicação não são incluídos nessa fonte. Se o HTML tiver sido alterado por outro editor, a geração pede que o conflito seja resolvido antes de sobrescrever.

## Validação do site

**Verificar site** procura arquivos ausentes, diferenças entre maiúsculas e minúsculas nos caminhos, referências de CSS e imagens, links e capas inválidos no catálogo, cards duplicados e documentações sem card. Isso ajuda a localizar caminhos que funcionam no Windows e falham no Linux. A revisão de publicação também apresenta o resultado; erros exigem ciência explícita antes de prosseguir.

A análise é local: não visita links externos nem executa JavaScript. Ela tem limites de arquivos, bytes e referências; quando algum limite é atingido, informa que a análise foi parcial. Recursos carregados dinamicamente precisam de conferência no navegador.

## Lixeira consistente

Ao enviar uma página à lixeira, seu card sai do catálogo e sua fonte é guardada junto da cópia recuperável do HTML. Restaurar devolve esses itens, preservando os demais cards. Colisões com arquivos ou cadastros recriados são informadas antes da restauração.

Na exclusão definitiva, a revisão mostra as imagens exclusivas que podem ser removidas. Imagens compartilhadas ficam preservadas. Depois, revise e publique as remoções pelo GitHub para atualizar o site hospedado. Veja [Lixeira de páginas](LIXEIRA-PAGINAS.md).

## Operações acompanháveis e diagnóstico

Geração, revisão de texto, clone, atualização, publicação, validação e backups usam uma fila com uma operação por vez. O painel **Operações** apresenta etapa, tempo e resultado persistido, inclusive depois de recarregar a página. Ocultar o progresso não cancela a operação. Se o servidor reiniciar durante uma ação, ela é marcada como interrompida; confira o resultado antes de repetir.

O **Diagnóstico** mostra versão, usuário do serviço, permissões, espaço livre, banco, configuração Git e editor. O teste de autenticação Git é uma ação separada e somente de leitura. Um teste local bem-sucedido não confirma regras de rede da EC2 ou acesso externo ao LXC.

## Backups e revisor

O botão **Backups** oferece cópias completas protegidas por senha, agendamento e restauração com revisão de destinos. Consulte [Backups](BACKUPS.md).

O editor oferece revisão local de português, sugestões, correção automática e desfazer. Não precisa de GPU, conta externa ou chave para o modo local. Consulte [Revisor de texto](REVISOR.md).

## Atualizar o servidor

Extraia o pacote 3.0.0 fora de `/opt/seabirds/app`. Dentro da pasta extraída `SeaBirdsCloud`, como root:

```bash
bash deploy/update-app.sh
```

O atualizador instala as dependências e preserva os dados, configurações e sites da instalação existente em `/opt/seabirds`. Para uma instalação nova, consulte [Instalação LXC](../INSTALAR-LXC.md). A atualização local entregue não atualiza sua EC2 ou seu LXC automaticamente.
