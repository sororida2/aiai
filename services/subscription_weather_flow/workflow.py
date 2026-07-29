from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from framework.workflow.registry import WorkflowRegistry
from framework.workflow.state_machine import StateMachine
from services.subscription_status.workflow import SUBSCRIPTION_STATUS_OUTPUT_SCHEMA, subscription_status
from services.weather.workflow import WEATHER_OUTPUT_SCHEMA, weather

steps = WorkflowRegistry()


@steps.step(order=1, next={"완료": "query_weather"})
def query_subscription(context: dict[str, Any]) -> str:
    context["subscription_result"] = subscription_status(applicant_id=context["applicant_id"])
    return "완료"


@steps.step(order=2, next={"완료": "DONE"})
def query_weather(context: dict[str, Any]) -> str:
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
