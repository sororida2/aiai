from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

from agents import Agent, Runner
from agents.exceptions import UserError
from dotenv import load_dotenv

import services
from framework.harness.guardrail import output_schema_guardrail
from framework.harness.logging_setup import configure_logging, get_logger
from framework.prompts.store import PromptStore
from framework.registry.decorators import registry
from framework.registry.discovery import discover_services
from framework.workflow.state_machine import AwaitingHumanAction, StateMachine

logger = get_logger("main")

load_dotenv()
configure_logging()  # LOG_LEVEL 환경변수(기본 INFO) — discover_services()보다 먼저 호출해야 그 로그도 잡힌다

FRAMEWORK_DIR = pathlib.Path(__file__).parent / "framework"

discover_services(services)  # services/<name>/workflow.py를 전부 import해 등록 트리거
registry.validate()  # 등록된 tool 카탈로그 참조 무결성 검사 (workflow_step/next는 각 파일이 import 시점에 자체 검증)


def build_triage_agent() -> Agent:
    """예전 `Orchestrator`/`AgentRunner`(choose_tool/extract_arguments/rewrite_request)를
    전부 대신한다 — tool 선택, 누락 인자 자연어 추출, 고정 조합 없는 tool 간 동적 연결까지
    SDK의 `Agent`+`Runner`가 기본 동작으로 처리한다.

    지금은 flat 구조(모든 tool을 하나의 Agent에)로 시작한다 — 지금 8개 tool이 아직 도메인별로
    뚜렷하게 나뉘지 않아서, handoff 트리(Triage Agent → Service Agent들)로 미리 쪼개는 건
    과한 구조다. 도메인이 늘어나 실제로 나눌 필요가 생기면 그때 handoffs=[...]를 도입한다.

    `tool_use_behavior`는 **기본값을 그대로 쓴다**(`run_llm_again`) — 처음엔
    `"stop_on_first_tool"`로 시작했는데, 이게 "첫 tool 호출 즉시 멈춘다"는 뜻이라 `ip_geolocation`
    → `university_search`처럼 tool을 이어서 불러야 하는 요청에서 **두 번째 tool 호출 자체가
    안 일어나는** 걸 Windows 실측으로 확인했다(§ ARCHITECTURE.md의 SDK 마이그레이션 절). 페어마다
    고정 composition tool을 만드는 임시방편도 시도했지만 사용자가 "질문이 바뀌면(예: 통화로)
    또 새로 만들어야 하지 않냐"고 지적해서 되돌렸다 — 근본적으로 tool_use_behavior 자체를
    고쳐야 하는 문제였다. 구조화된 dict를 그대로 돌려받는 건(모델이 재요약/재작성하지 않고)
    `tool_use_behavior`가 아니라 `_extract_last_tool_output()`이 `result.new_items`에서
    tool의 원본 반환값을 직접 꺼내는 방식으로 해결한다(아래).
    """
    prompt_store = PromptStore(base_dir=FRAMEWORK_DIR / "prompts")
    return Agent(
        name="triage",
        instructions=prompt_store.common_prompt(),
        tools=registry.function_tools(),
        output_guardrails=[output_schema_guardrail],
    )


def handle(request: str) -> dict[str, Any]:
    """요청 하나의 진입점. 내부적으로 `Runner.run_sync(triage_agent, request)`가
    tool 선택부터 인자 채우기, 필요하면 여러 tool을 잇는 것까지 전부 수행한다.
    """
    logger.info("request received: %r", request)
    agent = build_triage_agent()
    try:
        result = Runner.run_sync(agent, request)
    except AwaitingHumanAction as e:
        return _paused_response(e)
    except UserError as e:
        # failure_error_function=None(§ registry/decorators.py)은 예외를 삼키지 않고
        # 밖으로 전파시키긴 하는데, SDK가 원본을 그대로 주지 않고 자기 UserError로 한 번
        # 감싸서 던진다(Windows 실측으로 확인, __cause__에 원본이 그대로 남아있음). 진짜
        # AwaitingHumanAction이면 풀어서 처리하고, 그게 아니면(진짜 tool 버그 등) 다시 던진다.
        if isinstance(e.__cause__, AwaitingHumanAction):
            return _paused_response(e.__cause__)
        raise

    _log_run_items(result)
    output = _extract_last_tool_output(result)
    logger.info("request done: result=%s", output)
    return output


