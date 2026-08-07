from __future__ import annotations

from typing import Any

from framework.harness.guardrail import validate_tool_output
from framework.registry.decorators import tool
from services.applicant_list.adapter import ApplicantListAdapter

APPLICANT_LIST_OUTPUT_SCHEMA = {"applicants": Any, "table": Any}


def _render_table(applicants: list[dict[str, Any]]) -> str:
    header = "| 신청자 ID | 이름 | 상태 | 상태 신뢰도 |\n|---|---|---|---|"
    rows = [
        f"| {a['applicant_id']} | {a['name']} | {a['status']} | {a['status_confidence']} |" for a in applicants
    ]
    return "\n".join([header, *rows])


@tool(
    name="applicant_list",
    description=(
        "현재 청약 신청자 전원의 목록과 각자의 진행 단계를 표 형식으로 보여준다. "
        "입력을 받지 않는다. 이 결과를 보고 사용자가 특정 신청자의 상세 상태를 물어보면, "
        "그 사람의 applicant_id를 이 목록에서 찾아 subscription_status(applicant_id=...)로 "
        "이어서 조회해야 한다 — applicant_list 자체는 상세 조회 기능이 없다."
    ),
    output_schema=APPLICANT_LIST_OUTPUT_SCHEMA,
)
def applicant_list() -> dict[str, Any]:
    applicants = ApplicantListAdapter().execute()["applicants"]
    result = {"applicants": applicants, "table": _render_table(applicants)}
    return validate_tool_output("applicant_list", result)
