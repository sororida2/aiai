from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, registry, tool, workflow_step
from framework.workflow.state_machine import StateMachine
from services.applicant_list.adapter import ApplicantListAdapter


@workflow_step(order=1, next={"완료": "DONE"})
def fetch_applicants(context: dict[str, Any]) -> str:
    adapter: ApplicantListAdapter = context["adapter"]
    context["last_result"] = adapter.execute()
    return "완료"


def build_state_machine() -> StateMachine:
    return StateMachine(registry=registry, entry="fetch_applicants")


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
)
@guardrail(output_schema={"applicants": Any, "table": Any})
def applicant_list() -> dict[str, Any]:
    context: dict[str, Any] = {"adapter": ApplicantListAdapter()}
    build_state_machine().run(context)
    applicants = context["last_result"]["applicants"]
    return {"applicants": applicants, "table": _render_table(applicants)}
