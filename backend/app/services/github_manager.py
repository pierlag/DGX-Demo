"""GitHub manager.

Lightweight wrapper around the GitHub REST API used by the Tunnels admin page
to:
  * authenticate with a Personal Access Token (PAT),
  * list the account's repositories,
  * report a tunnel to a repository: create an issue titled after the tunnel
    (if none exists), or add a comment with the tunnel's public URL when it
    already exists.

The token requires the ``repo`` scope (or ``public_repo`` for public repos
only). It is persisted via the shared JSON state store so it survives restarts.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services.state_store import load_state, save_state

_API = "https://api.github.com"
_DEVICE_CODE_URL = "https://github.com/login/device/code"
_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
_STATE = "github"


class GitHubManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        st = load_state(_STATE, {"token": "", "login": ""})
        self._token: str = st.get("token", "")
        self._login: str = st.get("login", "")
        # Device-flow transient state (not persisted).
        self._device = {
            "in_progress": False,
            "user_code": "",
            "verification_uri": "",
            "message": "",
        }

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def status(self) -> dict:
        return {
            "connected": bool(self._token),
            "login": self._login,
            "device": dict(self._device),
        }

    def _persist_token(self, token: str) -> dict:
        """Validate a token (and its scopes) then persist it on success."""
        try:
            r = httpx.get(f"{_API}/user",
                          headers={
                              "Authorization": f"Bearer {token}",
                              "Accept": "application/vnd.github+json",
                              "X-GitHub-Api-Version": "2022-11-28",
                          },
                          timeout=15)
        except Exception as exc:
            return {"connected": False, "login": "", "message": str(exc)}
        if r.status_code != 200:
            return {"connected": False, "login": "",
                    "message": f"Token invalide ({r.status_code})."}
        # Ensure the token carries a scope allowing issue creation on repos.
        scopes = {
            s.strip()
            for s in r.headers.get("X-OAuth-Scopes", "").split(",")
            if s.strip()
        }
        if scopes and not ({"repo", "public_repo"} & scopes):
            return {
                "connected": False,
                "login": "",
                "message": (
                    "Le jeton ne possède pas le scope « repo ». "
                    "Régénérez un jeton avec le scope « repo »."
                ),
            }
        login = r.json().get("login", "")
        with self._lock:
            self._token = token
            self._login = login
            save_state(_STATE, {"token": token, "login": login})
        return {"connected": True, "login": login,
                "message": f"Connecté en tant que {login}."}

    def set_token(self, token: str) -> dict:
        token = (token or "").strip()
        if not token:
            return {"connected": False, "login": "", "message": "Token vide."}
        return self._persist_token(token)

    # ------------------------------------------------------------------
    # Device Flow (OAuth) — requests the ``repo`` scope
    # ------------------------------------------------------------------
    def device_status(self) -> dict:
        return self.status()

    def start_device_flow(self) -> dict:
        """Begin a GitHub OAuth Device Flow requesting the ``repo`` scope.

        Returns the user code + verification URI to display; a background thread
        polls GitHub until the user authorises, then stores the access token.
        """
        client_id = (settings.github_client_id or "").strip()
        if not client_id:
            return {
                "connected": False,
                "login": "",
                "device": dict(self._device),
                "message": (
                    "VIBEMCP_GITHUB_CLIENT_ID n'est pas configuré. Créez une "
                    "OAuth App GitHub (Device Flow activé) et renseignez son "
                    "Client ID dans le fichier .env."
                ),
            }
        if self._device.get("in_progress"):
            return self.status()

        scope = (settings.github_oauth_scope or "repo").strip()
        try:
            r = httpx.post(
                _DEVICE_CODE_URL,
                headers={"Accept": "application/json"},
                data={"client_id": client_id, "scope": scope},
                timeout=20,
            )
        except Exception as exc:
            return {"connected": False, "login": "", "message": str(exc)}
        if r.status_code != 200:
            return {"connected": False, "login": "",
                    "message": f"Échec device flow ({r.status_code})."}
        payload = r.json()
        device_code = payload.get("device_code", "")
        if not device_code:
            return {"connected": False, "login": "",
                    "message": payload.get("error_description", "Erreur device flow.")}

        with self._lock:
            self._device = {
                "in_progress": True,
                "user_code": payload.get("user_code", ""),
                "verification_uri": payload.get("verification_uri",
                                                "https://github.com/login/device"),
                "message": "Ouvrez le lien GitHub et saisissez le code affiché.",
            }

        interval = int(payload.get("interval", 5)) or 5
        expires_in = int(payload.get("expires_in", 900)) or 900
        threading.Thread(
            target=self._poll_device_token,
            args=(client_id, device_code, interval, expires_in),
            daemon=True,
        ).start()
        return self.status()

    def _poll_device_token(self, client_id: str, device_code: str,
                           interval: int, expires_in: int) -> None:
        deadline = time.time() + expires_in
        while time.time() < deadline:
            time.sleep(interval)
            try:
                r = httpx.post(
                    _ACCESS_TOKEN_URL,
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": client_id,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    timeout=20,
                )
            except Exception:
                continue
            if r.status_code != 200:
                continue
            data = r.json()
            err = data.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += int(data.get("interval", 5)) or 5
                continue
            if err:
                with self._lock:
                    self._device = {
                        "in_progress": False, "user_code": "",
                        "verification_uri": "",
                        "message": data.get("error_description", err),
                    }
                return
            token = data.get("access_token", "")
            if token:
                res = self._persist_token(token)
                with self._lock:
                    self._device = {
                        "in_progress": False, "user_code": "",
                        "verification_uri": "",
                        "message": res.get("message", ""),
                    }
                return
        with self._lock:
            self._device = {
                "in_progress": False, "user_code": "", "verification_uri": "",
                "message": "Délai de connexion GitHub dépassé.",
            }

    def clear(self) -> dict:
        with self._lock:
            self._token = ""
            self._login = ""
            self._device = {
                "in_progress": False, "user_code": "",
                "verification_uri": "", "message": "",
            }
            save_state(_STATE, {"token": "", "login": ""})
        return {"connected": False, "login": "", "device": dict(self._device)}


    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------
    def list_repos(self) -> dict:
        if not self._token:
            return {"repos": [], "message": "Non connecté à GitHub."}
        repos: list[dict] = []
        try:
            page = 1
            while page <= 5:  # cap at 500 repos
                r = httpx.get(
                    f"{_API}/user/repos",
                    headers=self._headers(),
                    params={"per_page": 100, "page": page,
                            "sort": "updated", "affiliation": "owner,collaborator"},
                    timeout=20,
                )
                if r.status_code != 200:
                    return {"repos": [],
                            "message": f"Erreur GitHub ({r.status_code})."}
                batch = r.json()
                if not batch:
                    break
                for repo in batch:
                    repos.append({
                        "full_name": repo.get("full_name", ""),
                        "private": repo.get("private", False),
                    })
                if len(batch) < 100:
                    break
                page += 1
        except Exception as exc:
            return {"repos": [], "message": str(exc)}
        return {"repos": repos}

    # ------------------------------------------------------------------
    # Tunnel reporting
    # ------------------------------------------------------------------
    def report_tunnel(self, repo: str, name: str, url: str) -> dict:
        """Create an issue titled ``name`` if absent, else comment with the URL.

        ``repo`` is the ``owner/name`` full name.
        """
        if not self._token:
            return {"ok": False, "message": "Non connecté à GitHub."}
        repo = (repo or "").strip()
        name = (name or "").strip()
        if "/" not in repo:
            return {"ok": False, "message": "Dépôt invalide."}
        if not name:
            return {"ok": False, "message": "Nom de tunnel manquant."}

        title = f"Tunnel: {name}"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        url_line = url or "(URL non disponible)"

        try:
            # Find an existing open OR closed issue with this exact title.
            existing = self._find_issue(repo, title)
            if existing is None:
                body = (
                    f"Tunnel **{name}** exposé publiquement.\n\n"
                    f"- URL : {url_line}\n"
                    f"- Créé le : {ts}\n"
                )
                r = httpx.post(
                    f"{_API}/repos/{repo}/issues",
                    headers=self._headers(),
                    json={"title": title, "body": body},
                    timeout=20,
                )
                if r.status_code not in (200, 201):
                    return {"ok": False,
                            "message": f"Échec création issue ({r.status_code})."}
                issue = r.json()
                return {"ok": True, "created": True,
                        "issue_number": issue.get("number"),
                        "issue_url": issue.get("html_url"),
                        "message": f"Issue #{issue.get('number')} créée."}

            number = existing.get("number")
            comment = f"Nouvelle URL du tunnel **{name}** : {url_line}\n\n_{ts}_"
            r = httpx.post(
                f"{_API}/repos/{repo}/issues/{number}/comments",
                headers=self._headers(),
                json={"body": comment},
                timeout=20,
            )
            if r.status_code not in (200, 201):
                return {"ok": False,
                        "message": f"Échec ajout commentaire ({r.status_code})."}
            return {"ok": True, "created": False,
                    "issue_number": number,
                    "issue_url": existing.get("html_url"),
                    "message": f"Commentaire ajouté à l'issue #{number}."}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def _find_issue(self, repo: str, title: str) -> dict | None:
        """Return the first issue (open or closed) whose title matches exactly."""
        page = 1
        while page <= 5:  # cap at 500 issues
            r = httpx.get(
                f"{_API}/repos/{repo}/issues",
                headers=self._headers(),
                params={"state": "all", "per_page": 100, "page": page},
                timeout=20,
            )
            if r.status_code != 200:
                return None
            batch = r.json()
            if not batch:
                break
            for item in batch:
                # Skip pull requests (they show up in the issues endpoint).
                if "pull_request" in item:
                    continue
                if item.get("title", "") == title:
                    return item
            if len(batch) < 100:
                break
            page += 1
        return None


github_manager = GitHubManager()
