from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass


class UnmappedValueError(Exception):
    """미확인 코드값 — guardrail이 fail-fast로 차단해야 하는 지점.

    이 예외를 조사 큐(로그)로 흘려보내는 것이 지속적 발굴 파이프라인의 입구다.
    """


@dataclass(frozen=True)
class MappedValue:
    raw: str
    value: str
    confidence: str  # "confirmed" | "inferred"

    def require_confirmed(self) -> str:
        if self.confidence != "confirmed":
            raise UnmappedValueError(
                f"raw value '{self.raw}' is only 'inferred' — not usable in a judgment branch"
            )
        return self.value


class SemanticMapping:
    """레거시 원시값 -> 정규화값. 매핑 조사는 사람이 최초 1회 수행하는 고정 자산."""

    def __init__(self, entries: dict[str, dict[str, str]]) -> None:
        self._entries = entries

    @classmethod
    def from_json(cls, path: str | pathlib.Path) -> "SemanticMapping":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("mappings", {}))

    def normalize(self, raw_value: str) -> MappedValue:
        entry = self._entries.get(raw_value)
        if entry is None:
            raise UnmappedValueError(f"raw value '{raw_value}' has no mapping entry")
        return MappedValue(raw=raw_value, value=entry["value"], confidence=entry["confidence"])
