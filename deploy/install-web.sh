#!/usr/bin/env bash
# Acesso HTTP no mesmo endereco do gerador, sem tunel na maquina do usuario.
# Uso no servidor: bash deploy/install-web.sh [porta-publica [porta-interna]]
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 077
fail() { printf '%s\n' "$*" >&2; exit 1; }
render_config() {
    cat <<EOF
{
    admin off
}
http://:$public_port {
    redir /editor /editor/ 308
    handle_path /editor/* {
        reverse_proxy 127.0.0.1:8765
    }
    handle {
        reverse_proxy 127.0.0.1:$app_port
    }
}
EOF
}
if [[ "${1:-}" == --help ]]; then
    printf 'Uso: bash deploy/install-web.sh [porta-publica [porta-interna]]\nPadrao: 8000 e 8001. Executar como root no servidor.\n'
    exit 0
fi
print_only=0
if [[ "${1:-}" == --print-config ]]; then print_only=1; shift; fi
[[ $# -le 2 ]] || fail 'Informe apenas a porta publica e, opcionalmente, a porta interna.'
public_port=${1:-8000}
app_port=${2:-8001}
for port in "$public_port" "$app_port"; do
    [[ "$port" =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || fail 'Porta invalida.'
done
[[ "$public_port" != "$app_port" && "$public_port" != 8765 && "$app_port" != 8765 ]] || fail 'As tres portas precisam ser diferentes (editor interno: 8765).'
if (( print_only )); then render_config; exit 0; fi

[[ $EUID -eq 0 ]] || fail 'Execute como root no servidor Linux.'
source /etc/os-release
[[ "$ID" == debian || "$ID" == ubuntu ]] || fail 'Requer Debian ou Ubuntu.'
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ -f "$source_dir/install-editor.sh" && -f "$source_dir/seabirds-web.service" ]] || fail 'Mantenha os arquivos da pasta deploy juntos.'
grep -q SEABIRDS_EDITOR_URL /opt/seabirds/app/seabirds/config.py 2>/dev/null || fail 'Atualize primeiro o codigo do gerador para 2.6.0 ou posterior.'
systemctl is-active --quiet seabirds || fail 'O servico seabirds precisa estar ativo antes de configurar o acesso web.'
grep -Eq '^SEABIRDS_PASSWORD=.+$' /etc/seabirds/seabirds.env || fail 'Defina SEABIRDS_PASSWORD em /etc/seabirds/seabirds.env primeiro.'
web_was_active=0
if systemctl is-active --quiet seabirds-web; then web_was_active=1; fi
if (( ! web_was_active )) && command -v ss >/dev/null && ss -H -ltn "sport = :$app_port" | grep -q .; then
    fail 'A porta interna ja esta ocupada. Escolha outra como segundo argumento.'
fi

# Instalar/iniciar o editor nao altera a pasta do site nem as credenciais do Git.
bash "$source_dir/install-editor.sh"
if [[ ! -x /usr/bin/caddy ]]; then
    apt-get update
    apt-get install -y caddy
    # Remove apenas o site de boas-vindas iniciado pelo pacote que acabamos de instalar.
    systemctl disable --now caddy
fi
[[ -x /usr/bin/caddy ]] || fail 'O pacote caddy nao forneceu /usr/bin/caddy.'

task_dir=$(mktemp -d /tmp/seabirds-web.XXXXXXXX)
managed_files=(
    /etc/seabirds/web.Caddyfile
    /etc/seabirds/web.env
    /etc/systemd/system/seabirds.service.d/60-web.conf
    /etc/systemd/system/seabirds-web.service
)
made_changes=0
cleanup() {
    result=$?
    trap - EXIT
    if (( result != 0 && made_changes )); then
        printf 'Falha na configuracao web; restaurando a configuracao anterior do gerador.\n' >&2
        systemctl stop seabirds-web >/dev/null 2>&1 || true
        for i in "${!managed_files[@]}"; do
            if [[ -f "$task_dir/$i.before" ]]; then
                cp -p -- "$task_dir/$i.before" "${managed_files[$i]}"
            else
                rm -f -- "${managed_files[$i]}"
            fi
        done
        systemctl daemon-reload
        systemctl restart seabirds || true
        if (( web_was_active )); then systemctl start seabirds-web || true; fi
    fi
    rm -f -- "$task_dir"/*
    rmdir -- "$task_dir"
    exit "$result"
}
trap cleanup EXIT
for i in "${!managed_files[@]}"; do
    [[ ! -e "${managed_files[$i]}" ]] || cp -p -- "${managed_files[$i]}" "$task_dir/$i.before"
done
render_config > "$task_dir/Caddyfile"
/usr/bin/caddy validate --config "$task_dir/Caddyfile" --adapter caddyfile
backup_dir="/etc/seabirds/web-backups/$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$backup_dir"
for i in "${!managed_files[@]}"; do
    [[ ! -f "$task_dir/$i.before" ]] || cp -p -- "$task_dir/$i.before" "$backup_dir/$i.before"
done
printf '%s\n' "${managed_files[@]}" > "$backup_dir/arquivos.txt"

made_changes=1
install -m 644 "$task_dir/Caddyfile" /etc/seabirds/web.Caddyfile
install -m 600 /dev/stdin /etc/seabirds/web.env <<EOF
SEABIRDS_HOST=127.0.0.1
SEABIRDS_PORT=$app_port
SEABIRDS_EDITOR_URL=/editor/
EOF
install -d -m 755 /etc/systemd/system/seabirds.service.d
install -m 644 /dev/stdin /etc/systemd/system/seabirds.service.d/60-web.conf <<'EOF'
[Service]
EnvironmentFile=/etc/seabirds/web.env
EOF
install -m 644 "$source_dir/seabirds-web.service" /etc/systemd/system/seabirds-web.service
systemctl daemon-reload
systemctl restart seabirds
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 \
    --retry-max-time 30 --max-time 3 --output /dev/null "http://127.0.0.1:$app_port/healthz"
systemctl restart seabirds-web
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 \
    --retry-max-time 30 --max-time 3 --output /dev/null "http://127.0.0.1:$public_port/editor/login"
[[ $(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:$public_port/") == 401 ]] || fail 'O gerador nao respondeu com a autenticacao esperada.'
for service_name in seabirds seabirds-editor seabirds-web; do
    systemctl is-active --quiet "$service_name"
done
systemctl enable seabirds-web
made_changes=0
printf '\nPronto: abra http://ENDERECO-DO-SERVIDOR:%s/ e use Editor do site.\n' "$public_port"
printf 'O editor fica em /editor/ e usa a senha de /etc/seabirds/code-server.yaml.\n'
printf 'O gerador mantem o usuario/senha atuais e abre a pasta do site selecionada.\n'
printf 'Configuracoes anteriores: %s\n' "$backup_dir"
