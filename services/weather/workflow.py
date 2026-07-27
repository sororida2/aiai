from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, registry, tool, workflow_step
from framework.workflow.state_machine import StateMachine
from services.weather.adapter import WeatherAdapter


@workflow_step(order=1, source="yahoo_weather_rapidapi", next={"완료": "DONE"})
def fetch_weather(context: dict[str, Any]) -> str:
    adapter: WeatherAdapter = context["adapter"]
    result = adapter.execute(location=context["location"])
    context["last_result"] = result
    return "완료"


def build_state_machine() -> StateMachine:
    return StateMachine(registry=registry, entry="fetch_weather")


@tool(
    name="weather",
    description="지정한 지역(location)의 현재 날씨를 조회한다. location 하나만 입력받는다.",
)
@guardrail(
    output_schema={
        "location": Any,
        "condition": Any,
        "condition_confidence": {"choices": ["confirmed", "inferred"]},
        "temperature": Any,
    }
)
def weather(location: str) -> dict[str, Any]:
    context: dict[str, Any] = {"location": location, "adapter": WeatherAdapter()}
    build_state_machine().run(context)
    return context["last_result"]
