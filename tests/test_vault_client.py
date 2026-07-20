import pytest

from src.vault_client import BotCityVaultProvider, VaultClient, VaultCredentialError


class Provider:
    def __init__(self, credential):
        self.credential = credential

    def get_credential(self, label):
        self.label = label
        return self.credential


def test_vault_client_recovers_erp_credential_from_credencial_erp():
    provider = Provider({"username": "rebecca.erp", "password": "segredo"})

    credential = VaultClient(provider).get_erp_credential()

    assert provider.label == "credencial_erp"
    assert credential.username == "rebecca.erp"
    assert credential.password == "segredo"


def test_vault_client_requires_username_and_password():
    with pytest.raises(VaultCredentialError):
        VaultClient(Provider({"username": "rebecca.erp"})).get_erp_credential()


def test_botcity_vault_provider_adapta_credencial_do_sdk():
    class Sdk:
        def __init__(self):
            self.calls = []

        def get_credential(self, label, key):
            self.calls.append((label, key))
            values = {"username": "marcelo.erp", "password": "segredo"}
            return values[key]

    sdk = Sdk()

    credential = BotCityVaultProvider(sdk).get_credential("credencial_erp")

    assert sdk.calls == [
        ("credencial_erp", "username"),
        ("credencial_erp", "password"),
    ]
    assert credential == {"username": "marcelo.erp", "password": "segredo"}
