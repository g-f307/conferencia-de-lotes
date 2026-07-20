from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol


LOGGER = logging.getLogger(__name__)
DEFAULT_CREDENTIAL_LABEL = "credencial_erp"


class CredentialProvider(Protocol):
    def get_credential(self, label: str) -> dict[str, str]:
        raise NotImplementedError


@dataclass(frozen=True)
class ErpCredential:
    username: str
    password: str


class VaultCredentialError(RuntimeError):
    pass


class VaultClient:
    def __init__(
        self,
        provider: CredentialProvider,
        credential_label: str = DEFAULT_CREDENTIAL_LABEL,
    ) -> None:
        self.provider = provider
        self.credential_label = credential_label

    def get_erp_credential(self) -> ErpCredential:
        credential = self.provider.get_credential(self.credential_label)
        username = str(credential.get("username") or "").strip()
        password = str(credential.get("password") or "")

        if not username or not password:
            raise VaultCredentialError("credencial_erp deve conter username e password")

        LOGGER.info("Credencial ERP recuperada para usuario %s", username)
        return ErpCredential(username=username, password=password)
