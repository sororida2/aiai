from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from services.university_search.adapter import UniversitySearchAdapter

UNIVERSITY_SEARCH_OUTPUT_SCHEMA = {"universities": Any}


@tool(
    name="university_search",
    description=(
        "지정한 국가 코드(country_code, ISO 3166-1 alpha-2, 예: KR/US/MY)에 속한 대학 목록"
        "(이름/도메인/웹사이트)을 조회한다."
    ),
)
@guardrail(output_schema=UNIVERSITY_SEARCH_OUTPUT_SCHEMA)
def university_search(country_code: str) -> dict[str, Any]:
    return UniversitySearchAdapter().execute(country_code=country_code)
