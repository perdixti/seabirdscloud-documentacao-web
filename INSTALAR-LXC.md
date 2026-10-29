# Instalar SeaBirdsCloud 3.0.0 no LXC Debian 13

Para atualizar uma instalação existente ou preparar um clone em `/opt`, veja primeiro [Linux e LXC](docs/LINUX.md).

Execute os comandos dentro de um LXC Debian 13 não privilegiado, como root. O instalador usa Python e systemd diretamente; Docker não é necessário. Reserve inicialmente 1–2 vCPU, 1 GB de RAM e disco suficiente para o repositório e suas imagens. Esse dimensionamento é uma sugestão inicial, sem medição no seu Proxmox.

## 1. Copiar e instalar

Copie `SeaBirdsCloud-LXC-Debian13-3.0.0.zip` para `/root` do LXC. Em um terminal Windows com acesso SSH ao container, uma opção é:

```powershell
scp SeaBirdsCloud-LXC-Debian13-3.0.0.zip root@IP-DO-LXC:/root/
```

No terminal do LXC:

```bash
apt-get update
apt-get install -y unzip
cd /root
unzip SeaBirdsCloud-LXC-Debian13-3.0.0.zip
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

O destino deve ser uma pasta nova. Configure nome, e-mail e token em **Site e repositórios → Configurar GitHub** antes do clone. A aplicação já usa as credenciais salvas nas próximas operações, sem reiniciar. SSH e `SEABIRDS_GITHUB_TOKEN` continuam disponíveis como alternativas. A autenticação do Windows não é transferida para o LXC. O README detalha as opções e permissões do token; não coloque a credencial na URL do clone.

Os caminhos usados no formulário pertencem ao LXC. Exemplo:

```text
Raiz do site:         /srv/seabirds/SeaBirdsCloud-site
HTML de saída:        /srv/seabirds/SeaBirdsCloud-site/projetos/outros/teste.html
Pasta de imagens:     /srv/seabirds/SeaBirdsCloud-site/imagens/projetos/outros/teste
Imagens no HTML:      ../../imagens/projetos/outros/teste
```

Edite e salve os arquivos locais; depois use **Publicar alterações do site**, revise a seleção e confirme o commit/push. A pipeline já existente do repositório publica os HTML e imagens no S3.

## 4. VS Code Web opcional

Para disponibilizar o editor no navegador, na mesma pasta extraída execute:

```bash
bash deploy/install-web.sh
```

Abra o gerador normalmente e clique em **Site e repositórios → Editor do site**. O editor estará em `/editor/`, na mesma porta 8000, com senha própria e acesso aos arquivos do site no servidor. O instalador principal sozinho não instala esse complemento. Consulte [Editor Web](docs/EDITOR-WEB.md) para atualização, acesso HTTP na EC2 e migração para a rede interna do Proxmox.

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

### Erro `useradd: command not found`

A revisão r1 normaliza o PATH do instalador, incluindo `/usr/sbin`, e instala explicitamente o pacote `passwd`, que fornece `useradd` no Debian. Se a primeira tentativa foi interrompida nesse ponto, continue na pasta do projeto, como root:

```bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
apt-get install -y passwd
bash deploy/install-debian.sh
```

Esses comandos também permitem repetir a instalação usando o clone anterior. As etapas já concluídas podem ser executadas novamente; o instalador preserva a configuração e os dados existentes.

O ZIP e a sintaxe dos scripts foram verificados no Windows. A captura enviada durante a instalação real no LXC revelou a falta de `useradd` no PATH; a correção cobre o PATH e a dependência ausente. A instalação completa ainda precisa ser conferida nesse destino.
