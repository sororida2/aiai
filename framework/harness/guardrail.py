from __future__ import annotations

from typing import Any

from agents import Agent, GuardrailFunctionOutput, RunContextWrapper, output_guardrail

from framework.harness.logging_setup import get_logger
from framework.harness.schema import OptionalField, SchemaViolation, optional, validate_schema
from framework.registry.decorators import registry

logger = get_logger("guardrail")

__all__ = ["output_schema_guardrail", "GuardrailViolation", "OptionalField", "optional", "validate_tool_output"]


class GuardrailViolation(Exception):
    def __init__(self, stage: str, tool_name: str, detail: str) -> None:
        super().__init__(f"[{stage}] '{tool_name}' guardrail failed: {detail}")
        self.stage = stage
        self.tool_name = tool_name
        self.detail = detail


def validate_tool_output(tool_name: str, output: dict[str, Any]) -> dict[str, Any]:
    """`registry.tool_for(tool_name).output_schema`로 output을 검증하고 그대로 돌려준다.

    tool 함수 본문 마지막 줄에서 `return validate_tool_output("weather", result)`처럼
    선택적으로 부르는 fine-grained 검증이다 — Agent 단위 guardrail(아래
    `output_schema_guardrail`)은 "이 출력을 만든 tool이 뭔지" 알 방법이 없어서
    enum/optional 같은 tool별 세부 규칙까지 못 보므로(§ 아래 설명), 그 세부 검증이
    실제로 필요한 tool은 이 헬퍼를 명시적으로 불러 예전 GuardrailChain과 같은
    수준의 보장을 유지한다.
    """
    spec = registry.tool_for(tool_name)
    try:
        validate_schema(output, spec.output_schema)
    except SchemaViolation as e:
        logger.error("output: '%s' guardrail failed — %s", tool_name, e.detail)
        raise GuardrailViolation("output", tool_name, e.detail) from e
    logger.debug("'%s' output validated ok", tool_name)
    return output


@output_guardrail
async def output_schema_guardrail(ctx: RunContextWrapper[Any], agent: Agent, output: Any) -> GuardrailFunctionOutput:
    """Agent의 최종 출력을 관찰한다 — SDK 관례대로 tool 단위가 아니라 Agent 단위다.

    **알려진 한계(§ ARCHITECTURE.md의 SDK 마이그레이션 절 참고)**: 예전 `GuardrailChain`은
    tool을 부를 때마다(개별 호출 단위로) 그 tool에 선언된 `output_schema`로 검증했다.
    SDK의 `@output_guardrail`은 Agent의 최종 출력 **하나**만 보고, 이 함수 시그니처
    (`ctx`/`agent`/`output`)만으로는 "어떤 tool이 이 값을 만들었는지" 알 수 없다.

    처음엔 여기서 `isinstance(output, dict)`로 막으려 했는데, 실제로 Windows에서 돌려보니
    `tool_use_behavior="stop_on_first_tool"`일 때 이 자리에 넘어오는 `output`이 dict가
    아니었다(정확한 타입은 SDK 내부 구현에 달려 있어 이 자리에서 확정할 수 없음) — 그래서
    유효한 응답인데도 tripwire가 발동해 막아버리는 실제 버그를 냈다. 진짜 스키마 검증은 이미
    `validate_tool_output(name, output)`이 tool 함수 본문 안에서 끝냈으므로(§ 위 함수,
    `services/weather/workflow.py` 등 실제 사례), 여기서는 **막지 않고 로깅만** 한다 —
    이 자리의 정확한 데이터 모양을 확신하기 전까지는 안전하게 관찰만 하는 쪽을 택했다.
    """
    logger.debug("output guardrail: observed output type=%s", type(output).__name__)
    return GuardrailFunctionOutput(output_info={"observed_type": type(output).__name__}, tripwire_triggered=False)
