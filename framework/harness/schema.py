from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OptionalField:
    """호출 조건에 따라 부재를 허용하는 필드 wrapper.

    없으면 통과, 있으면 inner 규칙(Any/choices/중첩 스키마)으로 그대로 검증한다 —
    기본은 스키마에 선언된 키가 전부 필수인데, 이 wrapper로 감싼 키만 예외적으로
    부재를 허용한다. `harness.guardrail`의 output_schema와
    `registry.decorators.human_action`의 payload_schemas가 공유하는 원시 요소다.
    """

    inner: Any


def optional(schema: Any) -> OptionalField:
    return OptionalField(schema)


class SchemaViolation(Exception):
    """스키마 위반 하나 — 호출자(guardrail/human_action)가 자기 맥락(stage,
    tool_name 등)을 붙여 자기 예외 타입으로 다시 던지는 걸 전제로 한다.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def validate_schema(value: dict[str, Any], schema: dict[str, Any] | None, path: str = "") -> None:
    """value가 schema를 만족하는지 재귀 검증한다.

    스키마 값의 형태로 세 가지를 구분한다.
    - `Any` -> 필드 존재 여부만 확인
    - `{"choices": [...]}` -> enum 제약
    - 그 외 dict -> 중첩 스키마로 간주해 재귀 검증
    `OptionalField`로 감싸진 키는 부재를 허용한다. 위반 시 `SchemaViolation`을
    던지며, `path`는 실패 지점을 `subscription.status`처럼 점(dot) 경로로 표현한다.
    """
    if schema is None:
        return
    for key, expected_type in schema.items():
        field_path = f"{path}.{key}" if path else key

        if isinstance(expected_type, OptionalField):
            if key not in value:
                continue
            expected_type = expected_type.inner

        if key not in value:
            raise SchemaViolation(f"missing required field '{field_path}'")

        if expected_type is Any:
            continue

        if isinstance(expected_type, dict) and "choices" in expected_type:
            if value[key] not in expected_type["choices"]:
                raise SchemaViolation(f"'{field_path}'={value[key]!r} not in enum {expected_type['choices']}")
            continue

        if isinstance(expected_type, dict):
            nested_value = value[key]
            if not isinstance(nested_value, dict):
                raise SchemaViolation(f"'{field_path}' expected a nested object, got {type(nested_value).__name__}")
            validate_schema(nested_value, expected_type, path=field_path)
