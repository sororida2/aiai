from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, registry, tool
from framework.workflow.registry import WorkflowRegistry
from framework.workflow.state_machine import StateMachine
from services.subscription_status.workflow import SUBSCRIPTION_STATUS_OUTPUT_SCHEMA
from services.weather.workflow import WEATHER_OUTPUT_SCHEMA

steps = WorkflowRegistry()


@steps.step(order=1, next={"완료": "query_weather"})
def query_subscription(context: dict[str, Any]) -> str:
    # 다른 서비스의 함수를 직접 import하지 않는다 — 이름(문자열)만 알면 되도록 전역
    # ToolRegistry에서 런타임에 찾는다. 오케스트레이터가 tool을 고를 때와 같은 원칙
    # ("엔진은 tool 이름 문자열에만 커플링된다")을 서비스 간 호출에도 그대로 적용한 것.
    # 함수 본문 안에서(모듈 로드 시점이 아니라) 찾기 때문에 discover_services()가
    # 서비스를 어떤 순서로 import하든 안전하다 — 실제 호출 시점엔 전부 등록이 끝나 있다.
    # tool_for()가 돌려주는 ToolSpec 자체가 호출 가능해서(.__call__) .func를 몰라도 된다.
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
@guardrail(output_schema={"subscription": SUBSCRIPTION_STATUS_OUTPUT_SCHEMA, "weather": WEATHER_OUTPUT_SCHEMA})
def subscription_weather_flow(applicant_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"applicant_id": applicant_id}
    build_state_machine().run(context)
    return {"subscription": context["subscription_result"], "weather": context["weather_result"]}
