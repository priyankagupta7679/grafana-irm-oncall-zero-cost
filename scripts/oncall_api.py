"""Tiny client for the Grafana IRM (OnCall) public API.

Credentials are read from environment variables or a local .env file
(git-ignored). Nothing secret is ever hard-coded in this repo.
"""
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=REPO_ROOT / ".env"):
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name):
    value = os.environ.get(name, "")
    if not value or "replace-me" in value or "REGION" in value:
        sys.exit(f"ERROR: set {name} in your .env (see .env.example)")
    return value


class OnCall:
    def __init__(self):
        load_dotenv()
        base = require_env("ONCALL_API_URL").rstrip("/")
        if not base.endswith("/api/v1"):
            base = base + "/api/v1"
        self.base = base
        self.session = requests.Session()
        # IRM expects the raw token, no "Bearer" prefix
        self.session.headers.update({
            "Authorization": require_env("ONCALL_API_TOKEN"),
            "Content-Type": "application/json",
        })

    def _url(self, path):
        return path if path.startswith("http") else f"{self.base}/{path.strip('/')}/"

    def request(self, method, path, **kwargs):
        resp = self.session.request(method, self._url(path), timeout=30, **kwargs)
        if resp.status_code >= 400:
            sys.exit(f"ERROR {method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json() if resp.content else {}

    def get(self, path, **params):
        return self.request("GET", path, params=params)

    def post(self, path, body):
        return self.request("POST", path, json=body)

    def put(self, path, body):
        return self.request("PUT", path, json=body)

    def list_all(self, path, **params):
        """Follow pagination and return every result."""
        page = self.get(path, **params)
        items = list(page.get("results", []))
        while page.get("next"):
            page = self.request("GET", page["next"])
            items.extend(page.get("results", []))
        return items

    def find_by_name(self, path, name, **params):
        for item in self.list_all(path, **params):
            if item.get("name") == name:
                return item
        return None

    def user_id_by_email(self, email):
        users = self.list_all("users", email=email)
        if not users:
            sys.exit(f"ERROR: no Grafana user with email {email}. "
                     "Invite them first (see docs/UI-SETUP.md).")
        return users[0]["id"]
