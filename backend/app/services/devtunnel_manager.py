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
import uuid
from dataclasses import dataclass

from app.config import settings  # noqa: F401  (kept for default ports usage)


def _new_devtunnel_name() -> str:
    """Return a brand-new unique devtunnel name (GUID-based).

    devtunnel tunnel IDs must be 3-60 chars of lowercase letters, digits and
    hyphens. A uuid4 hex prefixed with a letter satisfies those constraints and
    guarantees a fresh, collision-free tunnel for every new creation.
    """
    return f"t{uuid.uuid4().hex}"

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
    log: str = ""
    # Actual devtunnel tunnel name used for every CLI call (a fresh GUID per
    # creation). ``name`` stays the human-readable logical name for the UI.
    devtunnel_name: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "port": self.port,
            "protocol": self.protocol,
            "url": self.url,
            "tunnel_id": self.tunnel_id,
            "hosting": self.hosting,
            "message": self.message,
            "log": self.log,
            "devtunnel_name": self.devtunnel_name,
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

    def logout_github(self) -> LoginState:
        """Log the current GitHub account out of devtunnel."""
        cli = self._cli()
        if not cli:
            self.login.message = "devtunnel CLI introuvable."
            return self.login
        try:
            subprocess.run([cli, "user", "logout"], capture_output=True,
                           text=True, timeout=15)
        except Exception as exc:
            self.login.message = str(exc)
        self.login = LoginState()
        self.login_status()
        return self.login

    # ------------------------------------------------------------------
    # Tunnel lifecycle
    # ------------------------------------------------------------------
    def list_tunnels(self) -> list[dict]:
        """Return every configured tunnel (from `devtunnel list`), merged with
        any live hosting state tracked in this process.

        Remote tunnels are named with an opaque GUID; we relabel them with their
        human-readable logical name whenever we still know the mapping in this
        process."""
        cli = self._cli()
        # Reverse map: devtunnel GUID name -> logical name (this process only).
        dt_to_logical = {
            t.devtunnel_name: lname
            for lname, t in self._tunnels.items() if t.devtunnel_name
        }
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
                    dt_name = tunnel_id.split(".")[0]
                    # Relabel with the logical name when known; otherwise keep
                    # the raw GUID (orphan from a previous run).
                    name = dt_to_logical.get(dt_name, dt_name)
                    configured[name] = {
                        "name": name, "tunnel_id": tunnel_id,
                        "devtunnel_name": dt_name,
                    }
            except Exception:
                pass

        # Merge: start from configured, overlay in-memory live state.
        result: dict[str, dict] = {}
        for name, info in configured.items():
            result[name] = {
                "name": name,
                "tunnel_id": info.get("tunnel_id", ""),
                "devtunnel_name": info.get("devtunnel_name", ""),
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
        tunnel, parsing the dynamically generated public URL.

        Identical flow for every tunnel (dashboard, mcp, …). If a pre-existing
        tunnel is in a corrupt/stale state (host fails with "not found"), it is
        automatically deleted and recreated from scratch so the behaviour stays
        the same as a freshly created tunnel.
        """
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

            # Fresh GUID for every new creation; drop the previous remote tunnel
            # (old GUID) so we never reuse a stale/corrupt one.
            self._delete_previous(cli, name)
            tunnel = Tunnel(name=name, port=port, protocol=protocol,
                            devtunnel_name=_new_devtunnel_name(),
                            message="Création du tunnel…")
            self._tunnels[name] = tunnel

            ok, msg = self._provision(cli, tunnel, force_fresh=False)
            if not ok:
                tunnel.message = msg
                return {"ok": False, "tunnel": tunnel.as_dict(), "message": msg}
            proc = self._start_host(cli, tunnel)

        # Wait (outside the lock) for the host process to emit the URL.
        if not (self._await_url(tunnel, proc) and self._confirm_hosting(tunnel, proc)):
            # The host process died (no URL, or it collapsed right after
            # emitting one) → stale/corrupt tunnel. Recover by recreating it
            # from scratch, exactly like a new one.
            with self._lock:
                tunnel.message = "Réinitialisation du tunnel…"
                ok, msg = self._provision(cli, tunnel, force_fresh=True)
                if not ok:
                    tunnel.message = msg
                    return {"ok": False, "tunnel": tunnel.as_dict(),
                            "message": msg}
                proc = self._start_host(cli, tunnel)
            self._await_url(tunnel, proc) and self._confirm_hosting(tunnel, proc)

        return {"ok": True, "tunnel": tunnel.as_dict(), "message": tunnel.message}

    def create_tunnel_stream(self, name: str, port: int,
                             protocol: str = "http"):
        """Generator yielding progress events while creating/hosting a tunnel.

        Mirrors :meth:`create_tunnel` but emits a progress event between each
        devtunnel command, pausing 4s between commands so the UI can display a
        step-by-step progress bar.

        Each event is a dict::

            {"progress": int 0-100, "message": str, "step": str,
             "done": bool, "ok": bool, "tunnel": dict | None}
        """
        import time

        PAUSE = 4

        def ev(progress, message, step="", done=False, ok=True, tunnel=None):
            return {
                "progress": progress, "message": message, "step": step,
                "done": done, "ok": ok,
                "tunnel": tunnel.as_dict() if tunnel else None,
            }

        cli = self._cli()
        if not cli:
            yield ev(100, "devtunnel CLI introuvable.", done=True, ok=False)
            return

        name = (name or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            yield ev(100, "Nom invalide (minuscules, chiffres, tirets).",
                     done=True, ok=False)
            return

        with self._lock:
            existing_proc = self._procs.get(name)
            if existing_proc and existing_proc.poll() is None:
                yield ev(100, "Tunnel déjà en cours d'hébergement.",
                         step="done", done=True, ok=True,
                         tunnel=self._tunnels[name])
                return
            # Fresh GUID for every new creation; drop the previous remote tunnel
            # (old GUID) so we never reuse a stale/corrupt one.
            self._delete_previous(cli, name)
            tunnel = Tunnel(name=name, port=port, protocol=protocol,
                            devtunnel_name=_new_devtunnel_name(),
                            message="Création du tunnel…")
            self._tunnels[name] = tunnel

        # Step 1/3 — create / verify the tunnel
        yield ev(5, "Étape 1/3 · Création du tunnel…", step="create")
        with self._lock:
            ok, msg = self._ensure_exists(cli, tunnel, force_fresh=False)
        if not ok:
            tunnel.message = msg
            yield ev(100, msg, step="create", done=True, ok=False, tunnel=tunnel)
            return
        yield ev(33, "Tunnel créé · pause 4s…", step="create")
        time.sleep(PAUSE)

        # Step 2/3 — configure the port
        yield ev(40, "Étape 2/3 · Configuration du port…", step="port")
        with self._lock:
            ok, msg = self._ensure_port(cli, tunnel)
        if not ok:
            tunnel.message = msg
            yield ev(100, msg, step="port", done=True, ok=False, tunnel=tunnel)
            return
        yield ev(66, "Port configuré · pause 4s…", step="port")
        time.sleep(PAUSE)

        # Step 3/3 — start hosting and resolve the public URL
        yield ev(75, "Étape 3/3 · Démarrage de l'hébergement…", step="host")
        with self._lock:
            proc = self._start_host(cli, tunnel)
        # The host is considered ready only when it both emits a public URL and
        # keeps running through the stabilisation window. A tunnel that prints
        # its URL then dies a moment later is stale/corrupt → reinit once.
        ready = self._await_url(tunnel, proc) and self._confirm_hosting(tunnel, proc)
        if not ready:
            yield ev(80, "Réinitialisation du tunnel…", step="host")
            with self._lock:
                ok, msg = self._provision(cli, tunnel, force_fresh=True)
                if not ok:
                    tunnel.message = msg
                    yield ev(100, msg, step="host", done=True, ok=False,
                             tunnel=tunnel)
                    return
                proc = self._start_host(cli, tunnel)
            self._await_url(tunnel, proc) and self._confirm_hosting(tunnel, proc)

        ok = bool(tunnel.url) and proc.poll() is None
        if ok:
            final_msg = tunnel.message
        else:
            # Surface the full devtunnel output so the user can diagnose.
            detail = (tunnel.log or "").strip()
            final_msg = "Impossible de récupérer l'URL."
            if detail:
                final_msg += "\n\nSortie devtunnel host :\n" + detail
        yield ev(100, final_msg, step="done", done=True, ok=ok, tunnel=tunnel)

    def _delete_previous(self, cli: str, name: str) -> None:
        """Delete the remote devtunnel previously created for ``name`` (its old
        GUID) so each new creation starts from a clean, collision-free tunnel.

        Must be called while holding ``self._lock``."""
        prev = self._tunnels.get(name)
        if not prev or not prev.devtunnel_name:
            return
        proc = self._procs.pop(name, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            subprocess.run([cli, "delete", prev.devtunnel_name, "-f"],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    def _provision(self, cli: str, tunnel: "Tunnel",
                   force_fresh: bool) -> tuple[bool, str]:
        """Ensure the tunnel exists and has the port configured.

        When ``force_fresh`` is True the tunnel is deleted first so it is
        recreated cleanly (clears any corrupt server/cache state)."""
        ok, msg = self._ensure_exists(cli, tunnel, force_fresh)
        if not ok:
            return ok, msg
        return self._ensure_port(cli, tunnel)

    def _ensure_exists(self, cli: str, tunnel: "Tunnel",
                       force_fresh: bool) -> tuple[bool, str]:
        """Create the tunnel if it does not already exist."""
        name = tunnel.devtunnel_name

        if force_fresh:
            subprocess.run([cli, "delete", name, "-f"],
                           capture_output=True, text=True, timeout=30)
            tunnel.url = ""

        # Does the tunnel already exist? `devtunnel show <name>` resolves by
        # bare name. We must NOT call `create` on an existing tunnel: a
        # conflicting `create` corrupts default-tunnel resolution and makes the
        # subsequent `port create`/`host` fail with "Tunnel not found".
        exists = False
        if not force_fresh:
            show = subprocess.run([cli, "show", name], capture_output=True,
                                  text=True, timeout=30)
            show_out = show.stdout + show.stderr
            exists = show.returncode == 0 and "tunnel id" in show_out.lower()
            if exists:
                id_m = _TUNNEL_ID_RE.search(show_out)
                if id_m:
                    tunnel.tunnel_id = id_m.group(1)

        if not exists:
            # devtunnel create <name> --allow-anonymous
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
                return False, f"Échec création : {create_out.strip()[:200]}"
        return True, "Tunnel créé."

    def _ensure_port(self, cli: str, tunnel: "Tunnel") -> tuple[bool, str]:
        """Configure the forwarded port on the tunnel (idempotent).

        IMPORTANT: never run `port create` if the port already exists. devtunnel
        would add a DUPLICATE port entry, after which `devtunnel host` aborts
        with "An item with the same key has already been added. Key: host".
        """
        name, port, protocol = tunnel.devtunnel_name, tunnel.port, tunnel.protocol

        # Is the port already configured? `devtunnel port list <name>` lists
        # the existing ports; skip creation if our port is already present.
        listing = subprocess.run(
            [cli, "port", "list", name], capture_output=True, text=True,
            timeout=30,
        )
        list_out = listing.stdout + listing.stderr
        already = bool(re.search(rf"\b{port}\b", list_out)) if listing.returncode == 0 else False
        if already:
            return True, "Tunnel prêt (port déjà configuré)."

        # devtunnel port create <name> -p <port> --protocol http
        port_res = subprocess.run(
            [cli, "port", "create", name, "-p", str(port),
             "--protocol", protocol],
            capture_output=True, text=True, timeout=30,
        )
        port_out = port_res.stdout + port_res.stderr
        low_port = port_out.lower()
        port_exists = (
            "already exists" in low_port
            or "conflict with existing" in low_port
            or "port number conflicts" in low_port
        )
        if port_res.returncode != 0 and not port_exists:
            return False, f"Échec port : {port_out.strip()[:200]}"
        return True, "Tunnel prêt."

    def _start_host(self, cli: str, tunnel: "Tunnel") -> subprocess.Popen:
        """Start `devtunnel host <name>` and parse the public URL in a thread."""
        name, port = tunnel.name, tunnel.port
        dt_name = tunnel.devtunnel_name

        # Kill any host process still running for this tunnel before starting a
        # new one. Two concurrent `devtunnel host <name>` for the same tunnel
        # make the CLI abort with "An item with the same key has already been
        # added. Key: host" (duplicate host registration). This happens during
        # the force_fresh recovery path when the first host is slow to emit an
        # URL but has not exited.
        old = self._procs.pop(name, None)
        if old and old.poll() is None:
            old.terminate()
            try:
                old.wait(timeout=5)
            except subprocess.TimeoutExpired:
                old.kill()

        proc = subprocess.Popen(
            [cli, "host", dt_name],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self._procs[name] = proc
        tunnel.hosting = True
        tunnel.url = ""
        tunnel.log = ""
        tunnel.message = "Hébergement en cours, récupération de l'URL…"

        def _select_url(found: list[str]) -> str:
            # Drop the "inspect network activity" URLs.
            cands = [u for u in found if "inspect" not in u] or found
            # Prefer the clean public HTTPS endpoint (no explicit :port suffix),
            # i.e. served over standard ports 80/443, e.g.
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
            # NB: use readline() (not `for line in proc.stdout`) — the latter
            # read-ahead-buffers ~8KB and would never yield lines for a
            # long-running, low-output process like `devtunnel host`.
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                # Keep the full devtunnel output (capped) to surface on errors.
                tunnel.log = (tunnel.log + line)[-4000:]
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
        return proc

    @staticmethod
    def _await_url(tunnel: "Tunnel", proc: subprocess.Popen,
                   timeout: float = 30.0) -> bool:
        """Wait up to ``timeout`` seconds for the public URL.

        Returns False only if the host process exited without producing one
        (signalling a stale/corrupt tunnel that warrants a reinit). A slow but
        still-running host process is given the full timeout window so a healthy
        tunnel is not needlessly torn down and recreated."""
        import time as _time
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            if tunnel.url:
                return True
            if proc.poll() is not None:
                # Host process exited before emitting an URL.
                return False
            _time.sleep(0.1)
        return bool(tunnel.url)

    @staticmethod
    def _confirm_hosting(tunnel: "Tunnel", proc: subprocess.Popen,
                         grace: float = 30.0) -> bool:
        """Confirm the host stays alive after the URL was captured.

        ``devtunnel host`` sometimes prints the public URL and then dies a
        moment later (stale/corrupt tunnel). Returns True only if the host
        process is still running at the end of the ``grace`` window, so a tunnel
        that collapses right after emitting its URL is treated as a failure and
        can be reinitialised instead of being reported as active."""
        import time as _time
        deadline = _time.monotonic() + grace
        while _time.monotonic() < deadline:
            if proc.poll() is not None:
                # Host exited shortly after emitting the URL → not stable.
                return False
            _time.sleep(0.2)
        return proc.poll() is None


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
            t = self._tunnels.pop(name, None)
            # Resolve to the real devtunnel (GUID) name when we know it; fall
            # back to the provided name (e.g. an orphan listed by its GUID).
            target = t.devtunnel_name if t and t.devtunnel_name else name
        try:
            res = subprocess.run([cli, "delete", target], capture_output=True,
                                 text=True, timeout=30)
            out = (res.stdout + res.stderr).strip()
            ok = res.returncode == 0 or "not found" in out.lower()
            return {"ok": ok, "message": out[:200]}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}


devtunnel_manager = DevTunnelManager()
