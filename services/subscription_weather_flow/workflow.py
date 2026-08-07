from __future__ import annotations

from typing import Any

from framework.harness.guardrail import GuardrailViolation
from framework.harness.schema import SchemaViolation, validate_schema
from framework.registry.decorators import registry, tool
from framework.workflow.registry import WorkflowRegistry
from framework.workflow.state_machine import StateMachine

steps = WorkflowRegistry()


@steps.step(order=1, next={"완료": "query_weather"})
def query_subscription(context: dict[str, Any]) -> str:
    # 다른 서비스의 함수를 직접 import하지 않는다 — 이름(문자열)만 알면 되도록 전역
    # ToolRegistry에서 런타임에 찾는다. tool_for()가 돌려주는 ToolSpec 자체가 호출
    # 가능해서(.__call__ -> .func) SDK를 거치지 않고 원본 함수를 바로 부른다 —
    # SDK function_tool로 감싼 버전은 JSON 문자열 인자를 받아서 이런 직접 합성엔 안 맞는다.
    subscription_status = registry.tool_for("subscription_status")
    context["subscription_result"] = subscription_status(applicant_id=context["applicant_id"])
    return "완료"


@steps.step(order=2, next={"완료": "DONE"})
def query_weather(context: dict[str, Any]) -> str:
    weather = registry.tool_for("weather")
    region = context["subscription_result"]["region"]
    context["weather_result"] = weather(location=region)
    return "완료"


steps.validate()


def build_state_machine() -> StateMachine:
    return StateMachine(registry=steps, entry="query_subscription")


@tool(
    name="subscription_weather_flow",
    description=(
        "청약 신청자의 진행상황을 조회하고, 그 신청자의 소재 지역(region) 날씨까지 이어서 "
        "조회하는 복합 capability. applicant_id 하나만 입력받는다 — location은 입력받지 않으며, "
        "subscription_status 조회 결과의 region 값을 그대로 weather의 입력으로 사용한다."
    ),
)
def subscription_weather_flow(applicant_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"applicant_id": applicant_id}
    build_state_machine().run(context)
    result = {"subscription": context["subscription_result"], "weather": context["weather_result"]}

    # 중첩 스키마는 호출 시점(여기)에 다른 두 tool의 output_schema를 조회해서 조립한다 —
    # discover_services()가 이 파일을 어떤 순서로 import하든(알파벳상 weather보다 먼저 와도)
    # 실제 호출은 항상 모든 서비스 등록이 끝난 뒤 일어나므로 안전하다.
    nested_schema = {
        "subscription": registry.tool_for("subscription_status").output_schema,
        "weather": registry.tool_for("weather").output_schema,
    }
    try:
        validate_schema(result, nested_schema)
    except SchemaViolation as e:
        raise GuardrailViolation("output", "subscription_weather_flow", e.detail) from e
    return result
