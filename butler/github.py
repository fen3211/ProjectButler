"""GitHub без SDK: личный токен + urllib.

Вход по Personal Access Token (права repo) вместо OAuth: OAuth требует
регистрации приложения у GitHub, токен даёт те же возможности за минуту.
Токен хранится локально в ~/.project-butler/github.token (только чтение владельцем).
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_PATH = Path.home() / ".project-butler" / "github.token"
API = "https://api.github.com"


# ---------- токен ----------

def get_token() -> str:
    try:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_token(token) -> None:
    token = str(token or "").strip()
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)                    # на Windows chmod условен, но не мешает
    except OSError:
        pass


def clear_token() -> None:
    try:
        TOKEN_PATH.unlink()
    except OSError:
        pass


# ---------- REST ----------

def gh_request(method, path, token=None, payload=None, timeout=25):
    """(status, data) — код GitHub и разобранный JSON; ошибки сети мягкие."""
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ProjectButler")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8", "replace"))
        except ValueError:
            data = {"message": str(exc)}
        return exc.code, data
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, {"message": f"сеть не отвечает: {exc}"}


def validate_token(token) -> dict:
    """GET /user: кто вошёл. {"ok": True, "login", ...} или {"ok": False, "error"}."""
    status, data = gh_request("GET", "/user", token)
    if status == 200:
        return {"ok": True, "login": data.get("login", ""),
                "name": data.get("name") or data.get("login", ""),
                "avatar": data.get("avatar_url", "")}
    if status == 401:
        return {"ok": False, "error": "токен недействителен или истёк"}
    if status == 403:
        return {"ok": False, "error": "GitHub отказал (лимит или права токена)"}
    return {"ok": False, "error": (data.get("message") or f"HTTP {status}") if status else
            data.get("message", "нет связи с GitHub")}


def authed_user() -> dict:
    """Текущий пользователь по сохранённому токену (без сети, если токена нет)."""
    token = get_token()
    if not token:
        return {"ok": False, "error": "токен не настроен"}
    return validate_token(token)


# ---------- git-хелперы ----------

def current_branch(root) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root),
                             capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="replace")
        return out.stdout.strip() or "main"
    except (OSError, subprocess.TimeoutExpired):
        return "main"


def remote_url(root) -> str:
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(root),
                             capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="replace")
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_remote(url) -> str:
    """https://github.com/owner/repo(.git) и git@github.com:owner/repo.git → owner/repo."""
    url = str(url or "").strip()
    m = re.search(r"github\.com[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else ""


def _git(root, *args, timeout=120):
    out = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                         timeout=timeout, encoding="utf-8", errors="replace")
    return out.returncode, (out.stdout + out.stderr).strip()


# ---------- действия ----------

def publish(root, name, private, token, log) -> dict:
    """Публикация проекта: нет репо — создать (POST /user/repos), нет origin — добавить, push.

    Токен в push-URL подставляется на лету и нигде не сохраняется.
    """
    root = str(root)
    if not os.path.isdir(os.path.join(root, ".git")):
        return {"ok": False, "error": "у проекта нет git — сначала «Создать git»"}
    if not token:
        return {"ok": False, "error": "нет токена — настрой вход через GitHub в настройках"}
    who = validate_token(token)
    if not who.get("ok"):
        return {"ok": False, "error": who.get("error", "токен не прошёл проверку")}
    login = who["login"]
    repo = name.strip() or os.path.basename(root)
    repo = re.sub(r"[^A-Za-z0-9_.-]", "-", repo)

    status, data = gh_request("GET", f"/repos/{login}/{repo}", token)
    full = f"{login}/{repo}"
    if status == 404:
        log(f"• репозитория нет — создаю {full} ({'private' if private else 'public'})…")
        status, data = gh_request("POST", "/user/repos", token,
                                  {"name": repo, "private": bool(private),
                                   "description": f"Project Butler: {os.path.basename(root)}"})
        if status not in (200, 201):
            return {"ok": False, "error": (data.get("errors", [{}])[0].get("message")
                                           or data.get("message") or f"HTTP {status}")}
    elif status != 200:
        return {"ok": False, "error": data.get("message") or f"HTTP {status}"}
    else:
        log(f"• репозиторий {full} уже существует")

    code, out = _git(root, "remote", "get-url", "origin")
    if code != 0:
        log(f"• origin не было — добавляю https://github.com/{full}.git")
        code, out = _git(root, "remote", "add", "origin", f"https://github.com/{full}.git")
        if code != 0:
            return {"ok": False, "error": out}

    branch = current_branch(root)
    log(f"• пушу ветку {branch} (токен в команду не сохраняется)…")
    code, out = _git(root, "push", "-u",
                     f"https://x-access-token:{token}@github.com/{full}.git", branch,
                     timeout=600)
    if code != 0:
        # не оставляем токен ни в сообщении об ошибке, ни в remote
        safe = out.replace(token, "***")
        return {"ok": False, "error": f"push не прошёл: {safe[:300]}"}
    return {"ok": True, "repo": full, "url": f"https://github.com/{full}",
            "branch": branch, "private": bool(data.get("private", private))}


def repo_settings(owner_repo, token, payload) -> dict:
    """PATCH репозитория: private, description, homepage, has_issues, has_wiki."""
    allowed = {k: payload[k] for k in ("private", "description", "homepage",
                                       "has_issues", "has_wiki") if k in payload}
    status, data = gh_request("PATCH", f"/repos/{owner_repo}", token, allowed)
    if status != 200:
        return {"ok": False, "error": data.get("message") or f"HTTP {status}"}
    return {"ok": True, "private": data.get("private"), "html_url": data.get("html_url", ""),
            "description": data.get("description", ""), "has_issues": data.get("has_issues"),
            "has_wiki": data.get("has_wiki")}


def create_release(owner_repo, token, tag, name, body, target="") -> dict:
    """Создаёт релиз (GitHub сам поставит тег на указанный коммит или HEAD дефолтной ветки)."""
    payload = {"tag_name": tag, "name": name or tag, "body": body or ""}
    if target:
        payload["target_commitish"] = target
    status, data = gh_request("POST", f"/repos/{owner_repo}/releases", token, payload)
    if status not in (200, 201):
        return {"ok": False, "error": data.get("message") or f"HTTP {status}"}
    return {"ok": True, "url": data.get("html_url", ""), "tag": data.get("tag_name", tag)}


def repo_info(owner_repo, token) -> dict:
    status, data = gh_request("GET", f"/repos/{owner_repo}", token)
    if status != 200:
        return {"ok": False, "error": data.get("message") or f"HTTP {status}"}
    return {"ok": True, "private": data.get("private"), "html_url": data.get("html_url", ""),
            "description": data.get("description", ""), "has_issues": data.get("has_issues"),
            "has_wiki": data.get("has_wiki"), "default_branch": data.get("default_branch", "main"),
            "stars": data.get("stargazers_count", 0)}
