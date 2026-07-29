from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from services.weather.adapter import WeatherAdapter

WEATHER_OUTPUT_SCHEMA = {
    "location": Any,
    "condition": Any,
    "condition_confidence": {"choices": ["confirmed", "inferred"]},
    "temperature": Any,
}


@tool(
    name="weather",
    description="지정한 지역(location)의 현재 날씨를 조회한다. location 하나만 입력받는다.",
)
@guardrail(output_schema=WEATHER_OUTPUT_SCHEMA)
def weather(location: str) -> dict[str, Any]:
    return WeatherAdapter().execute(location=location)
