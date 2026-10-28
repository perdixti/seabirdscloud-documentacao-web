#!/usr/bin/env bash
# Complemento opcional do SeaBirdsCloud: executar como root na EC2/LXC.
# O editor usa os mesmos arquivos locais; publicar continua sendo uma acao manual.
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 077

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail 'Execute este arquivo como root no servidor Linux.'
source /etc/os-release
[[ "$ID" == debian || "$ID" == ubuntu ]] || fail 'Este complemento requer Debian ou Ubuntu.'
id seabirds >/dev/null 2>&1 || fail 'O usuario seabirds nao existe. Instale o gerador primeiro.'
getent group seabirds >/dev/null || fail 'O grupo seabirds nao existe. Revise a instalacao do gerador.'
[[ -d /srv/seabirds && -d /var/lib/seabirds ]] || fail 'As pastas do gerador nao foram encontradas.'
[[ -d /run/systemd/system ]] || fail 'O servidor precisa estar usando systemd.'

config=/etc/seabirds/code-server.yaml
service=/etc/systemd/system/seabirds-editor.service
if [[ -e "$config" ]]; then
    grep -Eq '^bind-addr: *127\.0\.0\.1:8765 *$' "$config" || fail 'Existe outra configuracao em /etc/seabirds/code-server.yaml. Ela foi preservada; revise o endereco antes de continuar.'
    grep -Eq '^auth: *password *$' "$config" || fail 'A configuracao existente precisa usar auth: password. Ela foi preservada.'
    if grep -q 'TROQUE-POR-' "$config"; then
        fail 'Defina a senha em /etc/seabirds/code-server.yaml antes de continuar.'
    fi
fi

apt-get update
apt-get install -y ca-certificates curl openssl
if [[ ! -x /usr/bin/code-server ]]; then
    installer_file=$(mktemp /tmp/seabirds-code-server.XXXXXXXX.sh)
    trap 'rm -f -- "$installer_file"' EXIT
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 3 \
        https://code-server.dev/install.sh --output "$installer_file"
    sh "$installer_file"
fi
[[ -x /usr/bin/code-server ]] || fail 'O instalador oficial nao criou /usr/bin/code-server. Verifique a instalacao do pacote.'

install -d -m 755 /etc/seabirds
install -d -o seabirds -g seabirds -m 700 /var/lib/seabirds/code-server
if [[ ! -e "$config" ]]; then
    editor_password=$(openssl rand -hex 24)
    install -m 600 -o seabirds -g seabirds /dev/stdin "$config" <<EOF
bind-addr: 127.0.0.1:8765
auth: password
password: $editor_password
cert: false
disable-telemetry: true
EOF
    unset editor_password
fi

if [[ ! -e "$service" ]]; then
    install -m 644 /dev/stdin "$service" <<'EOF'
[Unit]
Description=Editor Web dos arquivos locais SeaBirdsCloud
After=network.target

[Service]
Type=simple
User=seabirds
Group=seabirds
WorkingDirectory=/srv/seabirds
Environment=HOME=/var/lib/seabirds
Environment=SHELL=/bin/bash
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/bin/code-server --config /etc/seabirds/code-server.yaml --user-data-dir /var/lib/seabirds/code-server /srv/seabirds
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/seabirds /srv/seabirds
RestrictSUIDSGID=yes

[Install]
WantedBy=multi-user.target
EOF
fi

install -d -m 755 /etc/systemd/system/seabirds-editor.service.d
install -m 644 /dev/stdin /etc/systemd/system/seabirds-editor.service.d/20-shell.conf <<'EOF'
[Service]
Environment=SHELL=/bin/bash
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EOF
systemctl daemon-reload
systemctl enable seabirds-editor
systemctl restart seabirds-editor
if ! curl --fail --silent --show-error --retry 10 --retry-connrefused \
    --retry-delay 1 --retry-max-time 30 --max-time 3 --output /dev/null \
    http://127.0.0.1:8765/login; then
    fail 'O editor nao respondeu. Consulte: journalctl -u seabirds-editor -n 40 --no-pager'
fi
systemctl is-active --quiet seabirds-editor || fail 'O servico parou. Consulte journalctl -u seabirds-editor.'
printf '\nEditor respondendo em 127.0.0.1:8765 no servidor.\n'
printf 'A senha esta em /etc/seabirds/code-server.yaml; consulte-a apenas no seu console.\n'
printf 'Para acesso pelo navegador no endereco do gerador, execute: bash deploy/install-web.sh\n'
printf 'Confira o servico com: systemctl status seabirds-editor --no-pager\n'
