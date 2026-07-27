from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from framework.harness.logging_setup import get_logger
from framework.harness.schema import OptionalField, SchemaViolation, optional, validate_schema
from framework.registry.decorators import GuardrailSpec, ToolRegistry

logger = get_logger("guardrail")

__all__ = ["GuardrailChain", "GuardrailViolation", "OptionalField", "optional"]


class GuardrailViolation(Exception):
    def __init__(self, stage: str, tool_name: str, detail: str) -> None:
        super().__init__(f"[{stage}] '{tool_name}' guardrail failed: {detail}")
        self.stage = stage
        self.tool_name = tool_name
        self.detail = detail


def _validate(value: dict[str, Any], schema: dict[str, Any] | None, stage: str, tool_name: str) -> None:
    if schema is None:
        logger.debug("'%s' %s_schema not declared, skipping %s validation", tool_name, stage, stage)
        return
    try:
        validate_schema(value, schema)
    except SchemaViolation as e:
        logger.error("%s: '%s' guardrail failed — %s", stage, tool_name, e.detail)
        raise GuardrailViolation(stage, tool_name, e.detail) from e
    logger.debug("'%s' %s validated ok", tool_name, stage)


@dataclass
class GuardrailChain:
    """Input Guardrail -> Tool 실행 -> Output Guardrail. 실패 시 즉시 차단.

    엔진은 registry에 선언된 스키마만 읽는다. 여기에 특정 tool 이름을
    하드코딩하는 분기가 생기면 그게 안티패턴이다.
    """

    registry: ToolRegistry

    def run(self, tool_name: str, call: Callable[[], dict[str, Any]], input_payload: dict[str, Any]) -> dict[str, Any]:
        spec: GuardrailSpec | None = self.registry.guardrail_for(tool_name)
        if spec is None:
            return call()

        _validate(input_payload, spec.input_schema, "input", tool_name)
        output = call()
        _validate(output, spec.output_schema, "output", tool_name)
        return output
