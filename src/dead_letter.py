"""Persistência JSON Lines para itens irrecuperáveis de dados."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from typing import TextIO

from src.logging_config import sanitize_text

DEFAULT_DEAD_LETTER_PATH = Path("data") / "output" / "dead_letter.jsonl"
SAFE_ITEM_FIELDS = (
    "lote_id",
    "produto",
    "linha",
    "turno",
    "status",
    "responsavel",
    "data",
)


class DeadLetterWriter:
    """Grava uma única ocorrência por item, motivo, execução e task."""

    def __init__(
        self,
        path: str | Path,
        *,
        execution_id: str,
        task_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = Path(path)
        self.execution_id = _required_text(execution_id, "execution_id")
        self.task_id = _required_text(task_id, "task_id")
        self.now = now

    def write(
        self,
        item: Mapping[str, object],
        *,
        reason: str,
        attempts: int,
    ) -> bool:
        """Retorna `True` somente quando uma nova linha é persistida."""
        normalized_reason = _required_text(reason, "reason")
        if isinstance(attempts, bool) or attempts < 1:
            raise ValueError("attempts deve ser um inteiro maior que zero")

        sanitized_item = sanitize_item(item)
        deduplication_key = self._deduplication_key(
            sanitized_item,
            normalized_reason,
        )
        timestamp = self.now()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        record = {
            "item": sanitized_item,
            "motivo": sanitize_text(normalized_reason),
            "tentativas": attempts,
            "timestamp": timestamp.astimezone(UTC).isoformat(),
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "deduplication_key": deduplication_key,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self.path.open("a+", encoding="utf-8") as stream:
            flock(stream.fileno(), LOCK_EX)
            try:
                if deduplication_key in self._load_known_keys(stream):
                    return False
                stream.seek(0, 2)
                stream.write(serialized)
                stream.flush()
                return True
            finally:
                flock(stream.fileno(), LOCK_UN)

    def _deduplication_key(
        self,
        item: dict[str, str],
        reason: str,
    ) -> str:
        canonical = json.dumps(
            {
                "item": item,
                "motivo": sanitize_text(reason),
                "execution_id": self.execution_id,
                "task_id": self.task_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _load_known_keys(stream: TextIO) -> set[str]:
        keys: set[str] = set()
        stream.seek(0)
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = str(record.get("deduplication_key") or "").strip()
            if key:
                keys.add(key)
        return keys


def sanitize_item(item: Mapping[str, object]) -> dict[str, str]:
    """Mantém apenas os campos necessários e nunca persiste observações."""
    return {
        field: sanitize_text(item.get(field) or "")
        for field in SAFE_ITEM_FIELDS
    }


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} deve ser informado")
    return normalized
