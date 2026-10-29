# Linux e LXC — versão 3.0.1

A aplicação usa a mesma interface, gerador, template e catálogo de imagens no Windows e no Linux. Os caminhos pertencem à máquina do servidor. No LXC, um caminho como `/opt/Meu site` deve existir e estar acessível ao usuário `seabirds`.

## Atualizar o LXC existente

Copie `SeaBirdsCloud-LXC-Debian13-3.0.1.zip` para `/root` do LXC. Como root, dentro do container:

```bash
apt-get update
apt-get install -y unzip
mkdir -p /root/seabirds-update-3.0.1
unzip SeaBirdsCloud-LXC-Debian13-3.0.1.zip -d /root/seabirds-update-3.0.1
cd /root/seabirds-update-3.0.1/SeaBirdsCloud
sha256sum -c MANIFEST.sha256
bash deploy/update-app.sh
```

O instalador preserva `/var/lib/seabirds` (banco, rascunhos, históricos e lixeiras), `/srv/seabirds` (sites) e a configuração já existente em `/etc/seabirds/seabirds.env`. Faça backup desses caminhos antes da atualização. As credenciais antigas continuam funcionando. Na versão 3.0.1, autor e token também podem ser gerenciados em **Configurar GitHub**, sem reiniciar o serviço; veja [GitHub Web](GITHUB-WEB.md).

## Usar um clone existente em /opt

Salve as edições abertas antes desta etapa, pois os serviços ativos serão reiniciados. Execute como root, substituindo o exemplo pela **pasta do seu site que contém o index.html**:

```bash
seabirds-configure-site '/opt/Meu site'
```

Para apenas conferir o plano:

```bash
seabirds-configure-site '/opt/Meu site' --check
```

Esse preparador atribui a pasta e seus arquivos ao usuário/grupo `seabirds`, garante leitura e escrita ao proprietário e libera apenas esse caminho em um complemento do serviço systemd. Ele inclui os metadados `.git` do clone, permitindo que o mesmo usuário faça commit/push. Se uma pasta pai bloquear a passagem, adiciona somente permissão de travessia para `seabirds` por ACL. Links simbólicos e outros sistemas de arquivos dentro da pasta não são percorridos. Arquivos com hard links exigem preparação manual; o programa os detecta antes de alterar a árvore.

O preparador também configura `seabirds-editor.service`, se esse serviço opcional já estiver instalado. Se instalar o editor depois, execute novamente o preparador para esse site. Os complementos são separados por caminho; você pode preparar mais de um clone.

Na aplicação, abra **Site e repositórios**, digite o caminho absoluto e pressione Enter ou **Atualizar páginas**. Ao usar **Selecionar**, você pode digitar o caminho completo no seletor e confirmar diretamente. O caminho digitado é validado antes da seleção. Pastas inexistentes geram um erro no próprio seletor; entradas sem acesso são sinalizadas sem impedir a leitura dos demais arquivos.

## Permissões e localização

A aba do site mostra o usuário do servidor e avisa quando a pasta está somente para leitura. Nesse estado, a visualização continua disponível. Edição e publicação ficam disponíveis depois que a pasta é preparada e a listagem é atualizada.

