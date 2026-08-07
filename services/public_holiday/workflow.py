from __future__ import annotations

from typing import Any

from framework.harness.guardrail import validate_tool_input, validate_tool_output
from framework.registry.decorators import tool
from services.public_holiday.adapter import PublicHolidayAdapter
from shared.countries import ISO_3166_1_ALPHA2

PUBLIC_HOLIDAY_OUTPUT_SCHEMA = {"holidays": Any}

# country_code는 여기 own adapter에 정규화용 mapping.json이 없어(Nager.Date가 alpha-2를
# 그대로 받음) 잘못된 값이 들어와도 여태 아무것도 안 걸렀다 — 특히 ip_geolocation처럼 다른
# tool의 출력을 모델이 이어서 채우는 체이닝 경로에서 실측된 gap(§ ARCHITECTURE.md의
# "SDK 마이그레이션" 절). year는 자연스러운 닫힌 집합이 없어 Any로 둔다(SDK의 타입 체크로 충분).
PUBLIC_HOLIDAY_INPUT_SCHEMA = {"year": Any, "country_code": {"choices": sorted(ISO_3166_1_ALPHA2)}}


@tool(
    name="public_holiday",
    description=(
        "지정한 연도(year)와 국가 코드(country_code, ISO 3166-1 alpha-2, 예: KR/US/JP)의 "
        "공휴일 목록을 조회한다."
    ),
    output_schema=PUBLIC_HOLIDAY_OUTPUT_SCHEMA,
    input_schema=PUBLIC_HOLIDAY_INPUT_SCHEMA,
)
def public_holiday(year: int, country_code: str) -> dict[str, Any]:
    validate_tool_input("public_holiday", {"year": year, "country_code": country_code})
    result = PublicHolidayAdapter().execute(year=year, country_code=country_code)
    return validate_tool_output("public_holiday", result)
