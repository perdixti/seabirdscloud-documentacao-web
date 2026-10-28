#!/usr/bin/env bash
# Executar dentro do LXC, nunca no host Proxmox: bash deploy/install-debian.sh
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    printf 'Execute como root dentro do LXC Debian 13.\n' >&2
    exit 1
fi
source /etc/os-release
if [[ "$ID" != debian || "$VERSION_ID" != 13 ]]; then
    printf 'Este instalador foi preparado para Debian 13.\n' >&2
    exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$source_dir" == /opt/seabirds/app ]]; then
    printf 'Execute o instalador a partir de uma cópia fora de /opt/seabirds/app.\n' >&2
    exit 1
fi
apt-get update
apt-get install -y python3 python3-venv ca-certificates git openssh-client
if ! id seabirds >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/seabirds --shell /usr/sbin/nologin seabirds
fi
install -d -m 755 /opt/seabirds/app /etc/seabirds
install -d -o seabirds -g seabirds -m 700 /var/lib/seabirds
install -d -o seabirds -g seabirds -m 750 /srv/seabirds
cp -a -- "$source_dir/seabirds" /opt/seabirds/app/
install -m 644 "$source_dir/requirements.lock" /opt/seabirds/app/requirements.lock
python3 -m venv /opt/seabirds/venv
/opt/seabirds/venv/bin/python -m pip install -r /opt/seabirds/app/requirements.lock
if [[ ! -f /etc/seabirds/seabirds.env ]]; then
    password="$(/opt/seabirds/venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))')"
    umask 077
    read -sp "Digite o seu token: " token
    printf 'SEABIRDS_DATA_DIR=/var/lib/seabirds\nSEABIRDS_HOST=0.0.0.0\nSEABIRDS_PORT=80\nSEABIRDS_USERNAME=admin\nSEABIRDS_PASSWORD=%s\nSEABIRDS_HISTORY_LIMIT=50\nSEABIRDS_GITHUB_TOKEN=' "$password" "$token" > /etc/seabirds/seabirds.env
fi
install -m 644 "$source_dir/deploy/seabirds.service" /etc/systemd/system/seabirds.service
systemctl daemon-reload
systemctl enable seabirds
systemctl restart seabirds
printf 'Instalado. Acesse http://IP-DO-LXC:80 com usuário admin.\n'
printf 'Consulte a senha em /etc/seabirds/seabirds.env e os logs com journalctl -u seabirds.\n'
printf 'Use /srv/seabirds para os arquivos HTML, templates e imagens, ou autorize outro diretório no serviço.\n'
