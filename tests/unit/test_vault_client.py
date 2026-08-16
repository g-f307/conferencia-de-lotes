import pytest

from src.vault_client import BotCityVaultProvider, VaultClient, VaultCredentialError


pytestmark = pytest.mark.unit


class Provider:
    def __init__(self, credential):
        self.credential = credential

    def get_credential(self, label):
        self.label = label
        return self.credential


def test_vault_client_recovers_erp_credential_from_credencial_erp2():
    provider = Provider({"username": "rebecca.erp", "password": "segredo"})

    credential = VaultClient(provider).get_erp_credential()

    assert provider.label == "credencial_erp2"
    assert credential.username == "rebecca.erp"
    assert credential.password == "segredo"
    assert "segredo" not in repr(credential)


def test_vault_client_requires_username_and_password():
    with pytest.raises(VaultCredentialError):
        VaultClient(Provider({"username": "rebecca.erp"})).get_erp_credential()


def test_vault_client_cacheia_credencial_recuperada():
    provider = Provider({"username": "rebecca.erp", "password": "segredo"})
    client = VaultClient(provider)

    assert client.get_erp_credential() is client.get_erp_credential()


def test_botcity_vault_provider_adapta_credencial_do_sdk():
    class Sdk:
        def __init__(self):
            self.calls = []

        def get_credential(self, label, key):
            self.calls.append((label, key))
            values = {"username": "marcelo.erp", "password": "segredo"}
            return values[key]

    sdk = Sdk()

    credential = BotCityVaultProvider(sdk).get_credential("credencial_erp2")

    assert sdk.calls == [
        ("credencial_erp2", "username"),
        ("credencial_erp2", "password"),
    ]
    assert credential == {"username": "marcelo.erp", "password": "segredo"}


def test_botcity_vault_provider_informa_chave_obrigatoria_ausente():
    class Sdk:
        def get_credential(self, label, key):
            raise ValueError("Key not found")

    with pytest.raises(
        VaultCredentialError,
        match="Credencial credencial_erp2 nao contem a chave obrigatoria username",
    ):
        BotCityVaultProvider(Sdk()).get_credential("credencial_erp2")
