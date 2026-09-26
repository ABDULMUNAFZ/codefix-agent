"""Minimal TrueForge REST client for the endpoints CodeFix setup uses."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class TrueForgeError(RuntimeError):
    def __init__(self, *, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:500]}")
        self.status = status


@dataclass(frozen=True)
class TrueForgeClient:
    base_url: str
    api_token: str | None = None
    timeout: float = 30.0

    def request(self, method: str, path: str, body: Any = None) -> Any:
        url = self.base_url.rstrip("/") + path
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.api_token:
            req.add_header("Authorization", f"Bearer {self.api_token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as exc:
            raise TrueForgeError(method=method, path=path, status=exc.code, body=exc.read().decode(errors="replace")) from exc
        except urllib.error.URLError as exc:
            raise TrueForgeError(method=method, path=path, status=0, body=str(exc.reason)) from exc
        return json.loads(raw) if raw else None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, body)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, body)
