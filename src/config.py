"""Configuração central do bot carregada por variáveis de ambiente."""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values


TRUE_VALUES = {"1", "true", "yes", "sim", "on"}


def as_bool(value: str | None, default: bool = False) -> bool:
    """Converte uma variável textual em booleano de forma previsível."""
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def as_optional_float(
    value: str | None,
    default: float,
) -> float | None:
    """Converte número textual sem interromper o carregamento da configuração."""
    if value is None:
        return default
    try:
        converted = float(value.strip())
    except ValueError:
        return None
    return converted if math.isfinite(converted) else None


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
    bot_id: str
    execution_id: str
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
    web_artifact_dir: Path
    web_timeout_seconds: float | None
    runner_context: bool

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "Settings":
        """Carrega `.env` e resolve caminhos relativos a partir do projeto."""
        root = (base_dir or Path(__file__).resolve().parents[1]).resolve()
        dotenv_env = {
            key: value
            for key, value in dotenv_values(root / ".env").items()
            if value is not None
        }
        env = {**dotenv_env, **os.environ}
        runner_server, runner_task_id = botcity_runner_args()
        runner_context = bool(runner_server and runner_task_id)

        def project_path(variable: str, default: str) -> Path:
            configured = Path(env.get(variable, default)).expanduser()
            if configured.is_absolute():
                return configured
            return (root / configured).resolve()

        def env_or_default(variable: str, default: str = "") -> str:
            return (env.get(variable, "").strip() or default).strip()

        return cls(
            base_dir=root,
            maestro_enabled=as_bool(env.get("MAESTRO_ENABLED"), runner_context),
            vault_enabled=as_bool(env.get("VAULT_ENABLED"), runner_context),
            maestro_server=env_or_default("MAESTRO_SERVER", runner_server),
            maestro_login=env_or_default("MAESTRO_LOGIN"),
            maestro_key=env_or_default("MAESTRO_KEY"),
            maestro_task_id=env_or_default("MAESTRO_TASK_ID", runner_task_id),
            bot_id=env_or_default("BOT_ID", "bot-conferencia-de-lotes-v2"),
            execution_id=env_or_default(
                "EXECUTION_ID",
                runner_task_id or "execucao-local",
            ),
            datapool_label=env.get(
                "DATAPOOL_LABEL", "FilaAuditoriaLotes2"
            ).strip(),
            vault_label=env.get("VAULT_LABEL", "credencial_erp2").strip(),
            reference_lotes=tuple(
                lote.strip()
                for lote in env.get("REFERENCE_LOTES", "L001,L002").split(",")
                if lote.strip()
            ),
            input_dir=project_path("INPUT_DIR", "dados_entrada"),
            input_csv=project_path("INPUT_CSV", "dados_entrada/lotes_auditoria.csv"),
            log_file=project_path("LOG_FILE", "logs/execucao.log"),
            report_dir=project_path("REPORT_DIR", "relatorios"),
            processing_delay_seconds=float(env.get("PROCESSING_DELAY_SECONDS", "1")),
            web_automation_enabled=as_bool(
                env.get("WEB_AUTOMATION_ENABLED"), runner_context
            ),
            web_test_url=env_or_default(
                "WEB_TEST_URL", "web/index-lotes/index.html"
            ),
            web_artifact_dir=project_path(
                "WEB_ARTIFACT_DIR", "artefatos"
            ),
            web_timeout_seconds=as_optional_float(
                env.get("WEB_TIMEOUT_SECONDS"),
                15.0,
            ),
            runner_context=runner_context,
        )

    def validate(self) -> None:
        """Valida valores dependentes das integrações habilitadas."""
        if self.maestro_enabled:
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

        if self.web_automation_enabled:
            self._validate_web_test_url()

    def _validate_web_test_url(self) -> None:
        """Garante que a página web e o timeout do Selenium sejam válidos."""
        if (
            self.web_timeout_seconds is None
            or self.web_timeout_seconds <= 0
        ):
            raise ValueError(
                "WEB_TIMEOUT_SECONDS deve ser um número maior que zero"
            )
        if not self.web_test_url.strip():
            raise ValueError("WEB_TEST_URL deve ser informado")
        if urlparse(self.web_test_url).scheme:
            return

        path = Path(self.web_test_url).expanduser()
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.is_file():
            raise ValueError(f"WEB_TEST_URL local inexistente: {path}")
