#!/usr/bin/python3
"""Libera um clone/site específico para os serviços SeaBirdsCloud no Linux."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def validate_site(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or any(ord(char) < 32 for char in value):
        raise ValueError("Informe o caminho absoluto da pasta do site.")
    root = path.resolve(strict=True)
    blocked = {"/", "/opt", "/srv", "/mnt", "/media", "/usr", "/var", "/tmp", "/var/tmp"}
    if str(root) in blocked or any(
        root == Path(base) or root.is_relative_to(base)
        for base in (
            "/etc",
            "/usr",
            "/boot",
            "/dev",
            "/proc",
            "/sys",
            "/root",
            "/home",
            "/opt/seabirds/app",
            "/opt/seabirds/venv",
            "/var/lib/seabirds",
        )
    ):
        raise ValueError(
            "Selecione somente a pasta do site, por exemplo /opt/meu-site ou /srv/seabirds/site."
        )
    if not root.is_dir() or not (root / "index.html").is_file():
        raise ValueError("A pasta selecionada precisa conter o index.html do site.")
    if (root / ".git").is_file():
        raise ValueError(
            "Para um worktree com .git externo, prepare o repositório e suas permissões manualmente."
        )
    return root


def managed_paths(root):
    device = root.stat().st_dev
    yield root
    for parent, directories, names in os.walk(root, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if not (Path(parent) / name).is_symlink()
            and (Path(parent) / name).stat().st_dev == device
        ]
        for name in directories + names:
            path = Path(parent) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_dev != device:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                raise ValueError(
                    "Arquivo com hard links: copie-o para um arquivo independente antes de preparar: "
                    + str(path)
                )
            if stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode):
                yield path


def dropin(root):
    value = json.dumps(str(root).replace("%", "%%"), ensure_ascii=False)
    return "[Service]\nReadWritePaths=" + value + "\n"


def write_dropin(unit_directory, unit, root):
    identifier = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    folder = unit_directory / (unit + ".d")
    folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    descriptor, temporary = tempfile.mkstemp(prefix=".site-", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(dropin(root))
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o644)
        Path(temporary).replace(folder / ("site-" + identifier + ".conf"))
    finally:
        Path(temporary).unlink(missing_ok=True)


def configure(root, uid, gid, unit_directory=Path("/etc/systemd/system")):
    if not (unit_directory / "seabirds.service").is_file():
        raise ValueError("Instale o serviço SeaBirdsCloud antes de preparar a pasta.")
    # Pré-valida tudo antes de mudar a propriedade. Não segue links nem outros mounts.
    paths = list(managed_paths(root))
    for path in paths:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not path.resolve().is_relative_to(root):
            raise ValueError("Uma entrada mudou durante a preparação. Execute novamente.")
        os.chown(path, uid, gid, follow_symlinks=False)
        mode = stat.S_IMODE(info.st_mode) & 0o777
        mode |= 0o700 if stat.S_ISDIR(info.st_mode) else 0o600
        os.chmod(path, mode, follow_symlinks=False)
    units = ["seabirds.service"]
    if (unit_directory / "seabirds-editor.service").is_file():
        units.append("seabirds-editor.service")
    for unit in units:
        write_dropin(unit_directory, unit, root)
    return units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Pasta do site/clone que contém o index.html")
    parser.add_argument("--check", action="store_true", help="Mostrar o plano sem alterar arquivos")
    args = parser.parse_args()
    try:
        if not sys.platform.startswith("linux"):
            raise ValueError("Este preparador é específico para o serviço Linux.")
        root = validate_site(args.path)
        count = len(list(managed_paths(root)))
        if args.check:
            print(f"Pasta: {root}\nUsuário/grupo: seabirds\nEntradas: {count}\n" + dropin(root))
            return 0
        if os.geteuid() != 0:
            raise ValueError("Execute como root ou com sudo para preparar esta pasta.")
        if not Path("/etc/systemd/system/seabirds.service").is_file():
            raise ValueError("Instale o serviço SeaBirdsCloud antes de preparar a pasta.")
        import grp
        import pwd

        user = pwd.getpwnam("seabirds")
        group = grp.getgrnam("seabirds")
        for parent in reversed(root.parents):
            if subprocess.run(
                ["/usr/sbin/runuser", "-u", "seabirds", "--", "/usr/bin/test", "-x", str(parent)]
            ).returncode:
                subprocess.run(
                    ["/usr/bin/setfacl", "-m", "u:seabirds:--x", "--", str(parent)], check=True
                )
        units = configure(root, user.pw_uid, group.gr_gid)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        for unit in units:
            subprocess.run(["systemctl", "try-restart", unit], check=True)
        print(f"Pasta preparada: {root}. Atualize as páginas no aplicativo.")
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print("Não foi possível preparar a pasta: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
