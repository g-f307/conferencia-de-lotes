"""Configuração central do bot carregada por variáveis de ambiente."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


TRUE_VALUES = {"1", "true", "yes", "sim", "on"}


def as_bool(value: str | None, default: bool = False) -> bool:
    """Converte uma variável textual em booleano de forma previsível."""
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class Settings:
    """Valores não sigilosos e credenciais técnicas do Maestro.

    A senha do ERP não pertence a esta classe: ela deve vir do Credentials
    Vault em tempo de execução, sob responsabilidade do módulo de Vault.
    """

    base_dir: Path
    maestro_enabled: bool
    vault_enabled: bool
    maestro_server: str
    maestro_login: str
    maestro_key: str
    maestro_task_id: str
    datapool_label: str
    vault_label: str
    input_dir: Path
    log_file: Path
    report_dir: Path

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "Settings":
        """Carrega `.env` e resolve caminhos relativos a partir do projeto."""
        root = (base_dir or Path(__file__).resolve().parents[1]).resolve()
        load_dotenv(root / ".env")

        def project_path(variable: str, default: str) -> Path:
            configured = Path(os.getenv(variable, default)).expanduser()
            if configured.is_absolute():
                return configured
            return (root / configured).resolve()

        return cls(
            base_dir=root,
            maestro_enabled=as_bool(os.getenv("MAESTRO_ENABLED")),
            vault_enabled=as_bool(os.getenv("VAULT_ENABLED")),
            maestro_server=os.getenv("MAESTRO_SERVER", "").strip(),
            maestro_login=os.getenv("MAESTRO_LOGIN", "").strip(),
            maestro_key=os.getenv("MAESTRO_KEY", "").strip(),
            maestro_task_id=os.getenv("MAESTRO_TASK_ID", "").strip(),
            datapool_label=os.getenv(
                "DATAPOOL_LABEL", "FilaAuditoriaLotes"
            ).strip(),
            vault_label=os.getenv("VAULT_LABEL", "credencial_erp").strip(),
            input_dir=project_path("INPUT_DIR", "dados_entrada"),
            log_file=project_path("LOG_FILE", "logs/execucao.log"),
            report_dir=project_path("REPORT_DIR", "relatorios"),
        )

    def validate(self) -> None:
        """Valida apenas os valores necessários quando o Maestro está ativo."""
        if not self.maestro_enabled:
            return

        required = {
            "MAESTRO_SERVER": self.maestro_server,
            "MAESTRO_LOGIN": self.maestro_login,
            "MAESTRO_KEY": self.maestro_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Configuração obrigatória ausente: " + ", ".join(missing)
            )
        if not self.vault_enabled:
            raise ValueError(
                "VAULT_ENABLED deve ser true quando MAESTRO_ENABLED=true"
            )
