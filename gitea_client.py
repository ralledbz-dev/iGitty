from __future__ import annotations

import os
import re
from typing import Any

import requests

GITEA_BASE_URL = "http://127.0.0.1:3000"
GITEA_TOKEN_ENV = "DBZS_HOME_API_TOKEN"
_REQUEST_TIMEOUT = (3.05, 15)
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


class GiteaError(RuntimeError):
    """A safe, user-facing Gitea error."""


def validate_gitea_name(value: str) -> str:
    """Return a safe Gitea owner or repository name."""
    if not isinstance(value, str):
        raise ValueError("Der Gitea-Name muss eine Zeichenkette sein.")
    value = value.strip()
    if value in {".", ".."} or not _NAME_PATTERN.fullmatch(value):
        raise ValueError(
            "Der Gitea-Name darf nur Buchstaben, Zahlen, Punkt, Bindestrich "
            "und Unterstrich enthalten und höchstens 100 Zeichen lang sein."
        )
    return value


class GiteaClient:
    """Small, non-redirecting Gitea REST client for local mirror management."""

    def __init__(self, token: str):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Ein Gitea-Token ist erforderlich.")
        self._token = token.strip()
        self._session = requests.Session()
        self._session.trust_env = False
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"token {self._token}",
            "User-Agent": "iGitty-local-gitea-mirror",
        }

    @classmethod
    def from_environment(cls) -> "GiteaClient":
        token = os.environ.get(GITEA_TOKEN_ENV, "")
        if not token.strip():
            raise GiteaError(
                f"Kein Gitea-Token in der Umgebungsvariable {GITEA_TOKEN_ENV} gefunden."
            )
        return cls(token)

    def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> requests.Response:
        try:
            return self._session.request(
                method,
                f"{GITEA_BASE_URL}{path}",
                headers=self._headers,
                json=json,
                timeout=(3.05, 600) if method == "POST" else _REQUEST_TIMEOUT,
                allow_redirects=False,
            )
        except requests.Timeout:
            if method == "POST":
                raise GiteaError(
                    "Die Migration ist möglicherweise bereits gestartet; "
                    "der Ausgang ist unklar. Bitte Gitea prüfen, bevor erneut versucht wird."
                ) from None
            raise GiteaError(
                "Zeitüberschreitung bei der Verbindung mit Gitea."
            ) from None
        except requests.RequestException:
            if method == "POST":
                raise GiteaError(
                    "Die Migration konnte nicht eindeutig abgeschlossen werden; "
                    "der Ausgang ist unklar. Bitte Gitea prüfen, bevor erneut versucht wird."
                ) from None
            raise GiteaError("Gitea konnte nicht erreicht werden.") from None

    @staticmethod
    def _status_error(response: requests.Response, action: str) -> GiteaError:
        status = response.status_code
        if status in {401, 403}:
            return GiteaError(
                "Gitea hat die Authentifizierung oder Berechtigung abgelehnt."
            )
        if status == 409:
            return GiteaError(
                "Gitea meldet einen Konflikt; das Repository existiert möglicherweise bereits."
            )
        if status == 422:
            return GiteaError(
                f"Gitea konnte {action} wegen ungültiger Angaben nicht ausführen."
            )
        return GiteaError(f"Gitea konnte {action} nicht ausführen (HTTP {status}).")

    def get_user(self) -> dict[str, Any]:
        response = self._request("GET", "/api/v1/user")
        if not 200 <= response.status_code < 300:
            raise self._status_error(response, "den Benutzerabruf")
        try:
            data = response.json()
        except (ValueError, requests.RequestException):
            raise GiteaError("Gitea lieferte eine ungültige Benutzerantwort.") from None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("login"), str)
            or not data["login"].strip()
        ):
            raise GiteaError("Gitea lieferte keine gültige Benutzerantwort.")
        return data

    def get_repository(self, owner: str, name: str) -> dict[str, Any] | None:
        owner = validate_gitea_name(owner)
        name = validate_gitea_name(name)
        response = self._request("GET", f"/api/v1/repos/{owner}/{name}")
        if response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise self._status_error(response, "den Repositoryabruf")
        try:
            data = response.json()
        except (ValueError, requests.RequestException):
            raise GiteaError(
                "Gitea lieferte eine ungültige Repositoryantwort."
            ) from None
        if not isinstance(data, dict):
            raise GiteaError("Gitea lieferte eine ungültige Repositoryantwort.")
        return data

    def create_mirror(
        self,
        source_repo: dict[str, Any],
        target_owner: str,
        target_name: str,
        private: bool = True,
        github_token: str | None = None,
    ) -> dict[str, Any]:
        target_owner = validate_gitea_name(target_owner)
        target_name = validate_gitea_name(target_name)
        if not isinstance(source_repo, dict):
            raise ValueError("Das Quell-Repository ist ungültig.")
        source_owner = source_repo.get("owner")
        if not isinstance(source_owner, dict):
            raise ValueError("Das Quell-Repository enthält keinen gültigen Besitzer.")
        source_owner_name = validate_gitea_name(source_owner.get("login", ""))
        source_name = validate_gitea_name(source_repo.get("name", ""))
        source_private = source_repo.get("private") is True
        if source_private and not private:
            raise ValueError(
                "Ein privates Quell-Repository muss privat gespiegelt werden."
            )
        if source_private and (
            not isinstance(github_token, str) or not github_token.strip()
        ):
            raise ValueError(
                "Für ein privates Quell-Repository ist ein GitHub-Token erforderlich."
            )
        existing = self.get_repository(target_owner, target_name)
        if existing is not None:
            raise GiteaError(
                "Das Ziel-Repository existiert bereits; es wird nichts überschrieben."
            )

        payload: dict[str, Any] = {
            "clone_addr": f"https://github.com/{source_owner_name}/{source_name}.git",
            "service": "git",
            "mirror": True,
            "repo_owner": target_owner,
            "repo_name": target_name,
            "private": private,
            "description": source_repo.get("description") or "",
        }
        if isinstance(github_token, str) and github_token.strip():
            payload["auth_username"] = "x-access-token"
            payload["auth_password"] = github_token.strip()

        response = self._request("POST", "/api/v1/repos/migrate", json=payload)
        if not 200 <= response.status_code < 300:
            raise self._status_error(response, "die Migration")
        try:
            data = response.json()
        except (ValueError, requests.RequestException):
            raise GiteaError(
                "Gitea lieferte keine gültige Migrationsantwort."
            ) from None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("name"), str)
            or data["name"].casefold() != target_name.casefold()
            or data.get("mirror") is not True
            or not isinstance(data.get("owner"), dict)
            or not isinstance(data["owner"].get("login"), str)
            or data["owner"]["login"].casefold() != target_owner.casefold()
        ):
            raise GiteaError(
                "Gitea lieferte eine unvollständige Migrationsantwort. "
                "Bitte das Ziel in Gitea prüfen, bevor erneut gestartet wird."
            )
        return data
