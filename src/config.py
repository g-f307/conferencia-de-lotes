"""Configuração central do bot carregada por variáveis de ambiente."""

import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
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


def as_optional_int(value: str | None, default: int) -> int | None:
    """Converte um inteiro textual sem mascarar configuração inválida."""
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return None


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
    ml_enabled: bool
    ml_api_url: str
    ml_timeout_seconds: float | None
    runner_context: bool
    ml_confianca_minima: float | None = 0.85
    orchestration_enabled: bool = False
    orchestration_timeout_seconds: float | None = 300.0
    orchestration_poll_interval_seconds: float | None = 2.0
    reference_max_attempts: int | None = 3
    reference_retry_base_interval_seconds: float | None = 1.0
    reference_timeout_seconds: float | None = 5.0
    dead_letter_path: Path | None = None
    alerts_enabled: bool = False
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = ""
    telegram_api_base_url: str = "https://api.telegram.org"
    smtp_host: str = ""
    smtp_port: int | None = 587
    smtp_username: str = ""
    smtp_password: str = field(default="", repr=False)
    smtp_from: str = ""
    smtp_to: tuple[str, ...] = ()
    smtp_use_tls: bool = True
    alerts_timeout_seconds: float | None = 5.0

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
            processing_delay_seconds=float(env.get("PROCESSING_DELAY_SECONDS", "0")),
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
            ml_enabled=as_bool(env.get("ML_ENABLED"), False),
            ml_api_url=env_or_default("ML_API_URL"),
            ml_timeout_seconds=as_optional_float(
                env.get("ML_TIMEOUT_SECONDS"),
                3.0,
            ),
            runner_context=runner_context,
            ml_confianca_minima=as_optional_float(
                env.get("ML_CONFIANCA_MINIMA"),
                0.85,
            ),
            orchestration_enabled=as_bool(
                env.get("ORCHESTRATION_ENABLED"),
                False,
            ),
            orchestration_timeout_seconds=as_optional_float(
                env.get("ORCHESTRATION_TIMEOUT_SECONDS"),
                300.0,
            ),
            orchestration_poll_interval_seconds=as_optional_float(
                env.get("ORCHESTRATION_POLL_INTERVAL_SECONDS"),
                2.0,
            ),
            reference_max_attempts=as_optional_int(
                env.get("REFERENCE_MAX_ATTEMPTS"),
                3,
            ),
            reference_retry_base_interval_seconds=as_optional_float(
                env.get("REFERENCE_RETRY_BASE_INTERVAL_SECONDS"),
                1.0,
            ),
            reference_timeout_seconds=as_optional_float(
                env.get("REFERENCE_TIMEOUT_SECONDS"),
                5.0,
            ),
            dead_letter_path=project_path(
                "DEAD_LETTER_PATH",
                "data/output/dead_letter.jsonl",
            ),
            alerts_enabled=as_bool(env.get("ALERTS_ENABLED"), False),
            telegram_bot_token=env_or_default("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=env_or_default("TELEGRAM_CHAT_ID"),
            telegram_api_base_url=env_or_default(
                "TELEGRAM_API_BASE_URL",
                "https://api.telegram.org",
            ),
            smtp_host=env_or_default("SMTP_HOST"),
            smtp_port=as_optional_int(env.get("SMTP_PORT"), 587),
            smtp_username=env_or_default("SMTP_USERNAME"),
            smtp_password=env_or_default("SMTP_PASSWORD"),
            smtp_from=env_or_default("SMTP_FROM"),
            smtp_to=tuple(
                address.strip()
                for address in env.get("SMTP_TO", "").split(",")
                if address.strip()
            ),
            smtp_use_tls=as_bool(env.get("SMTP_USE_TLS"), True),
            alerts_timeout_seconds=as_optional_float(
                env.get("ALERTS_TIMEOUT_SECONDS"),
                5.0,
            ),
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

        if self.ml_enabled:
            self._validate_ml_configuration()

        if self.orchestration_enabled:
            if not self.maestro_enabled:
                raise ValueError(
                    "MAESTRO_ENABLED deve ser true quando ORCHESTRATION_ENABLED=true"
                )
            if (
                self.orchestration_timeout_seconds is None
                or self.orchestration_timeout_seconds <= 0
            ):
                raise ValueError(
                    "ORCHESTRATION_TIMEOUT_SECONDS deve ser maior que zero"
                )
            if (
                self.orchestration_poll_interval_seconds is None
                or self.orchestration_poll_interval_seconds <= 0
            ):
                raise ValueError(
                    "ORCHESTRATION_POLL_INTERVAL_SECONDS deve ser maior que zero"
                )

        if self.reference_max_attempts is None or self.reference_max_attempts < 1:
            raise ValueError("REFERENCE_MAX_ATTEMPTS deve ser maior que zero")
        if (
            self.reference_retry_base_interval_seconds is None
            or self.reference_retry_base_interval_seconds <= 0
        ):
            raise ValueError(
                "REFERENCE_RETRY_BASE_INTERVAL_SECONDS deve ser maior que zero"
            )
        if (
            self.reference_timeout_seconds is None
            or self.reference_timeout_seconds <= 0
        ):
            raise ValueError("REFERENCE_TIMEOUT_SECONDS deve ser maior que zero")
        if self.dead_letter_path is None:
            raise ValueError("DEAD_LETTER_PATH deve ser informado")

        if self.alerts_enabled:
            self._validate_alerts_configuration()

    def _validate_alerts_configuration(self) -> None:
        required = {
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat_id,
            "SMTP_HOST": self.smtp_host,
            "SMTP_FROM": self.smtp_from,
            "SMTP_TO": self.smtp_to,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Configuração obrigatória de alertas ausente: "
                + ", ".join(missing)
            )
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError(
                "SMTP_USERNAME e SMTP_PASSWORD devem ser informados em conjunto"
            )
        if self.smtp_port is None or not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP_PORT deve estar entre 1 e 65535")
        if self.alerts_timeout_seconds is None or self.alerts_timeout_seconds <= 0:
            raise ValueError("ALERTS_TIMEOUT_SECONDS deve ser maior que zero")

        parsed_url = urlparse(self.telegram_api_base_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("TELEGRAM_API_BASE_URL deve ser uma URL HTTP válida")
        if parsed_url.scheme == "http" and parsed_url.hostname not in {
            "127.0.0.1",
            "::1",
            "localhost",
        }:
            raise ValueError(
                "TELEGRAM_API_BASE_URL exige HTTPS fora do ambiente local"
            )

    def _validate_ml_configuration(self) -> None:
        """Valida somente os parâmetros necessários quando ML está ativo."""
        if not self.ml_api_url:
            raise ValueError("ML_API_URL deve ser informado quando ML_ENABLED=true")
        parsed_url = urlparse(self.ml_api_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("ML_API_URL deve ser uma URL HTTP ou HTTPS válida")
        if (
            parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError(
                "ML_API_URL não deve conter credenciais ou parâmetros sensíveis"
            )
        if self.ml_timeout_seconds is None or self.ml_timeout_seconds <= 0:
            raise ValueError(
                "ML_TIMEOUT_SECONDS deve ser um número maior que zero"
            )
        if (
            self.ml_confianca_minima is None
            or not 0 <= self.ml_confianca_minima <= 1
        ):
            raise ValueError(
                "ML_CONFIANCA_MINIMA deve ser um número entre zero e um"
            )

    def _validate_web_test_url(self) -> None:
        """Garante que a página web e o timeout do Playwright sejam válidos."""
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
