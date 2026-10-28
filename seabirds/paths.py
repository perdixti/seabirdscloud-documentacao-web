"""Caminhos do servidor e diagnóstico de acesso, em Windows e POSIX."""

import getpass
import os
import re
import shlex
from pathlib import Path
from urllib.parse import unquote, urlsplit


def local_path(value: str) -> Path:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("Informe um caminho válido do servidor.")
    if value.lower().startswith("file:"):
        parsed = urlsplit(value)
        if parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
            raise ValueError("Informe o caminho local da pasta, sem nome de outro servidor.")
        value = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", value):
            value = value[1:]
    if os.name != "nt" and re.match(r"^(?:[A-Za-z]:|\\\\)", value):
        raise ValueError(
            "Este servidor usa Linux. Informe o caminho nesta máquina, como /opt/meu-site ou /srv/seabirds/site."
        )
    if "://" in value:
        raise ValueError("Informe um caminho de arquivo ou pasta do servidor, não uma URL web.")
    return Path(value).expanduser().resolve()


def server_user():
    if os.name == "posix":
        import pwd

        return pwd.getpwuid(os.geteuid()).pw_name
    return getpass.getuser()


def folder_access(directory):
    writable = os.access(directory, os.W_OK | os.X_OK)
    helper = Path("/usr/local/sbin/seabirds-configure-site")
    return {
        "writable": writable,
        "user": server_user(),
        "setup_command": (
            "sudo /usr/local/sbin/seabirds-configure-site " + shlex.quote(str(directory))
            if os.name == "posix" and helper.is_file()
            else ""
        ),
    }


def directory_entries(directory):
    """Uma entrada inacessível não impede navegar nas outras pastas."""
    entries, skipped = [], 0
    for path in directory.iterdir():
        try:
            is_directory = path.is_dir()
            if path.is_symlink() and not path.exists():
                skipped += 1
                continue
            if is_directory and not os.access(path, os.R_OK | os.X_OK):
                skipped += 1
                continue
            entries.append((path, is_directory))
        except OSError:
            skipped += 1
    entries.sort(key=lambda item: (not item[1], item[0].name.casefold()))
    return entries, skipped