def _extract_last_tool_output(result: Any) -> dict[str, Any]:
    """모델이 마지막으로 부른 tool의 원본 반환값을 그대로 돌려준다 — `result.final_output`
    (모델이 생성한 텍스트)을 안 쓴다.

    `tool_use_behavior`를 기본값(모델이 필요하면 tool을 여러 번 이어 부를 수 있음)으로 둔
    대신, "구조화된 dict를 모델이 재요약하지 않고 그대로" 받는 건 이 함수가 대신 보장한다 —
    `result.new_items`에서 마지막 `ToolCallOutputItem`을 직접 찾아 그 안의 값을 쓴다.
    "가장 마지막에 부른 tool의 결과가 사용자가 원한 답"이라는 전제인데, 순차 체이닝에서는
    합리적이지만 진짜 복합 의도(예: 휴일 목록 **그리고** 대학 목록을 동시에 원하는 것)는
    여전히 못 푼다 — 그건 이 함수가 아니라 `limitation.md`의 "증거 3"이 다루는 별개 문제다.
    """
    tool_outputs = [item for item in result.new_items if type(item).__name__ == "ToolCallOutputItem"]
    if not tool_outputs:
        raise ValueError(
            f"tool을 하나도 안 부르고 끝났다 — final_output={result.final_output!r}. 이 프로젝트의 "
            "모든 tool은 구조화된 dict를 반환하는 게 계약이라, tool 호출 없이 끝나면 그 계약을 "
            "못 지킨 것이므로 명확히 실패시킨다."
        )
    output = tool_outputs[-1].output
    if isinstance(output, str):
        # tool의 반환값이 API로 오가는 과정에서 문자열로 바뀐다 — JSON(큰따옴표)일 수도,
        # 파이썬 repr(작은따옴표)일 수도 있어서 둘 다 시도한다(§ 위 result.final_output에서
        # 똑같은 문제를 실측으로 확인했던 것과 같은 이유).
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            output = ast.literal_eval(output)
    return output


def _log_run_items(result: Any) -> None:
    """이 run 안에서 실제로 무슨 일이 일어났는지(tool을 몇 번, 어떤 순서로 불렀는지) 로그로
    남긴다. `tool_use_behavior="stop_on_first_tool"`이 두 번째 tool 호출 자체를 막아버리는
    경우, 지금까지는 "그다음 tool의 'Invoking tool' 로그가 안 보인다"는 **부재**로만
    알아채야 해서 놓치기 쉬웠다(`ip_geolocation` → `university_search`가 실제로 이렇게
    놓친 적 있음, § ARCHITECTURE.md의 SDK 마이그레이션 절). `new_items`의 각 항목 타입을
    그대로 로깅해서, run이 몇 번째 항목·어떤 타입에서 멈췄는지 명시적으로 보이게 한다.
    """
    try:
        item_types = [type(item).__name__ for item in result.new_items]
    except AttributeError:
        logger.debug("run items: result.new_items를 못 읽음 (SDK 버전에 따라 속성이 다를 수 있음)")
        return
    logger.info("run items (%d): %s", len(item_types), item_types)


def resume(tool_name: str, context: dict[str, Any], step: str, action: dict[str, Any]) -> dict[str, Any]:
    """`handle()`이 돌려준 일시정지 응답("context"/"step")에 사람의 answer를 채워 넣고,
    멈췄던 지점부터 이어서 실행한다.

    `Runner.run()`(SDK의 triage 루프)을 다시 타지 않는다 — 어떤 tool의 어떤 step에서
    멈췄는지 이미 알고 있으므로 모델의 라우팅 판단이 다시 필요 없고, SDK의 Session이
    "죽었던 tool 호출을 정확히 그 지점부터 재개"하는 걸 보장해주는지도 검증되지 않았다
    (§ ARCHITECTURE.md의 SDK 마이그레이션 절). 예전 `Orchestrator.resume()`과 완전히
    같은 방식 — `WorkflowRegistry`/`StateMachine`을 직접 호출한다.
    """
    tool_spec = registry.tool_for(tool_name)
    if tool_spec.workflow_registry is None:
        raise ValueError(
            f"tool '{tool_name}'에는 workflow_registry가 없다 — @tool(workflow_registry=...)로 "
            "연결된 tool만 resume() 대상이 될 수 있다"
        )

    context["human_action"] = action
    logger.info("resuming: tool=%s step=%s action=%s", tool_name, step, action)

    try:
        StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)
    except AwaitingHumanAction as e:
        return _paused_response(e)

    result = context["last_result"]
    logger.info("resume done: tool=%s result_keys=%s", tool_name, list(result))
    return result


def _paused_response(e: AwaitingHumanAction) -> dict[str, Any]:
    logger.info("request paused: tool=%s step=%s choices=%s", e.tool_name, e.step, e.choices)
    return {
        "status": "awaiting_human_action",
        "tool": e.tool_name,  # @tool(pausable=True)가 자동으로 찍어둔 것 (§ registry/decorators.py)
        "step": e.step,
        "choices": list(e.choices),
        "context": e.context,
    }


if __name__ == "__main__":
    #print(handle("applicant_list 보여줘")["table"])
    #print(handle("서울 날씨 알려줘"))  # weather 단독 — 아직 안 돌려본 경로
    #print(handle("미국에 있는 대학 5개만 보여줘"))
    #print(handle("143.248.1.1의 위치한 나라를 알려줘"))
    print(handle("그리스의 2026년 공휴일을 알려줘"))
    #print(handle("미국 달러를 원화, 유로, 일본 엔으로 환전하면 얼마야?"))
    #print(handle("A123 신청자의 진행상황과 그 지역 날씨를 알려줘"))
    #print(handle("143.248.1.1이 위치한 나라의 대학교 5개를 알려줘"))  # 고정 조합이 없는 두 tool을 동적으로 이어야 하는 경우
