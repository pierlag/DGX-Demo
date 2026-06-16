"""DevTunnel manager.

Wraps the Microsoft `devtunnel` CLI to expose local ports to the internet,
tied to the user's GitHub account. Supports multiple *named* tunnels created
with the explicit workflow:

    1. devtunnel create <name> --allow-anonymous
    2. devtunnel port create <name> -p <port> --protocol http
    3. devtunnel host <name>            (parses the dynamic public URL)

Tunnels can be listed (`devtunnel list`) and deleted (`devtunnel delete`).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass

from app.config import settings  # noqa: F401  (kept for default ports usage)

_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]*devtunnels\.ms[^\s]*")
# GitHub device-code login: "...open the page https://github.com/login/device
# and enter the code XXXX-XXXX to authenticate."
_DEVICE_CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
_VERIFY_URL_RE = re.compile(r"https://\S*github\.com/login/device\S*")
# Tunnel ID as printed by `devtunnel list` / `devtunnel create` (e.g. dashboard.euw)
_TUNNEL_ID_RE = re.compile(r"\b([a-z0-9][a-z0-9-]*\.[a-z0-9]{2,})\b")


@dataclass
class LoginState:
    logged_in: bool = False
    account: str = ""
    message: str = ""
    # GitHub device-code login flow
    device_code: str = ""
    verification_url: str = ""
    login_in_progress: bool = False


@dataclass
class Tunnel:
    name: str
    port: int
    protocol: str = "http"
    url: str = ""
    tunnel_id: str = ""
    hosting: bool = False
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "port": self.port,
            "protocol": self.protocol,
            "url": self.url,
            "tunnel_id": self.tunnel_id,
            "hosting": self.hosting,
            "message": self.message,
        }


class DevTunnelManager:
    def __init__(self) -> None:
        self.login = LoginState()
        self._login_proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        # In-memory tunnels we created/host in this process, keyed by name.
        self._tunnels: dict[str, Tunnel] = {}
        self._procs: dict[str, subprocess.Popen] = {}

    def _cli(self) -> str | None:
        return shutil.which("devtunnel")

    # ------------------------------------------------------------------
    # GitHub login
    # ------------------------------------------------------------------
    def login_status(self) -> LoginState:
        cli = self._cli()
        if not cli:
            self.login.message = "devtunnel CLI introuvable."
            return self.login
        try:
            res = subprocess.run([cli, "user", "show"], capture_output=True,
                                 text=True, timeout=15)
            out = (res.stdout + res.stderr).strip()
            low = out.lower()
            logged_out = (
                not out
                or "not logged in" in low
                or "no user" in low
                or "please log in" in low
            )
            self.login.logged_in = not logged_out
            self.login.account = out.splitlines()[0] if (out and not logged_out) else ""
            if self.login.logged_in:
                self.login.login_in_progress = False
                self.login.device_code = ""
                self.login.verification_url = ""
        except Exception as exc:
            self.login.message = str(exc)
        return self.login

    def login_github(self) -> LoginState:
        """Trigger GitHub device-code login in the background."""
        cli = self._cli()
        if not cli:
            self.login.message = "devtunnel CLI introuvable."
            return self.login

        if self._login_proc and self._login_proc.poll() is None:
            return self.login

        self.login.device_code = ""
        self.login.verification_url = ""
        self.login.login_in_progress = True
        self.login.message = "Initialisation de la connexion GitHub…"

        try:
            self._login_proc = subprocess.Popen(
                [cli, "user", "login", "-g", "-d"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except Exception as exc:
            self.login.login_in_progress = False
            self.login.message = str(exc)
            return self.login

        def _reader() -> None:
            assert self._login_proc and self._login_proc.stdout
            while True:
                line = self._login_proc.stdout.readline()
                if not line:
                    break
                url_m = _VERIFY_URL_RE.search(line)
                if url_m:
                    self.login.verification_url = url_m.group(0)
                code_m = _DEVICE_CODE_RE.search(line)
                if code_m:
                    self.login.device_code = code_m.group(1)
                if self.login.device_code or self.login.verification_url:
                    self.login.message = (
                        "Ouvrez le lien GitHub et saisissez le code affiché."
                    )
            self.login.login_in_progress = False
            self.login_status()

        threading.Thread(target=_reader, daemon=True).start()

        import time as _time
        for _ in range(20):  # up to ~2s
            if self.login.device_code:
                break
            _time.sleep(0.1)
        return self.login

    # ------------------------------------------------------------------
    # Tunnel lifecycle
    # ------------------------------------------------------------------
    def list_tunnels(self) -> list[dict]:
        """Return every configured tunnel (from `devtunnel list`), merged with
        any live hosting state tracked in this process."""
        cli = self._cli()
        configured: dict[str, dict] = {}
        if cli:
            try:
                res = subprocess.run([cli, "list"], capture_output=True,
                                     text=True, timeout=20)
                out = res.stdout + res.stderr
                for raw in out.splitlines():
                    line = raw.strip()
                    low = line.lower()
                    if not line or low.startswith("tunnel id") or "tunnel(s)" in low:
                        continue
                    m = _TUNNEL_ID_RE.match(line)
                    if not m:
                        continue
                    tunnel_id = m.group(1)
                    name = tunnel_id.split(".")[0]
                    configured[name] = {"name": name, "tunnel_id": tunnel_id}
            except Exception:
                pass

        # Merge: start from configured, overlay in-memory live state.
        result: dict[str, dict] = {}
        for name, info in configured.items():
            result[name] = {
                "name": name,
                "tunnel_id": info.get("tunnel_id", ""),
                "port": 0,
                "protocol": "http",
                "url": "",
                "hosting": False,
                "message": "",
            }
        for name, t in self._tunnels.items():
            proc = self._procs.get(name)
            if proc is not None and proc.poll() is not None:
                t.hosting = False
            merged = result.get(name, {})
            d = t.as_dict()
            if not d.get("tunnel_id") and merged.get("tunnel_id"):
                d["tunnel_id"] = merged["tunnel_id"]
            result[name] = d
        return sorted(result.values(), key=lambda d: d["name"])

    def create_tunnel(self, name: str, port: int,
                      protocol: str = "http") -> dict:
        """Create (if needed), configure the port, and start hosting a named
        tunnel, parsing the dynamically generated public URL."""
        cli = self._cli()
        if not cli:
            return {"ok": False, "message": "devtunnel CLI introuvable."}
        name = (name or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            return {"ok": False,
                    "message": "Nom invalide (minuscules, chiffres, tirets)."}

        with self._lock:
            # Already hosting? Return current state.
            existing_proc = self._procs.get(name)
            if existing_proc and existing_proc.poll() is None:
                return {"ok": True, "tunnel": self._tunnels[name].as_dict(),
                        "message": "Tunnel déjà en cours d'hébergement."}

            tunnel = Tunnel(name=name, port=port, protocol=protocol,
                            message="Création du tunnel…")
            self._tunnels[name] = tunnel

            # 0. Does the tunnel already exist? `devtunnel show <name>`
            #    resolves by bare name. We must NOT call `create` on an existing
            #    tunnel: a conflicting `create` corrupts the default-tunnel
            #    resolution and makes the subsequent `port create`/`host` fail
            #    with "Tunnel not found".
            show = subprocess.run(
                [cli, "show", name],
                capture_output=True, text=True, timeout=30,
            )
            show_out = show.stdout + show.stderr
            exists = show.returncode == 0 and "tunnel id" in show_out.lower()
            if exists:
                id_m = _TUNNEL_ID_RE.search(show_out)
                if id_m:
                    tunnel.tunnel_id = id_m.group(1)
            else:
                # 1. devtunnel create <name> --allow-anonymous
                create = subprocess.run(
                    [cli, "create", name, "--allow-anonymous"],
                    capture_output=True, text=True, timeout=30,
                )
                create_out = create.stdout + create.stderr
                id_m = _TUNNEL_ID_RE.search(create_out)
                if id_m:
                    tunnel.tunnel_id = id_m.group(1)
                low_create = create_out.lower()
                already = (
                    "already exists" in low_create
                    or "conflict with existing" in low_create
                )
                if create.returncode != 0 and not already:
                    tunnel.message = f"Échec création : {create_out.strip()[:200]}"
                    return {"ok": False, "tunnel": tunnel.as_dict(),
                            "message": tunnel.message}

            # 2. devtunnel port create <name> -p <port> --protocol http
            port_res = subprocess.run(
                [cli, "port", "create", name, "-p", str(port),
                 "--protocol", protocol],
                capture_output=True, text=True, timeout=30,
            )
            port_out = port_res.stdout + port_res.stderr
            low_port = port_out.lower()
            # The port may already be configured on the tunnel — reported as
            # "already exists" or as a port-number "Conflict".
            port_exists = (
                "already exists" in low_port
                or "conflict with existing" in low_port
                or "port number conflicts" in low_port
            )
            if port_res.returncode != 0 and not port_exists:
                tunnel.message = f"Échec port : {port_out.strip()[:200]}"
                return {"ok": False, "tunnel": tunnel.as_dict(),
                        "message": tunnel.message}

            # 3. devtunnel host <name> (long-running; parse the public URL)
            proc = subprocess.Popen(
                [cli, "host", name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            self._procs[name] = proc
            tunnel.hosting = True
            tunnel.message = "Hébergement en cours, récupération de l'URL…"

            def _select_url(found: list[str]) -> str:
                # Drop the "inspect network activity" URLs.
                cands = [u for u in found if "inspect" not in u] or found
                # Prefer the clean public HTTPS endpoint (no explicit :port
                # suffix), i.e. served over standard ports 80/443, e.g.
                # https://<id>-<port>.<cluster>.devtunnels.ms
                no_suffix = [u for u in cands if not re.search(r":\d+$", u)]
                for u in no_suffix:
                    if f"-{port}." in u:
                        return u
                if no_suffix:
                    return no_suffix[0]
                return cands[0]

            def _reader() -> None:
                assert proc.stdout
                found: list[str] = []
                # NB: use readline() (not `for line in proc.stdout`) — the
                # latter read-ahead-buffers ~8KB and would never yield lines
                # for a long-running, low-output process like `devtunnel host`.
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    for raw in _URL_RE.findall(line):
                        u = raw.rstrip(".,;)")
                        if u and u not in found:
                            found.append(u)
                    if found:
                        tunnel.url = _select_url(found)
                        tunnel.message = "Tunnel actif."
                tunnel.hosting = False
                if not tunnel.message.startswith("Tunnel actif"):
                    tunnel.message = "L'hébergement s'est arrêté."

            threading.Thread(target=_reader, daemon=True).start()

        # Give the host process a moment to emit the URL.
        import time as _time
        for _ in range(60):  # up to ~6s
            if tunnel.url:
                break
            _time.sleep(0.1)
        return {"ok": True, "tunnel": tunnel.as_dict(), "message": tunnel.message}

    def stop_tunnel(self, name: str) -> dict:
        """Stop hosting a tunnel without deleting it."""
        with self._lock:
            proc = self._procs.pop(name, None)
            if proc:
                proc.terminate()
            t = self._tunnels.get(name)
            if t:
                t.hosting = False
                t.url = ""
                t.message = "Hébergement arrêté."
        return {"ok": True}

    def delete_tunnel(self, name: str) -> dict:
        """Stop hosting (if any) and delete the tunnel from the account."""
        cli = self._cli()
        if not cli:
            return {"ok": False, "message": "devtunnel CLI introuvable."}
        with self._lock:
            proc = self._procs.pop(name, None)
            if proc:
                proc.terminate()
            self._tunnels.pop(name, None)
        try:
            res = subprocess.run([cli, "delete", name], capture_output=True,
                                 text=True, timeout=30)
            out = (res.stdout + res.stderr).strip()
            ok = res.returncode == 0 or "not found" in out.lower()
            return {"ok": ok, "message": out[:200]}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}


devtunnel_manager = DevTunnelManager()
