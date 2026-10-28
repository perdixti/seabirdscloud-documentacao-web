# Editor no navegador — EC2 e LXC

O editor executa no servidor e acessa a mesma pasta do site usada pelo gerador. Depois da instalação, basta acessar o endereço do gerador e clicar em **Site e repositórios → Editor do site**. Não é necessário instalar VS Code, manter MobaXterm aberto ou criar um túnel no computador de quem está usando.

No ambiente atual:

- Gerador: `http://ec2-54-21-21-119.sa-east-1.compute.amazonaws.com:8000/`
- Editor: `http://ec2-54-21-21-119.sa-east-1.compute.amazonaws.com:8000/editor/`
- Pasta a selecionar na aplicação: `/srv/seabirds/SeaBirdsCloud-site`.

O botão acrescenta a pasta selecionada ao endereço do editor. Salvar grava os arquivos do servidor. Para enviar as mudanças ao GitHub e ao S3, volte ao gerador, atualize as páginas e revise a publicação como antes.

## Instalar ou atualizar uma vez no servidor

O arquivo ZIP contém a pasta `SeaBirdsCloud`. Extraia a versão 2.6.0 em uma pasta nova no servidor. Os passos abaixo são executados como root no console do próprio servidor; não é necessário manter nenhuma conexão aberta depois.

Se o gerador ainda não estiver instalado, no Debian 13 execute primeiro `bash deploy/install-debian.sh` na pasta extraída.

Se já estiver instalado em `/opt/seabirds/app`, entre na pasta `SeaBirdsCloud` extraída e atualize somente o código:

```bash
backup_dir=$(mktemp -d /root/seabirds-code-2.6.0.XXXXXXXX)
cp -a /opt/seabirds/app/. "$backup_dir/"
systemctl stop seabirds
cp -a seabirds/. /opt/seabirds/app/seabirds/
systemctl start seabirds
```

Os dados, o clone do site e as configurações ficam fora dessa pasta. As dependências Python desta versão são as mesmas da 2.5.0.

Ainda na pasta extraída, habilite o acesso pelo navegador:

```bash
bash deploy/install-web.sh
```

O instalador requer Debian/Ubuntu com systemd e a conta `seabirds` do gerador. Ele instala o code-server e o Caddy, gera a senha do editor, cria os serviços e configura o botão automaticamente. A configuração antiga de editor salva pelo usuário é preservada e substituída enquanto a conexão gerenciada estiver ativa.

O gerador e o editor terão suas próprias senhas. Para consultar a senha gerada do editor, abra `/etc/seabirds/code-server.yaml` no console do servidor e veja o campo `password`. A senha do gerador continua em `/etc/seabirds/seabirds.env`.

Verifique os três serviços:

```bash
systemctl status seabirds seabirds-editor seabirds-web --no-pager
```

O gerador passa a escutar internamente em `127.0.0.1:8001`. O editor escuta em `127.0.0.1:8765`. O serviço `seabirds-web` atende externamente na mesma porta `8000`, encaminha `/editor/` ao editor e as demais páginas ao gerador, incluindo WebSockets. A configuração do Git não é alterada.

O instalador usa um serviço Caddy próprio e não modifica o Caddyfile de outros sites. Se acabou de instalar o pacote Caddy, desativa apenas o serviço padrão de boas-vindas criado pelo pacote. As configurações anteriores do acesso web ficam em `/etc/seabirds/web-backups/`. Se a ativação falhar, restaura as configurações anteriores do gerador/proxy; o code-server instalado pode permanecer disponível internamente.

Para outras portas, use `bash deploy/install-web.sh PORTA_PUBLICA PORTA_INTERNA`. Por exemplo, `bash deploy/install-web.sh 80 8001` no LXC. Evite usar a porta interna de outro programa. A porta pública deve estar permitida no firewall do servidor; a porta 8000 já usada na EC2 continua sendo a única necessária para este acesso.

## Usar

1. Abra o endereço HTTP do gerador no navegador e autentique-se.
2. Selecione `/srv/seabirds/SeaBirdsCloud-site` em **Site e repositórios**.
3. Clique em **Editor do site → Abrir editor do site** e entre com a senha do editor.
4. Edite HTML, CSS, JavaScript e imagens na mesma pasta do servidor. Salve com Ctrl+S.
5. Volte ao gerador, clique em **Atualizar páginas**, revise e publique os arquivos desejados.

Se o clone estiver fora de `/srv/seabirds`, prepare o acesso com `seabirds-configure-site /caminho/do/site`, que ajusta o usuário e a liberação da pasta nos serviços do gerador e editor. O proxy não precisa acessar os arquivos diretamente.

## HTTP de desenvolvimento e migração

Esta configuração usa HTTP conforme solicitado para desenvolvimento. As senhas não têm criptografia de transporte em HTTP. Alguns recursos de extensões que usam webviews exigem HTTPS, conforme a [documentação do code-server](https://coder.com/docs/code-server/FAQ#why-do-web-views-not-work). A edição e gravação dos arquivos usam os serviços do servidor; não habilite exceções de segurança no navegador para contornar recursos que exigem HTTPS.

No LXC da rede interna, instale o gerador e execute o mesmo `deploy/install-web.sh`. O link `/editor/` usa o endereço aberto no navegador, sem fixar o DNS da EC2. Transfira o clone, as configurações e os dados que deseja manter para os mesmos caminhos no LXC. Não transfira a venv do Windows nem a da EC2 para outra instalação de Python.

Para ativar HTTPS no futuro, um proxy HTTPS pode encaminhar o endereço completo ao `seabirds-web`, preservando `/editor/` e WebSockets. A URL relativa continuará funcionando. Consulte o [guia oficial de proxy do code-server](https://coder.com/docs/code-server/guide).

## Diagnóstico

```bash
journalctl -u seabirds-web -u seabirds-editor -u seabirds -n 60 --no-pager
curl --fail http://127.0.0.1:8000/healthz
curl --fail http://127.0.0.1:8000/editor/login -o /dev/null
```

Depois de instalar, a conexão gerenciada deve mostrar `/editor/` em **Configurar editor**. Se ainda aparece `127.0.0.1`, confirme a atualização do código e reinicie `seabirds`. Não informe `127.0.0.1` na URL pública do editor.
