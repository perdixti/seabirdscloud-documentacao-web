"""Preferencias privadas do GitHub; o token nunca e retornado pela API."""

import json
import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .filesystem import atomic_write


class GitHubSettings:
    def __init__(self, directory):
        self.directory = Path(directory) / "secrets"
        self.path = self.directory / "github.json"
        self.key_path = self.directory / "github.key"
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.token_error = ""

    @staticmethod
    def identity(name, email, require_pair=True):
        name, email = name.strip(), email.strip()
        if len(name) > 200 or any(ord(char) < 32 or char in "<>" for char in name):
            raise ValueError("Informe um nome de autor válido, com até 200 caracteres.")
        if len(email) > 254 or (email and not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", email)):
            raise ValueError("Informe um e-mail válido para o autor dos commits.")
        if require_pair and bool(name) != bool(email):
            raise ValueError("Preencha o nome e o e-mail do autor juntos.")
        return {"name": name, "email": email}

    @property
    def author(self):
        return self.state.get("author", {"name": "", "email": ""})

    def token(self, environment_token):
        mode = self.state.get("token_mode", "environment")
        if mode == "disabled":
            return ""
        if mode == "environment":
            return environment_token
        try:
            return (
                Fernet(self.key_path.read_bytes())
                .decrypt(self.state["encrypted_token"].encode())
                .decode()
            )
        except (OSError, ValueError, KeyError, InvalidToken):
            self.token_error = (
                "Não foi possível ler o token salvo. Cole um novo token e salve novamente."
            )
            return ""

    def update(self, name, email, action, token):
        author = self.identity(name, email)
        if action not in {"keep", "replace", "remove"}:
            raise ValueError("Operação de token inválida.")
        if action == "replace" and (
            not token
            or len(token) > 4096
            or not re.fullmatch(r"[!-~]+", token)
            or token in {"COLE_O_TOKEN_REAL_AQUI", "SEU_TOKEN_AQUI"}
        ):
            raise ValueError(
                "Cole um token válido no campo de segredo, sem espaços ou quebras de linha."
            )
        if action != "replace" and token:
            raise ValueError("Para salvar um novo token, selecione a substituição do segredo.")
        state = {**self.state, "author": author}
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.directory.chmod(0o700)
        if action == "replace":
            try:
                key = self.key_path.read_bytes()
                cipher = Fernet(key)
            except (OSError, ValueError):
                key = Fernet.generate_key()
                atomic_write(self.key_path, key.decode())
                cipher = Fernet(key)
            self.key_path.chmod(0o600)
            state.update(token_mode="web", encrypted_token=cipher.encrypt(token.encode()).decode())
        elif action == "remove":
            state.pop("encrypted_token", None)
            state["token_mode"] = "disabled"
        atomic_write(self.path, json.dumps(state, ensure_ascii=False))
        self.path.chmod(0o600)
        self.state = state
        if action != "keep":
            self.token_error = ""

    def status(self, token):
        return {
            "author": self.author,
            "token_configured": bool(token),
            "token_source": self.state.get("token_mode", "environment") if token else "none",
            "token_error": self.token_error,
        }
