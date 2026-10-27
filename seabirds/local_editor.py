"""Iniciador opcional do VS Code Web instalado no Windows, somente em loopback."""

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
from pathlib import Path

from .filesystem import atomic_write


class LocalEditor:
    def __init__(self, directory, state, persist):
        self.directory = Path(directory)
        self.state, self.persist = state, persist
        self.process = None
        self.lock = threading.RLock()

    @staticmethod
    def executable():
        if os.name != "nt":
            return None
        command = shutil.which("code-tunnel")
        if command:
            return Path(command).resolve()
        command = shutil.which("code")
        candidate = Path(command).parent / "code-tunnel.exe" if command else None
        return candidate.resolve() if candidate and candidate.is_file() else None

    def owns_process(self, record):
        if not record:
            return False
        if self.process and self.process.pid == record["pid"]:
            return self.process.poll() is None
        if os.name != "nt":
            return False
        try:
            pid = int(record["pid"])
            command = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if($p){{$p | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress}}"
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            info = json.loads(result.stdout.decode("utf-8-sig"))
            return (
                os.path.normcase(info["ExecutablePath"]) == os.path.normcase(record["executable"])
                and str(self.directory / "vscode-server").casefold()
                in info["CommandLine"].casefold()
                and "serve-web" in info["CommandLine"]
            )
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            return False

    def start(self, root, confirm_license, port=8765):
        if confirm_license is not True:
            raise ValueError("Aceite os termos do Visual Studio Code Server para iniciar o editor.")
        with self.lock:
            executable = self.executable()
            if not executable:
                raise ValueError(
                    "O iniciador local requer o VS Code instalado no Windows. No LXC, configure a URL de um code-server."
                )
            if self.owns_process(self.state.get("local_editor")):
                return {"started": True, "url": self.state["editor_url"]}
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    raise ValueError(
                        "A porta do editor está ocupada por outro serviço. Configure a URL do editor existente."
                    )
            except OSError:
                pass
            version = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.decode("utf-8", errors="replace")
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
            if not match or tuple(map(int, match.groups())) < (1, 128, 1):
                raise ValueError(
                    "Atualize o VS Code para uma versão recente antes de iniciar o editor Web."
                )
            token_file = self.directory / "vscode-web.token"
            atomic_write(token_file, secrets.token_urlsafe(32))
            args = [
                str(executable),
                "--cli-data-dir",
                str(self.directory / "vscode-cli"),
                "serve-web",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--connection-token-file",
                str(token_file),
                "--accept-server-license-terms",
                "--default-folder",
                str(root),
                "--server-data-dir",
                str(self.directory / "vscode-server"),
                "--disable-telemetry",
            ]
            with (self.directory / "vscode-web.log").open("wb") as log:
                process = subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            self.process = process
            self.state.update(
                editor_url=f"http://127.0.0.1:{port}",
                editor_kind="vscode-serve-web",
                local_editor={"pid": process.pid, "port": port, "executable": str(executable)},
            )
            try:
                self.persist()
            except Exception:
                process.terminate()
                raise
            return {"started": True, "url": self.state["editor_url"]}

    def auth_query(self, parsed):
        record = self.state.get("local_editor")
        if record and parsed.hostname == "127.0.0.1" and parsed.port == record["port"]:
            if not self.owns_process(record):
                raise ValueError(
                    "O VS Code Web local não está em execução. Inicie-o novamente nas configurações do editor."
                )
            return {
                "tkn": (self.directory / "vscode-web.token").read_text(encoding="utf-8").strip()
            }
        return {}
