from __future__ import annotations

from typing import Any

from framework.harness.guardrail import optional
from framework.registry.decorators import guardrail, human_action, registry, tool, workflow_step
from framework.workflow.state_machine import AwaitingHumanAction, StateMachine
from services.subscription_status.adapter import SubscriptionStatusAdapter


@workflow_step(
    order=1,
    source="legacy_subscription_system",
    max_retries=5,
    next={
        "심사중": "fetch_status",  # 순환: 재조회
        "접수완료": "DONE",
        "서류미비": "DONE",
        "승인완료": "DONE",
        "미확인": "manual_review",  # confidence != confirmed → 사람 판단으로
    },
)
def fetch_status(context: dict[str, Any]) -> str:
    adapter: SubscriptionStatusAdapter = context["adapter"]
    result = adapter.execute(applicant_id=context["applicant_id"])
    context["last_result"] = result
    if result["status_confidence"] != "confirmed":
        return "미확인"
    return result["status"]


MANUAL_REVIEW_CHOICES = ("승인", "반려", "서류추가요청")
# 예전 @judged 시절엔 "자동승인"/"수동검토" 이분법이었다 — AI가 "사람한테 넘길지 말지"를
# 판단했으므로 그 이름이 맞았다. 지금은 이 노드 자체가 이미 사람이 보고 있는 지점이라
# "자동승인"(모순: 사람이 고르는데 자동?)/"수동검토"(모순: 이미 수동검토 중인데 수동검토로?)가
# 더 이상 말이 안 된다 — 사람이 실제로 내리는 결정(승인/반려)으로 바꿨다.


@workflow_step(order=2, next={"승인": "DONE", "반려": "DONE", "서류추가요청": "DONE"})
@human_action(
    choices=MANUAL_REVIEW_CHOICES,
    payload_schemas={"서류추가요청": {"field": Any}},
)
def manual_review(context: dict[str, Any]) -> dict[str, Any]:
    human_action_input = context.get("human_action")
    if human_action_input is None:
        # 사람의 답이 아직 없다 — StateMachine.run()이 이 예외를 잡아 실행을 멈추고
        # choices를 그대로 호출자에게 돌려준다(에러가 아니라 대기 신호).
        raise AwaitingHumanAction(choices=MANUAL_REVIEW_CHOICES)
    context["last_result"]["manual_review_decision"] = human_action_input
    return human_action_input


def build_state_machine() -> StateMachine:
    return StateMachine(registry=registry, entry="fetch_status")


SUBSCRIPTION_STATUS_OUTPUT_SCHEMA = {
    "applicant_id": Any,
    "status": {"choices": ["접수완료", "서류미비", "심사중", "승인완료", "보류"]},
    "status_confidence": {"choices": ["confirmed", "inferred"]},
    "region": Any,
    # human_action이 action+payload를 이미 bounded choices/payload_schemas로 검증했으므로
    # 여기서는 존재 여부만 확인한다 — action마다 payload 모양이 달라 discriminated union을
    # guardrail 스키마 문법 하나로 표현할 수 없다.
    "manual_review_decision": optional(Any),
}


@tool(
    name="subscription_status",
    description=(
        "청약 신청자의 진행상황을 조회한다. 내부적으로 상태 재조회/재제출대기/"
        "수동검토까지 이어지는 고정 서브 workflow 전체를 하나의 capability로 실행한다."
    ),
)
@guardrail(output_schema=SUBSCRIPTION_STATUS_OUTPUT_SCHEMA)
def subscription_status(applicant_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"applicant_id": applicant_id, "adapter": SubscriptionStatusAdapter()}
    build_state_machine().run(context)
    return context["last_result"]
