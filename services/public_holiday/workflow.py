from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from services.public_holiday.adapter import PublicHolidayAdapter

PUBLIC_HOLIDAY_OUTPUT_SCHEMA = {"holidays": Any}


@tool(
    name="public_holiday",
    description=(
        "지정한 연도(year)와 국가 코드(country_code, ISO 3166-1 alpha-2, 예: KR/US/JP)의 "
        "공휴일 목록을 조회한다."
    ),
)
@guardrail(output_schema=PUBLIC_HOLIDAY_OUTPUT_SCHEMA)
def public_holiday(year: int, country_code: str) -> dict[str, Any]:
    return PublicHolidayAdapter().execute(year=year, country_code=country_code)
