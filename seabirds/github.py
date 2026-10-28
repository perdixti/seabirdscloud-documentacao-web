"""Publicação dos arquivos revisados usando o clone Git da máquina do servidor."""

import difflib
import hashlib
import http.client
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode
from uuid import uuid4

from .filesystem import TemplateAssets, atomic_write, local_path, preview_asset_path, read_utf8
from .github_settings import GitHubSettings
from .project_catalog import CATALOG_FILENAME, IMAGE_EXTENSIONS, CatalogSource, ProjectCatalog

PUBLISH_EXTENSIONS = {
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".ico",
}


def github_repository(url):
    patterns = [
        r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?",
        r"git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?/?",
        r"ssh://git@github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?",
    ]
    for pattern in patterns:
        if match := re.fullmatch(pattern, url, re.I):
            return "/".join(match.groups())
    raise ValueError(
        "O remoto origin precisa apontar para um repositório do github.com por HTTPS ou SSH, sem credenciais na URL."
    )


class GitHubPublisher:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.catalog = self.directory / "github-publications.json"
        self.publications = (
            json.loads(self.catalog.read_text(encoding="utf-8")) if self.catalog.exists() else []
        )
        self.plans = {}
        self.lock = threading.RLock()
        self.environment_token = os.environ.get("SEABIRDS_GITHUB_TOKEN", "").strip()
        if self.environment_token and not re.fullmatch(r"[!-~]+", self.environment_token):
            raise ValueError("SEABIRDS_GITHUB_TOKEN contém caracteres inválidos.")
        self.preferences = GitHubSettings(directory)
        self.token = self.preferences.token(self.environment_token)
        self.workflow = os.environ.get("SEABIRDS_GITHUB_WORKFLOW", "deploy.yml")
        if not re.fullmatch(r"[\w.-]+\.ya?ml", self.workflow):
            raise ValueError(
                "SEABIRDS_GITHUB_WORKFLOW precisa ser o nome de um arquivo .yml ou .yaml."
            )

    def environment(self, token=None):
        token = self.token if token is None else token
        env = os.environ.copy()
        # Repositório e índice são definidos por cada operação, nunca por um ambiente herdado.
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            env.pop(key, None)
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never", GIT_LITERAL_PATHSPECS="1")
        env["LC_ALL"] = "C"
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
        env.pop("SEABIRDS_GITHUB_TOKEN", None)
        if token:
            env["SEABIRDS_GITHUB_TOKEN"] = token
            python = Path(sys.executable).as_posix()
            helper = Path(__file__).with_name("github_askpass.py").as_posix()
            launcher = self.directory / ".github-askpass.sh"
            script = f'#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(helper)} "$@"\n'
            self.directory.mkdir(parents=True, exist_ok=True)
            if not launcher.exists() or launcher.read_text(encoding="utf-8") != script:
                atomic_write(launcher, script)
                launcher.chmod(0o700)
            env["GIT_ASKPASS"] = launcher.resolve().as_posix()
        return env

    def clean_error(self, text, token=""):
        for secret in {self.token, self.environment_token, token} - {""}:
            text = text.replace(secret, "[oculto]")
        return re.sub(r"https?://[^\s/@]+(?::[^\s/@]*)?@", "https://[oculto]@", text).strip()[
            -1500:
        ]

    def git(self, root, *args, data=None, check=True, timeout=45, identity=None):
        token = self.token
        command = ["git", "-c", "core.quotepath=false"]
        if token:
            command += ["-c", "credential.helper="]
        if identity:
            command += [
                "-c",
                "user.name=" + identity["name"],
                "-c",
                "user.email=" + identity["email"],
            ]
        command += ["-C", str(root), *args]
        try:
            result = subprocess.run(
                command,
                input=data,
                capture_output=True,
                env=self.environment(token),
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError as exc:
            raise ValueError("Git não está instalado na máquina que executa o aplicativo.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "O Git excedeu o tempo de espera. Confira a conexão e a autenticação do servidor."
            ) from exc
        if check and result.returncode:
            detail = self.clean_error(
                (result.stderr or result.stdout).decode("utf-8", errors="replace"), token
            )
            if "dubious ownership" in detail:
                raise ValueError(
                    "O clone pertence a outro usuário do Linux. Prepare a pasta para o usuário do aplicativo com seabirds-configure-site antes de publicar."
                )
            if (
                "could not read Username for 'https://github.com'" in detail
                or "Authentication failed for 'https://github.com" in detail
            ):
                raise ValueError(
                    "Configure um token com acesso ao repositório em Site e repositórios → Configurar GitHub."
                )
            raise ValueError("Falha no Git: " + detail)
        return result

    def text(self, root, *args):
        return self.git(root, *args).stdout.decode("utf-8").strip()

    def author(self, root):
        defaults = self.preferences.author
        return {
            key: self.git(root, "config", "--get", "user." + key, check=False)
            .stdout.decode("utf-8")
            .strip()
            or defaults[key]
            for key in ("name", "email")
        }

    def settings_status(self, directory=""):
        with self.lock:
            result = self.preferences.status(self.token)
            if directory:
                try:
                    root = self.root(directory)
                    repository = self.repository(root)[0]
                    result.update(
                        directory=str(root),
                        repository=repository,
                        repository_author=self.author(root),
                    )
                except ValueError as exc:
                    result["repository_error"] = str(exc)
            return result

    def configure(self, name, email, action="keep", token="", directory=""):
        with self.lock:
            author = self.preferences.identity(name, email)
            root = self.root(directory) if directory else None
            if root:
                self.repository(root)
            # Valida e grava o segredo antes de alterar o Git; nenhum valor secreto retorna.
            self.preferences.update(name, email, action, token)
            self.token = self.preferences.token(self.environment_token)
            if root and author["name"]:
                try:
                    for key, value in author.items():
                        self.git(root, "config", "--local", "--", "user." + key, value)
                except ValueError as exc:
                    raise ValueError(
                        "As preferências foram salvas, mas não foi possível configurar o autor neste clone. Confira as permissões da pasta e tente salvar novamente. "
                        + str(exc)
                    ) from exc
            return self.settings_status(str(root) if root else "")

    def root(self, directory, output_path=""):
        # A saída define o repositório; um caminho salvo antigo não pode publicar o gerador.
        candidate = local_path(output_path or directory)
        if not candidate.is_dir():
            candidate = candidate.parent
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        root = Path(self.text(candidate, "rev-parse", "--show-toplevel")).resolve()
        if root == Path(__file__).resolve().parent.parent:
            raise ValueError(
                "O HTML de saída está na pasta do gerador. Salve a documentação dentro da pasta do site antes de publicar."
            )
        return root

    @staticmethod
    def directory_path(value):
        if not value:
            return None
        try:
            path = local_path(value)
        except ValueError:
            return None
        return path.parent if path.is_file() else path

    def site_root(self, root, directory, document):
        output = local_path(document.generation.output_path)
        for value in (directory, document.generation.site_dir):
            candidate = self.directory_path(value)
            if (
                candidate
                and candidate.is_relative_to(root)
                and output.is_relative_to(candidate)
                and (candidate / "index.html").is_file()
            ):
                return candidate
        if (root / "index.html").is_file():
            return root
        # Em um monorepo, usa o index mais externo entre a saída e a raiz Git.
        result = root
        for ancestor in [output.parent, *output.parent.parents]:
            if not ancestor.is_relative_to(root):
                break
            if (ancestor / "index.html").is_file():
                result = ancestor
        return result

    def recommended_files(self, root, site, document):
        output = local_path(document.generation.output_path)
        paths = [
            output,
            *(local_path(image.path) for image in document.generation.images if image.path),
        ]
        if output.is_file():
            for reference, _ in TemplateAssets(read_utf8(output, 10 * 1024 * 1024)).references:
                image = preview_asset_path(reference, output, site)
                if image and image.suffix.lower() in PUBLISH_EXTENSIONS - {".html", ".htm"}:
                    paths.append(image)
        return {path.relative_to(root).as_posix() for path in paths if path.is_relative_to(site)}

    def catalog_images(self, root, site, changes):
        result = set()
        state_path = self.directory / "site-workspace.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        config = state.get("catalogs", {}).get(str(site), {})
        try:
            listing = ProjectCatalog.site_path(site, config.get("page", "paginas/projetos.html"))
            for change in changes:
                path = root / change["path"]
                if path.name != CATALOG_FILENAME or not path.is_file():
                    continue
                source = CatalogSource(read_utf8(path, 2_000_000))
                for entry in source.entries.values():
                    try:
                        image = ProjectCatalog.reference(
                            site, listing, entry["imagem"], IMAGE_EXTENSIONS
                        )[1]
                        result.add(image.relative_to(root).as_posix())
                    except ValueError:
                        continue
        except ValueError:
            pass
        return result

    def repository(self, root):
        origins = self.text(root, "remote", "get-url", "--all", "origin").splitlines()
        pushes = self.text(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
        if len(origins) != 1 or len(pushes) != 1:
            raise ValueError(
                "Configure um único destino GitHub no origin para revisar a publicação."
            )
        origin, push = origins[0], pushes[0]
        repository = github_repository(origin)
        if github_repository(push).lower() != repository.lower():
            raise ValueError(
                "Os remotos de leitura e envio do origin apontam para repositórios diferentes."
            )
        return repository, origin, push

    def validate_branch(self, root):
        if self.text(root, "branch", "--show-current") != "main":
            raise ValueError("Abra a branch main no repositório antes de publicar.")
        for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply"):
            path = Path(self.text(root, "rev-parse", "--git-path", name))
            if not path.is_absolute():
                path = root / path
            if path.exists():
                raise ValueError("Conclua a operação Git em andamento antes de publicar.")

    def remote_head(self, root):
        self.git(root, "fetch", "--no-tags", "origin", "refs/heads/main")
        return self.text(root, "rev-parse", "FETCH_HEAD")

    @staticmethod
    def allowed(name):
        path = PurePosixPath(name)
        return (
            bool(name)
            and not path.is_absolute()
            and not any(
                part in {"..", ".git", ".github"} or part.startswith(".") for part in path.parts
            )
            and not any(ord(char) < 32 for char in name)
            and (path.suffix.lower() in PUBLISH_EXTENSIONS or path.name == CATALOG_FILENAME)
        )

    def changes(self, root, site=None):
        raw = self.git(
            root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"
        ).stdout
        result = []
        for row in raw.split(b"\0"):
            if not row:
                continue
            status, name = row[:2].decode("ascii"), row[3:].decode("utf-8")
            if "U" in status or status in {"AA", "DD"}:
                raise ValueError("Resolva os conflitos Git antes de publicar.")
            if self.allowed(name) and (site is None or (root / name).is_relative_to(site)):
                result.append(
                    {
                        "path": name,
                        "status": "deleted"
                        if "D" in status
                        else "added"
                        if status == "??" or "A" in status
                        else "modified",
                    }
                )
        if len(result) > 300:
            raise ValueError(
                "Há mais de 300 arquivos publicáveis alterados. Divida a publicação em partes pelo Git."
            )
        return result

    def snapshot(self, root, head, name):
        path = root / name
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("Um arquivo selecionado aponta para fora do repositório: " + name)
        if path.exists() and (not path.is_file() or path.stat().st_size > 10 * 1024 * 1024):
            raise ValueError("O arquivo precisa ter até 10 MB: " + name)
        raw = path.read_bytes() if path.is_file() else None
        digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
        oid = (
            self.git(root, "hash-object", "--path=" + name, "--stdin", data=raw)
            .stdout.decode()
            .strip()
            if raw is not None
            else None
        )
        diff = "Imagem binária: confira o arquivo na pasta do site."
        if path.suffix.lower() in {".html", ".htm", ".svg"} or path.name == CATALOG_FILENAME:
            old = self.git(root, "cat-file", "blob", f"{head}:{name}", check=False).stdout
            before = old.decode("utf-8", errors="replace").splitlines(True)
            after = (raw or b"").decode("utf-8", errors="replace").splitlines(True)
            diff = "".join(
                difflib.unified_diff(
                    before, after, fromfile="anterior/" + name, tofile="novo/" + name
                )
            )
            if len(diff) > 30000:
                diff = (
                    diff[:30000]
                    + "\n… Prévia limitada. Confira o arquivo completo antes de publicar."
                )
        return {"digest": digest, "oid": oid, "size": len(raw or b""), "diff": diff}

    def last(self, root):
        return next(
            (item for item in reversed(self.publications) if item["root"] == str(root)), None
        )

    def inspect(self, directory, document, site_only=False):
        with self.lock:
            if site_only:
                site = local_path(directory)
                root = self.root(directory)
                if not site.is_dir() or not site.is_relative_to(root):
                    raise ValueError("Selecione a raiz local do site dentro do repositório.")
            else:
                if not document.generation.output_path or Path(
                    document.generation.output_path
                ).suffix.lower() not in {".html", ".htm"}:
                    raise ValueError(
                        "Defina o arquivo HTML de saída antes de revisar a publicação."
                    )
                directory = directory or document.generation.github_repository_path
                root = self.root(directory, document.generation.output_path)
                site = self.site_root(root, directory, document)
            repository, origin, push = self.repository(root)
            self.validate_branch(root)
            head = self.text(root, "rev-parse", "HEAD")
            remote_head = self.remote_head(root)
            ahead, behind = map(
                int,
                self.text(
                    root, "rev-list", "--left-right", "--count", f"{head}...{remote_head}"
                ).split(),
            )
            recommended = None if site_only else self.recommended_files(root, site, document)
            changes = self.changes(root, site)
            if recommended is not None:
                recommended.update(self.catalog_images(root, site, changes))
            entries, total = {}, 0
            for change in changes:
                snapshot = self.snapshot(root, head, change["path"])
                total += snapshot["size"]
                if total > 100 * 1024 * 1024:
                    raise ValueError(
                        "As alterações ultrapassam 100 MB. Divida a publicação pelo Git."
                    )
                entries[change["path"]] = {
                    **change,
                    **snapshot,
                    "selected": recommended is None
                    or change["path"] in recommended
                    or PurePosixPath(change["path"]).name == CATALOG_FILENAME,
                }
            token = uuid4().hex
            now = time.monotonic()
            self.plans = {key: value for key, value in self.plans.items() if value["expires"] > now}
            while len(self.plans) >= 10:
                self.plans.pop(next(iter(self.plans)))
            self.plans[token] = {
                "root": root,
                "site_root": site,
                "repository": repository,
                "origin": origin,
                "push": push,
                "head": head,
                "remote_head": remote_head,
                "entries": entries,
                "expires": now + 900,
                "result": None,
            }
            author = self.author(root)
            return {
                "token": token,
                "root": str(root),
                "site_root": str(site),
                "directory_corrected": bool(directory) and self.directory_path(directory) != site,
                "site_only": site_only,
                "repository": repository,
                "branch": "main",
                "head": head,
                "remote_head": remote_head,
                "ahead": ahead,
                "behind": behind,
                "author": author,
                "files": [
                    {key: value for key, value in item.items() if key not in {"digest", "oid"}}
                    for item in entries.values()
                ],
                "last": self.last(root),
                "actions_url": f"https://github.com/{repository}/actions",
                "workflow": self.workflow,
            }

    def plan(self, token):
        plan = self.plans.get(token)
        if not plan or plan["expires"] <= time.monotonic():
            raise ValueError("A revisão expirou. Gere o HTML e revise a publicação novamente.")
        return plan

    def verify(self, plan):
        root = plan["root"]
        self.validate_branch(root)
        if self.repository(root) != (plan["repository"], plan["origin"], plan["push"]):
            raise ValueError("O remoto mudou. Revise a publicação novamente.")
        if self.text(root, "rev-parse", "HEAD") != plan["head"]:
            raise ValueError("A main local mudou. Revise a publicação novamente.")

    def sync(self, token):
        with self.lock:
            plan = self.plan(token)
            self.verify(plan)
            root = plan["root"]
            remote_head = self.remote_head(root)
            if self.git(
                root, "merge-base", "--is-ancestor", plan["head"], remote_head, check=False
            ).returncode:
                raise ValueError(
                    "A main local possui commits próprios. Resolva a divergência pelo Git antes de atualizar."
                )
            self.git(root, "merge", "--ff-only", "--no-edit", remote_head)
            del self.plans[token]
            return {"root": str(root), "head": self.text(root, "rev-parse", "HEAD")}

    def save(self):
        atomic_write(self.catalog, json.dumps(self.publications, ensure_ascii=False))

    def publish(self, token, selected, message):
        with self.lock:
            plan = self.plan(token)
            if plan["result"]:
                return plan["result"]
            selected = list(dict.fromkeys(selected))
            if (
                not selected
                or len(selected) > 100
                or any(name not in plan["entries"] for name in selected)
            ):
                raise ValueError("Selecione de 1 a 100 arquivos da revisão atual.")
            if not message.strip() or "\x00" in message:
                raise ValueError("Informe uma mensagem de commit válida.")
            self.verify(plan)
            root = plan["root"]
            author = self.author(root)
            if not author["name"] or not author["email"]:
                raise ValueError(
                    "Configure o nome e o e-mail do autor em Configurar GitHub antes de publicar."
                )
            if self.remote_head(root) != plan["head"]:
                raise ValueError(
                    "A main local e a remota precisam estar na mesma revisão. Atualize a main ou reenvie o commit pendente."
                )
            for name in selected:
                if (
                    self.snapshot(root, plan["head"], name)["digest"]
                    != plan["entries"][name]["digest"]
                ):
                    raise ValueError(
                        "O arquivo mudou após a revisão: " + name + ". Revise novamente."
                    )
            paths = b"\0".join(name.encode("utf-8") for name in selected) + b"\0"
            self.git(root, "add", "--pathspec-from-file=-", "--pathspec-file-nul", data=paths)
            self.verify(plan)
            self.git(
                root,
                "commit",
                "--only",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
                "-m",
                message.strip(),
                data=paths,
                identity=author,
            )
            sha = self.text(root, "rev-parse", "HEAD")
            changed = self.git(
                root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-z", "-r", sha
            ).stdout
            actual = {name.decode("utf-8") for name in changed.split(b"\0") if name}
            valid = (
                actual == set(selected) and self.text(root, "rev-parse", sha + "^") == plan["head"]
            )
            for name in selected:
                result = self.git(root, "rev-parse", "--verify", f"{sha}:{name}", check=False)
                actual_oid = result.stdout.decode().strip() if not result.returncode else None
                valid = valid and actual_oid == plan["entries"][name]["oid"]
            if not valid:
                raise ValueError(
                    "O commit local difere dos arquivos revisados, possivelmente por um hook. O envio foi interrompido; confira o Git antes de continuar."
                )
            publication = {
                "id": uuid4().hex,
                "root": str(root),
                "repository": plan["repository"],
                "origin": plan["origin"],
                "push": plan["push"],
                "sha": sha,
                "parent": plan["head"],
                "message": message.strip(),
                "files": selected,
                "status": "pending_push",
                "created_at": datetime.now(UTC).isoformat(),
                "workflow": self.workflow,
                "commit_url": f"https://github.com/{plan['repository']}/commit/{sha}",
                "actions_url": f"https://github.com/{plan['repository']}/actions",
            }
            self.publications.append(publication)
            self.save()
            plan["result"] = self.push(publication)
            return plan["result"]

    def push(self, publication):
        root = Path(publication["root"])
        error = None
        try:
            self.validate_branch(root)
            if self.repository(root) != (
                publication["repository"],
                publication["origin"],
                publication["push"],
            ):
                raise ValueError(
                    "O remoto mudou durante a publicação. Confira o repositório antes de reenviar."
                )
            if self.text(root, "rev-parse", "HEAD") != publication["sha"]:
                raise ValueError(
                    "A main local mudou durante a publicação. Confira o commit antes de reenviar."
                )
            self.git(
                root,
                "push",
                "--porcelain",
                "origin",
                publication["sha"] + ":refs/heads/main",
                timeout=60,
            )
        except ValueError as exc:
            error = str(exc)
        if error is None:
            publication["status"] = "pushed"
        self.save()
        return {"publication": dict(publication), "push_error": error}

    def publication(self, identifier):
        return next((item for item in self.publications if item["id"] == identifier), None)

    def api_token(self, item):
        if self.token:
            return self.token
        # Reutiliza o helper Git existente; a credencial fica só em memória.
        query = f"protocol=https\nhost=github.com\npath={item['repository']}.git\n\n"
        try:
            result = self.git(
                Path(item["root"]),
                "credential",
                "fill",
                data=query.encode(),
                check=False,
                timeout=15,
            )
        except ValueError:
            return ""
        if result.returncode:
            return ""
        fields = dict(
            line.split("=", 1)
            for line in result.stdout.decode("utf-8", errors="replace").splitlines()
            if "=" in line
        )
        password = fields.get("password", "")
        return password if re.fullmatch(r"[!-~]+", password) else ""

    def retry(self, identifier):
        with self.lock:
            item = self.publication(identifier)
            if not item:
                raise ValueError("Publicação não encontrada.")
            if item["status"] == "pushed":
                return {"publication": item, "push_error": None}
            root = Path(item["root"])
            self.validate_branch(root)
            if self.repository(root) != (item["repository"], item["origin"], item["push"]):
                raise ValueError("O remoto desta publicação foi alterado.")
            if self.text(root, "rev-parse", "HEAD") != item["sha"]:
                raise ValueError(
                    "A main local mudou após o commit pendente. Confira o Git antes de reenviar."
                )
            remote_head = self.remote_head(root)
            if remote_head == item["sha"]:
                item["status"] = "pushed"
                self.save()
                return {"publication": item, "push_error": None}
            if remote_head != item["parent"]:
                raise ValueError(
                    "A main remota mudou. Resolva a divergência pelo Git antes de reenviar o commit."
                )
            return self.push(item)

    def runs(self, identifier):
        item = self.publication(identifier)
        if not item or item["status"] != "pushed":
            raise ValueError("A publicação ainda não foi enviada ao GitHub.")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SeaBirdsCloud",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if token := self.api_token(item):
            headers["Authorization"] = "Bearer " + token
        query = urlencode(
            {"head_sha": item["sha"], "branch": "main", "event": "push", "per_page": 10}
        )
        connection = http.client.HTTPSConnection("api.github.com", timeout=15)
        try:
            path = f"/repos/{item['repository']}/actions/workflows/{quote(item['workflow'], safe='')}/runs?{query}"
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            content = response.read(2_000_001)
            if response.status != 200:
                raise ValueError(
                    "Não foi possível consultar o GitHub Actions. Confira o acesso ao repositório e, para repositórios privados, SEABIRDS_GITHUB_TOKEN com Actions: read."
                )
            if len(content) > 2_000_000:
                raise ValueError("Resposta do GitHub Actions excedeu o limite.")
            result = json.loads(content)
            return {
                "runs": [
                    {
                        "id": run["id"],
                        "name": run.get("name", item["workflow"]),
                        "status": run["status"],
                        "conclusion": run.get("conclusion"),
                        "url": f"https://github.com/{item['repository']}/actions/runs/{int(run['id'])}",
                    }
                    for run in result.get("workflow_runs", [])
                    if run.get("head_sha") == item["sha"]
                ],
                "actions_url": item["actions_url"],
            }
        except (OSError, json.JSONDecodeError, http.client.HTTPException) as exc:
            raise ValueError(
                "Não foi possível consultar a pipeline. Abra o GitHub Actions ou tente novamente."
            ) from exc
        finally:
            connection.close()
