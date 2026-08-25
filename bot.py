"""Entry point do bot para execução local ou pelo BotCity Runner."""

from src.config import Settings
from src.orchestrator import BOT_LABELS


if __name__ == "__main__":
    settings = Settings.from_env()
    if settings.orchestration_enabled or settings.bot_id in BOT_LABELS.values():
        from src.orchestrator import main
    else:
        from src.main import main

    raise SystemExit(main(settings))
