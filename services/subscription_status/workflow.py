from __future__ import annotations

import pathlib
from typing import Any

from framework.llm.openai_client import complete
from framework.prompts.store import PromptStore
from framework.registry.decorators import guardrail, judged, registry, tool, workflow_step
from framework.workflow.state_machine import StateMachine
from services.subscription_status.adapter import SubscriptionStatusAdapter

PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"
FRAMEWORK_PROMPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "framework" / "prompts"
prompt_store = PromptStore(base_dir=FRAMEWORK_PROMPTS_DIR)


@workflow_step(
    order=1,
    source="legacy_subscription_system",
    max_retries=5,
    next={
        "심사중": "fetch_status",  # 순환: 재조회
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


@workflow_step(order=2, next={"자동승인": "DONE", "수동검토": "DONE"})
@judged(choices=("자동승인", "수동검토"))
def manual_review(context: dict[str, Any]) -> str:
    prompt = prompt_store.compose("manual_review", PROMPTS_DIR)
    user = (
        f"신청자 ID: {context['applicant_id']}\n"
        f"레거시 조회 결과: {context['last_result']}\n\n"
        "위 정보를 바탕으로 '자동승인' 또는 '수동검토' 중 하나만 정확히 출력하라."
    )
    return complete(system=prompt, user=user)


def build_state_machine() -> StateMachine:
    return StateMachine(registry=registry, entry="fetch_status")


@tool(
    name="subscription_status",
    description=(
        "청약 신청자의 진행상황을 조회한다. 내부적으로 상태 재조회/재제출대기/"
        "수동검토까지 이어지는 고정 서브 workflow 전체를 하나의 capability로 실행한다."
    ),
)
@guardrail(
    output_schema={
        "applicant_id": Any,
        "status": {"choices": ["접수완료", "서류미비", "심사중", "승인완료", "보류"]},
        "status_confidence": {"choices": ["confirmed", "inferred"]},
        "region": Any,
    }
)
def subscription_status(applicant_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"applicant_id": applicant_id, "adapter": SubscriptionStatusAdapter()}
    build_state_machine().run(context)
    return context["last_result"]
