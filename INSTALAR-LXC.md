# Instalar SeaBirdsCloud 2.4.0 no LXC Debian 13

Execute os comandos dentro de um LXC Debian 13 não privilegiado, como root. O instalador usa Python e systemd diretamente; Docker não é necessário. Reserve inicialmente 1–2 vCPU, 1 GB de RAM e disco suficiente para o repositório e suas imagens. Esse dimensionamento é uma sugestão inicial, sem medição no seu Proxmox.

## 1. Copiar e instalar

Copie `SeaBirdsCloud-LXC-Debian13-2.4.0.zip` para `/root` do LXC. Em um terminal Windows com acesso SSH ao container, uma opção é:

```powershell
scp SeaBirdsCloud-LXC-Debian13-2.4.0.zip root@IP-DO-LXC:/root/
```

No terminal do LXC:

```bash
apt-get update
apt-get install -y unzip
cd /root
unzip SeaBirdsCloud-LXC-Debian13-2.4.0.zip
cd SeaBirdsCloud
sha256sum -c MANIFEST.sha256
bash deploy/install-debian.sh
systemctl status seabirds --no-pager
curl -fsS http://127.0.0.1:8000/healthz
```

O último comando pode ser executado depois de instalar `curl` com `apt-get install -y curl`, caso ainda não esteja disponível. O instalador precisa de acesso à Internet aos repositórios Debian e ao PyPI para instalar as dependências.

## 2. Acessar

Abra `http://IP-DO-LXC:8000` no navegador. Usuário: **admin**. A senha aleatória é criada durante a instalação; consulte-a no próprio LXC:

```bash
cat /etc/seabirds/seabirds.env
```

O arquivo contém a configuração privada do serviço. A aplicação usa autenticação HTTP Basic; para acesso pela Internet, configure HTTPS no proxy reverso. Há um exemplo em `deploy/Caddyfile.example`.

## 3. Preparar o site local

Na aba **Site e repositórios**, clique em **Clonar repositório**. Para seu site, informe:

```text
URL:     https://github.com/perdixti/SeaBirdsCloud-site.git
Destino: /srv/seabirds/SeaBirdsCloud-site
```

O destino deve ser uma pasta nova. Configure antes a autenticação Git no LXC, como o usuário `seabirds`, usando SSH ou `SEABIRDS_GITHUB_TOKEN` em `/etc/seabirds/seabirds.env`. Reinicie o serviço após alterar esse arquivo. A autenticação do Windows não é transferida para o LXC. O README detalha as opções e permissões do token; não coloque a credencial na URL do clone.

Os caminhos usados no formulário pertencem ao LXC. Exemplo:

```text
Raiz do site:         /srv/seabirds/SeaBirdsCloud-site
HTML de saída:        /srv/seabirds/SeaBirdsCloud-site/projetos/outros/teste.html
Pasta de imagens:     /srv/seabirds/SeaBirdsCloud-site/imagens/projetos/outros/teste
Imagens no HTML:      ../../imagens/projetos/outros/teste
```

Edite e salve os arquivos locais; depois use **Publicar alterações do site**, revise a seleção e confirme o commit/push. A pipeline já existente do repositório publica os HTML e imagens no S3.

## 4. VS Code Web opcional

No LXC, conecte um **code-server** com acesso à mesma pasta do clone. O README contém o procedimento; `deploy/seabirds-editor.service` e `deploy/code-server.yaml.example` são os exemplos de configuração. O instalador principal não instala nem inicia o editor opcional. O iniciador do VS Code instalado no Windows é específico daquela máquina.

## Dados, manutenção e backup

| Caminho | Conteúdo |
| --- | --- |
| `/opt/seabirds/app` | Código da aplicação |
| `/opt/seabirds/venv` | Ambiente Python criado no Debian |
| `/var/lib/seabirds` | Banco, rascunhos, históricos, cópias e lixeiras |
| `/srv/seabirds` | Clones do site, HTML, templates e imagens |
| `/etc/seabirds/seabirds.env` | Configuração e credenciais do serviço |

```bash
systemctl restart seabirds
journalctl -u seabirds -n 80 --no-pager
```

Guarde backup de `/var/lib/seabirds`, `/srv/seabirds` e `/etc/seabirds` antes de atualizar. Para uma cópia consistente do banco por cópia de arquivos, pare o serviço durante o backup. O instalador preserva dados e configuração existentes.

O pacote contém código, templates, testes e instruções. Os rascunhos, o repositório do site, as imagens locais, senhas, tokens e o ambiente Python do Windows não estão incluídos. Esta é uma instalação nova no LXC; uma migração dos dados atuais é uma operação separada.

O ZIP e a sintaxe dos scripts foram verificados no Windows. A instalação real no seu LXC/Proxmox ainda precisa ser executada e conferida nesse destino.
