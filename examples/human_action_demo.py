"""human_action 기반 human-in-the-loop 예시.

subscription_status의 manual_review 단계가 실제로 사람의 입력을 기다렸다가
재개되는 과정을 터미널에서 확인한다. 엔진 조립(discover_services,
registry.validate(), build_orchestrator)은 main.py 것을 그대로 재사용하고,
여기서는 pause -> 사람 입력 -> resume 흐름만 보여준다.

레거시 어댑터가 아직 스텁이라(SubscriptionStatusAdapter.call()이 항상
status_code="20"만 반환) manual_review까지 도달하려면 status_code "99"
(inferred)가 필요하다 — 실제 레거시 연동이 붙기 전까지는 이 데모에서만
어댑터를 몽키패치해서 그 경로를 재현한다.

실행: python examples/human_action_demo.py
"""

from __future__ import annotations

from main import build_orchestrator
from services.subscription_status.adapter import SubscriptionStatusAdapter


def _simulate_inferred_status(self, *, applicant_id: str) -> dict:
    return {"applicant_id": applicant_id, "status_code": "99", "region": "Seoul"}


def main() -> None:
    SubscriptionStatusAdapter.call = _simulate_inferred_status
    orchestrator = build_orchestrator()

    result = orchestrator.handle("subscription_status 조회해줘", applicant_id="A123")
    if result.get("status") != "awaiting_human_action":
        print("사람의 판단이 필요 없었습니다:", result)
        return

    print(f"\n[사람 확인 필요] tool={result['tool']} step={result['step']}")
    print("가능한 action:", ", ".join(result["choices"]))

    while True:
        action = input("고를 action을 입력하세요: ").strip()
        payload: dict[str, str] = {}
        if action == "서류추가요청":
            payload["field"] = input("어떤 서류가 더 필요한가요?: ").strip()
        try:
            resumed = orchestrator.resume(
                result["tool"], result["context"], result["step"], {"action": action, **payload}
            )
        except ValueError as e:
            print(f"입력이 올바르지 않습니다: {e}\n다시 골라주세요.")
            continue
        break

    print("\n최종 결과:", resumed)


if __name__ == "__main__":
    main()
