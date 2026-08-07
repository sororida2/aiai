"""human_action 기반 human-in-the-loop 예시.

subscription_status의 manual_review 단계가 실제로 사람의 입력을 기다렸다가
재개되는 과정을 터미널에서 확인한다. 엔진 조립(discover_services,
registry.validate(), build_triage_agent)은 main.py 것을 그대로 재사용하고,
여기서는 pause -> 사람 입력 -> resume 흐름만 보여준다.

레거시 어댑터가 아직 스텁이라(SubscriptionStatusAdapter.call()이 항상
status_code="20"만 반환) manual_review까지 도달하려면 status_code "99"
(inferred)가 필요하다 — 실제 레거시 연동이 붙기 전까지는 이 데모에서만
어댑터를 몽키패치해서 그 경로를 재현한다.

실행: python examples/human_action_demo.py
"""

from __future__ import annotations

import pathlib
import sys

# `python examples/human_action_demo.py`로 직접 실행하면 파이썬이 이 파일이 있는
# examples/ 디렉토리만 sys.path에 넣는다(cwd나 프로젝트 루트가 아니라) — 그래서
# 프로젝트 루트의 main.py를 못 찾고 ModuleNotFoundError가 난다. 이 파일 docstring이
# "직접 실행"을 문서화하고 있으니, 실행 방식과 무관하게 항상 되도록 프로젝트 루트를
# 명시적으로 sys.path에 추가한다.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from main import handle, resume  # noqa: E402
from services.subscription_status.adapter import SubscriptionStatusAdapter  # noqa: E402


def _simulate_inferred_status(self, *, applicant_id: str) -> dict:
    return {"applicant_id": applicant_id, "status_code": "99", "region": "Seoul"}


def main() -> None:
    SubscriptionStatusAdapter.call = _simulate_inferred_status

    result = handle("A123 신청자의 subscription_status 조회해줘")
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
            resumed = resume(result["tool"], result["context"], result["step"], {"action": action, **payload})
        except ValueError as e:
            print(f"입력이 올바르지 않습니다: {e}\n다시 골라주세요.")
            continue
        break

    print("\n최종 결과:", resumed)


if __name__ == "__main__":
    main()
