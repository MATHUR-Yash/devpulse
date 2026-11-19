"""Session-bound GitHub App authorization for the single-worker deployment."""

import base64
import hashlib
import os
import secrets
from threading import Lock
from time import monotonic
from urllib.parse import urlencode

import httpx2
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from ..auth import COOKIE, token_hash


class GitHubSessions:
    """Short-lived credentials stay in memory and expire on restart or logout."""

    def __init__(self):
        self.pending = {}
        self.grants = {}
        self.lock = Lock()

    def _prune(self):
        for entries in (self.pending, self.grants):
            for key in [k for k, record in entries.items() if record[0] <= monotonic()]:
                del entries[key]

    def begin(self, session):
        client_id, _, callback = settings()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        with self.lock:
            self._prune()
            self.pending[session] = (monotonic() + 600, state, verifier)
        params = urlencode(dict(client_id=client_id, redirect_uri=callback, state=state,
                                code_challenge=challenge, code_challenge_method="S256"))
        return RedirectResponse("https://github.com/login/oauth/authorize?" + params)

    def finish(self, session, code, state):
        client_id, secret, callback = settings()
        with self.lock:
            self._prune()
            pending = self.pending.get(session)
            if not pending or not secrets.compare_digest(pending[1].encode(), state.encode()):
                raise HTTPException(403, "GitHub authorization expired. Connect again.")
            del self.pending[session]
        try:
            response = httpx2.post("https://github.com/login/oauth/access_token", timeout=10,
                                   headers={"Accept": "application/json"},
                                   data=dict(client_id=client_id, client_secret=secret, code=code,
                                             redirect_uri=callback, code_verifier=pending[2]))
            response.raise_for_status()
            grant = response.json()
            token = grant["access_token"]
            lifetime = min(28800, int(grant.get("expires_in", 28800)))
        except (httpx2.HTTPError, ValueError, KeyError):
            raise HTTPException(403, "GitHub authorization failed. Connect again.") from None
        with self.lock:
            self.grants[session] = (monotonic() + lifetime, token)
        return RedirectResponse("/", status_code=303)

    def token(self, session):
        with self.lock:
            self._prune()
            grant = self.grants.get(session)
            return grant[1] if grant else None

    def forget(self, session):
        with self.lock:
            self.grants.pop(session, None)
            self.pending.pop(session, None)


def settings():
    values = tuple(os.getenv("DEVPULSE_GITHUB_" + key) for key in ("CLIENT_ID", "CLIENT_SECRET", "CALLBACK_URL"))
    if not all(values):
        raise HTTPException(503, "GitHub App authorization has not been configured on this server.")
    return values


def session_id(request: Request):
    return token_hash(request.cookies[COOKIE])
