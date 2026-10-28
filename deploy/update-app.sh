#!/usr/bin/env bash
# Atualiza uma instalacao existente sem substituir dados, segredos ou o site.
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 022
[[ $EUID -eq 0 ]] || { printf 'Execute como root no servidor.\n' >&2; exit 1; }
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ -f "$source_dir/seabirds/app.py" && -f "$source_dir/requirements.lock" ]] || { printf 'Extraia o pacote completo antes de atualizar.\n' >&2; exit 1; }
[[ "$source_dir" != /opt/seabirds/app && -x /opt/seabirds/venv/bin/python && -d /opt/seabirds/app/seabirds ]] || { printf 'Requer instalacao existente em /opt/seabirds. Execute a partir da pasta extraida.\n' >&2; exit 1; }
backup_dir=$(mktemp -d /var/backups/seabirds-code.XXXXXXXX)
chmod 700 "$backup_dir"
cp -a /opt/seabirds/app/. "$backup_dir/"
was_active=0
if systemctl is-active --quiet seabirds; then was_active=1; fi
changed=0
finish() {
    result=$?
    trap - EXIT
    if (( result != 0 )); then
        if (( changed )); then cp -a "$backup_dir/." /opt/seabirds/app/; fi
        if (( was_active )); then systemctl restart seabirds || true; fi
        printf 'Atualizacao interrompida; copia do codigo anterior: %s\n' "$backup_dir" >&2
    fi
    exit "$result"
}
trap finish EXIT
systemctl stop seabirds
/opt/seabirds/venv/bin/python -m pip install -r "$source_dir/requirements.lock"
changed=1
cp -a "$source_dir/seabirds/." /opt/seabirds/app/seabirds/
install -m 644 "$source_dir/requirements.lock" /opt/seabirds/app/requirements.lock
(cd /opt/seabirds/app && /opt/seabirds/venv/bin/python -c 'from seabirds.app import create_app; from seabirds import __version__; print("Codigo atualizado:", __version__)')
systemctl start seabirds
for attempt in {1..10}; do
    if systemctl is-active --quiet seabirds; then
        sleep 1
        systemctl is-active --quiet seabirds && break
    fi
    sleep 1
done
systemctl is-active --quiet seabirds
printf 'Atualizado. Os dados em /var/lib/seabirds, as configuracoes e o site foram preservados.\n'
printf 'Codigo anterior: %s\n' "$backup_dir"