O serviço usa `ProtectSystem=strict`: a permissão Unix e a liberação do caminho no systemd são necessárias para gravar em `/opt`. O preparador configura ambas. A documentação de referência está em [systemd.exec — ReadWritePaths](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#ReadWritePaths=).

Prefira `/srv/seabirds/NOME-DO-SITE` para novos clones pela interface, pois essa pasta já é gravável pelo serviço. Sites existentes em `/opt` podem continuar lá após o preparo. `/root`, `/home` e as pastas do próprio programa/banco são protegidos no serviço e não são aceitos pelo preparador. A execução local com `start.sh`, sob seu usuário Linux, segue as permissões normais desse usuário.

Caminhos com espaços, acentos e aspas externas são aceitos, assim como URLs locais `file:///...`. Caminhos Windows como `C:/...` precisam ser substituídos por caminhos do servidor Linux ou de uma pasta montada. O sistema de arquivos Linux diferencia maiúsculas de minúsculas.

## Git, imagens e editor Web

Para usar HTTPS, configure `SEABIRDS_GITHUB_TOKEN` no arquivo do serviço e reinicie `seabirds`. Para usar SSH, configure as chaves para o usuário `seabirds`, cujo HOME é `/var/lib/seabirds`. Autenticar apenas o usuário root no console não autentica automaticamente o serviço. Os detalhes estão no README.

Ctrl+V envia a imagem ao servidor e grava no diretório físico configurado. A referência no HTML pode continuar relativa, como `../../imagens/tutorial`. A prévia e o botão Visualizar usam HTTP no acesso ao servidor Linux, carregando os recursos do site; o HTML gerado preserva o template e seus scripts.

O code-server acessa o mesmo clone. Execute `bash deploy/install-web.sh` na pasta extraída para disponibilizar o editor em `/editor/` no endereço do gerador, sem túnel na máquina do usuário. Consulte [Editor Web](EDITOR-WEB.md) para atualização e detalhes dos serviços.

## Exclusão completa (2.9.0)

A lixeira agora oferece **Excluir definitivamente** para remover o HTML, os cards correspondentes e as imagens exclusivas, com revisão e confirmação. Consulte [Exclusão completa](LIXEIRA-PAGINAS.md). A suíte de 170 casos passou no Linux/Python 3.12 (169 aprovados e 1 ignorado) e Windows/Python 3.12 (162 aprovados e 8 ignorados).

## Validação do catálogo (2.8.0)

A suíte de 154 casos passou em Linux/Python 3.12 e 3.13 (153 aprovados e 1 ignorado) e Windows/Python 3.12 (147 aprovados e 7 ignorados). Foram verificados cadastro/edição/mudança de categoria, conflito de versão, desfazer após reiniciar, URLs e limites de pasta, preservação de comentários e publicação conjunta de HTML/capa/catálogo em remoto bare local. O navegador usou uma cópia do catálogo real de 21 categorias e 179 projetos, sem alterar o arquivo original do site.

Consulte [Catálogo](CATALOGO.md) e [Validação](VALIDACAO.md).

## Validação do gerenciamento GitHub (2.7.0)

Passaram 134 testes no Linux (1 ignorado) e 128 no Windows (7 ignorados). Foram verificados segredo criptografado, permissões privadas, ausência do token em respostas/erros, troca/remoção, persistência, uso imediato no clone e publicação, e configuração do autor na mesma revisão. O formulário foi exercitado no navegador contra Linux com dados sintéticos.

## Validação anterior do editor Web (2.6.0)

A suíte de 123 casos passou no Linux (122 aprovados, 1 ignorado) e no Windows (116 aprovados, 7 ignorados). O code-server e o proxy foram exercitados de fato pelo navegador em HTTP, com edição e gravação em disco. As três unidades também responderam sob as restrições systemd do instalador em uma árvore temporária. Veja [validação detalhada](VALIDACAO.md) e [Editor Web](EDITOR-WEB.md).

## Validação anterior (2.5.0)

Foram executados testes reais em Linux sob usuário comum e em serviços systemd transitórios com as restrições do instalador, usando clones e remotos bare locais de teste. Os três cenários foram: clone pertencente ao root, clone com dono corrigido ainda bloqueado pelo serviço e clone preparado com escrita autorizada. Foram exercitados HTML, CSS, upload de duas imagens, edição com backup, exclusão/restauração e commit/push local.

A interface foi aberta no navegador contra um servidor Linux com autenticação HTTP Basic. Foram confirmados a seleção direta do caminho absoluto, Ctrl+V de uma imagem sintética, a miniatura, a prévia com CSS e a gravação do HTML no disco Linux.

A suíte passou em Linux com Python 3.12 e 3.13, além da regressão Windows. O ambiente Linux utilizado foi Ubuntu 24.04 em WSL com systemd; o LXC Debian 13 do usuário não foi acessado remotamente. Docker e a instalação completa dentro do Proxmox não foram executados nesta validação.
