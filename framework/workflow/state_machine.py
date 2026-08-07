from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from framework.harness.logging_setup import get_logger
from framework.harness.tracing import tracer
from framework.workflow.registry import WorkflowRegistry, WorkflowStepSpec

logger = get_logger("state_machine")


class MaxRetriesExceeded(Exception):
    pass


class AwaitingHumanAction(Exception):
    """human_action 노드가 아직 사람의 답을 못 받아 실행을 멈췄다는 신호.

    에러가 아니라 "다음 턴에 답을 달라"는 정상적인 일시정지 신호다 — raise한
    쪽(예: manual_review)은 step 이름을 몰라도 되도록 choices만 채워서 던지고,
    StateMachine.run()이 잡아 step/context를 채운 뒤 다시 던진다. 이 예외가
    바깥(Orchestrator)까지 그대로 전파되면 호출자가 "멈췄다"는 걸 구분해 처리한다.
    """

    def __init__(self, choices: tuple[str, ...]) -> None:
        super().__init__(f"awaiting human action from {choices}")
        self.choices = choices
        self.step: str | None = None
        self.context: dict[str, Any] | None = None
        self.tool_name: str | None = None
        """`@tool(pausable=True)` 래퍼가 자동으로 채운다(§ registry/decorators.py) — raise한
        쪽(manual_review 등)은 자기가 어느 tool에 속해 있는지 몰라도 된다는 원칙을 그대로
        유지한다. `main.py`의 resume()이 어떤 tool의 workflow_registry를 찾을지 이 값으로 안다."""


TERMINAL = "DONE"

RETRY_COUNTS_KEY = "_step_retry_counts"
"""context 안에 "완료된" 스텝 실행 횟수를 세는 프레임워크 예약 키.

StateMachine.run()의 로컬 변수가 아니라 context에 두는 이유: Orchestrator.resume()은
멈출 때마다 새 StateMachine 인스턴스로 run()을 다시 호출한다(그때그때 로컬 변수는
초기화됨) — 순환이 human_action처럼 멈추는 노드를 거치면, 카운트가 resume 경계를
넘어 살아남아야 재시도 제한이 실제로 지켜진다. context는 resume()에 그대로
전달되는 유일한 것이라 여기 둔다. 스텝 작성자는 이 키를 직접 건드릴 필요 없다 —
run()이 자동으로 읽고 쓴다.

"완료된" 실행만 센다는 게 중요하다 — `spec.func(context)`가 예외 없이 outcome을
반환했을 때만 카운트를 올린다. 그래서 사람이 human_action의 bounded choices 밖의
값을 입력해 ValueError가 나거나(§ human_action) 아직 답이 없어 AwaitingHumanAction으로
멈춘 경우는 카운트되지 않는다 — "사람이 입력을 몇 번 틀렸는가"는 자동 순환 폭주와
무관한 문제라 같은 예산을 쓰면 안 된다는 판단.
"""


@dataclass
class StateMachine:
    """청약진행상황처럼 순서·분기·순환이 이미 알려진 도메인을 위한 고정 파이프라인.

    @workflow_step의 next 맵이 결정론적 분기/순환을 코드로 못박고,
    judged 함수만 실행 시점에 모델 판단으로 넘어간다(bounded choices는
    @judged 데코레이터가 강제).
    """

    registry: WorkflowRegistry
    entry: str

    def steps(self) -> dict[str, WorkflowStepSpec]:
        return self.registry.steps()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        steps = self.steps()
        current = self.entry
        visits: dict[str, int] = context.setdefault(RETRY_COUNTS_KEY, {})
        logger.info("state machine start: entry='%s'", self.entry)

        while current is not None:
            spec = steps.get(current)
            if spec is None:
                logger.error("unknown workflow step '%s'", current)
                raise KeyError(f"unknown workflow step '{current}'")

            # self-loop(fetch_status처럼 자기 자신으로 도는 것)뿐 아니라, 서로 다른
            # 여러 스텝을 거치는 순환(예: evaluator가 이전 스텝으로 되돌리는 것)까지
            # 전부 여기서 막는다 — "next_step == current"일 때만 세던 예전 방식은
            # 2개 이상 스텝을 왕복하는 순환을 전혀 감지하지 못했다. 체크는 "이미 완료된
            # 횟수"만 보고 실행 전에 미리 막는다 — 한도를 넘은 실행을 실제로 한 번 더
            # 돌리고 나서야 막는 낭비(레거시 API 재호출 등)를 피한다.
            completed = visits.get(current, 0)
            if completed >= spec.max_retries + 1:
                logger.error(
                    "step '%s' exceeded max_retries=%d (completed %d times already)", current, spec.max_retries, completed
                )
                raise MaxRetriesExceeded(
                    f"step '{current}' exceeded max_retries={spec.max_retries} (completed {completed} times already)"
                )
            if completed:
                logger.debug("step '%s' re-entered (completed %d/%d so far)", current, completed, spec.max_retries + 1)

            with tracer.span(name=current, kind="step"):
                try:
                    outcome = spec.func(context)
                except AwaitingHumanAction as e:
                    e.step = current
                    e.context = context
                    logger.info("state machine paused: step='%s' awaiting human action from %s", current, e.choices)
                    raise
                # ValueError(human_action의 bounded choices/payload_schemas 위반 등)는 여기서
                # 잡지 않고 그대로 전파한다 — "실패한 시도"라 완료 카운트에 넣지 않는다.

            visits[current] = completed + 1

            if spec.next is None:
                logger.info("state machine done: step='%s' (no next map)", current)
                return context

            # outcome이 spec.next의 키 밖이면 @workflow_step의 wrapper가 이미 그 자리에서
            # ValueError를 던졌을 것이므로, 여기 도달했다면 outcome은 항상 유효한 키다.
            next_step = spec.next[outcome]
            logger.info("step '%s' -> outcome=%r -> next='%s'", current, outcome, next_step)

            if next_step == TERMINAL:
                logger.info("state machine done: step='%s'", current)
                return context

            current = next_step

        return context
