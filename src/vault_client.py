from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from src.logging_config import LOGGER_NAME


LOGGER = logging.getLogger(LOGGER_NAME)
DEFAULT_CREDENTIAL_LABEL = "credencial_erp2"


class CredentialProvider(Protocol):
    def get_credential(self, label: str) -> dict[str, str]:
        raise NotImplementedError


@dataclass(frozen=True)
class ErpCredential:
    username: str
    password: str


class VaultCredentialError(RuntimeError):
    pass


class BotCityVaultProvider:
    """Provider real apoiado no SDK do BotCity Maestro."""

    def __init__(self, sdk: Any) -> None:
        self.sdk = sdk

    def get_credential(self, label: str) -> dict[str, str]:
        return {
            "username": self._get_required_key(label, "username"),
            "password": self._get_required_key(label, "password"),
        }

    def _get_required_key(self, label: str, key: str) -> str:
        try:
            return str(self.sdk.get_credential(label=label, key=key) or "")
        except AttributeError as exc:
            raise VaultCredentialError(
                "SDK do Maestro nao expoe get_credential para acessar o Vault"
            ) from exc
        except Exception as exc:
            raise VaultCredentialError(
                f"Credencial {label} nao contem a chave obrigatoria {key}"
            ) from exc


class VaultClient:
    def __init__(
        self,
        provider: CredentialProvider,
        credential_label: str = DEFAULT_CREDENTIAL_LABEL,
    ) -> None:
        self.provider = provider
        self.credential_label = credential_label
        self._cached_credential: ErpCredential | None = None

    def get_erp_credential(self) -> ErpCredential:
        if self._cached_credential is not None:
            return self._cached_credential

        credential = self.provider.get_credential(self.credential_label)
        username = str(credential.get("username") or "").strip()
        password = str(credential.get("password") or "")

        if not username or not password:
            raise VaultCredentialError(
                f"{self.credential_label} deve conter username e password"
            )

        LOGGER.info(
            "Credencial ERP recuperada para usuario %s",
            username,
            extra={
                "evento": "RECUPERACAO_CREDENCIAL",
                "formulario": "Vault",
                "status": "SUCCESS",
                "usuario": username,
            },
        )
        self._cached_credential = ErpCredential(username=username, password=password)
        return self._cached_credential
