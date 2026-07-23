"""Configuração central do bot carregada por variáveis de ambiente."""

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


TRUE_VALUES = {"1", "true", "yes", "sim", "on"}


def as_bool(value: str | None, default: bool = False) -> bool:
    """Converte uma variável textual em booleano de forma previsível."""
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def botcity_runner_args(argv: list[str] | None = None) -> tuple[str, str]:
    """Extrai server e task_id quando o BotCity Runner chama bot.py."""
    current_argv = argv if argv is not None else sys.argv
    if len(current_argv) < 3:
        return "", ""

    server = current_argv[1].strip()
    task_id = current_argv[2].strip()
    if not server.startswith(("http://", "https://")) or not task_id:
        return "", ""
    return server, task_id


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
    reference_lotes: tuple[str, ...]
    input_dir: Path
    input_csv: Path
    log_file: Path
    report_dir: Path
    processing_delay_seconds: float
    web_automation_enabled: bool
    web_test_url: str
    runner_context: bool

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "Settings":
        """Carrega `.env` e resolve caminhos relativos a partir do projeto."""
        root = (base_dir or Path(__file__).resolve().parents[1]).resolve()
        load_dotenv(root / ".env")
        runner_server, runner_task_id = botcity_runner_args()
        runner_context = bool(runner_server and runner_task_id)

        def project_path(variable: str, default: str) -> Path:
            configured = Path(os.getenv(variable, default)).expanduser()
            if configured.is_absolute():
                return configured
            return (root / configured).resolve()

        def env_or_default(variable: str, default: str = "") -> str:
            return (os.getenv(variable, "").strip() or default).strip()

        return cls(
            base_dir=root,
            maestro_enabled=as_bool(os.getenv("MAESTRO_ENABLED"), runner_context),
            vault_enabled=as_bool(os.getenv("VAULT_ENABLED"), runner_context),
            maestro_server=env_or_default("MAESTRO_SERVER", runner_server),
            maestro_login=env_or_default("MAESTRO_LOGIN"),
            maestro_key=env_or_default("MAESTRO_KEY"),
            maestro_task_id=env_or_default("MAESTRO_TASK_ID", runner_task_id),
            datapool_label=os.getenv(
                "DATAPOOL_LABEL", "FilaAuditoriaLotes2"
            ).strip(),
            vault_label=os.getenv("VAULT_LABEL", "credencial_erp2").strip(),
            reference_lotes=tuple(
                lote.strip()
                for lote in os.getenv("REFERENCE_LOTES", "L001,L002").split(",")
                if lote.strip()
            ),
            input_dir=project_path("INPUT_DIR", "dados_entrada"),
            input_csv=project_path("INPUT_CSV", "dados_entrada/lotes_auditoria.csv"),
            log_file=project_path("LOG_FILE", "logs/execucao.log"),
            report_dir=project_path("REPORT_DIR", "relatorios"),
            processing_delay_seconds=float(os.getenv("PROCESSING_DELAY_SECONDS", "1")),
            web_automation_enabled=as_bool(
                os.getenv("WEB_AUTOMATION_ENABLED"), False
            ),
            web_test_url=env_or_default(
                "WEB_TEST_URL", "docs/index-lotes/index.html"
            ),
            runner_context=runner_context,
        )

    def validate(self) -> None:
        """Valida apenas os valores necessários quando o Maestro está ativo."""
        if not self.maestro_enabled:
            return

        required = {"MAESTRO_SERVER": self.maestro_server}
        if not self.runner_context:
            required.update(
                {
                    "MAESTRO_LOGIN": self.maestro_login,
                    "MAESTRO_KEY": self.maestro_key,
                }
            )
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Configuração obrigatória ausente: " + ", ".join(missing)
            )
        if not self.vault_enabled:
            raise ValueError(
                "VAULT_ENABLED deve ser true quando MAESTRO_ENABLED=true"
            )
