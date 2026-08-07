from __future__ import annotations

from typing import Any

from framework.harness.guardrail import validate_tool_input, validate_tool_output
from framework.registry.decorators import tool
from services.university_search.adapter import UniversitySearchAdapter
from shared.countries import ISO_3166_1_ALPHA2

UNIVERSITY_SEARCH_OUTPUT_SCHEMA = {"universities": Any}

# 잘못된 country_code는 adapter 내부의 SemanticMapping.normalize()가 UnmappedValueError로
# 우연히 걸러주고 있었다(자기 mapping.json이 alpha-2 키를 갖고 있어서) — 여기서도 명시적으로
# 선언해 다른 tool(§ public_holiday)과 같은 지점(호출 직전)에서 같은 종류의 실패로 통일한다.
UNIVERSITY_SEARCH_INPUT_SCHEMA = {"country_code": {"choices": sorted(ISO_3166_1_ALPHA2)}}


@tool(
    name="university_search",
    description=(
        "지정한 국가 코드(country_code, ISO 3166-1 alpha-2, 예: KR/US/MY)에 속한 대학 목록"
        "(이름/도메인/웹사이트)을 조회한다."
    ),
    output_schema=UNIVERSITY_SEARCH_OUTPUT_SCHEMA,
    input_schema=UNIVERSITY_SEARCH_INPUT_SCHEMA,
)
def university_search(country_code: str) -> dict[str, Any]:
    validate_tool_input("university_search", {"country_code": country_code})
    result = UniversitySearchAdapter().execute(country_code=country_code)
    return validate_tool_output("university_search", result)
