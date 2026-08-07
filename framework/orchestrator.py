from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from framework.harness.guardrail import GuardrailChain
from framework.harness.logging_setup import get_logger
from framework.harness.tracing import tracer
from framework.prompts.store import PromptStore
from framework.registry.decorators import ToolRegistry
from framework.workflow.state_machine import AwaitingHumanAction, StateMachine

logger = get_logger("orchestrator")

MAX_RESOLUTION_DEPTH = 3
"""사전에 고정 조합으로 안 묶인 tool들을 그때그때 이어야 할 때(§ Orchestrator._resolve_missing_via_other_tool)
재작성-재시도를 몇 번까지 허용할지의 상한. 모델이 계속 못 이으면 이 횟수 안에 원래 흐름으로
돌아가 정직하게(TypeError로) 실패한다 — WorkflowRegistry의 max_retries와 같은 이유(무한 루프 방지)의
Orchestrator 레벨 버전."""


class AgentRunner(Protocol):
    """LLM 라우팅 판단 자체는 SDK(OpenAI Agents SDK 등)의 몫.

    오케스트레이터 엔진은 특정 SDK에 커플링되지 않도록 이 Protocol만 요구한다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str: ...

    def extract_arguments(
        self, request: str, tool_name: str, input_schema: dict[str, Any], known: dict[str, Any]
    ) -> dict[str, Any]:
        """자연어 request에서 아직 안 채워진 파라미터 값을 최대한 추측해서 돌려준다.

        `input_schema`는 아직 `known`(호출자가 이미 명시적으로 준 kwargs)에 없는
        필드만 담고 있다 — 이미 있는 값은 다시 추측 대상이 아니다. 확신 없는
        필드는 결과 dict에서 그냥 빼면 된다(억지로 채우지 않는다) — 그러면
        `spec.func(**kwargs)` 호출 시 파이썬이 "필수 인자 없음"으로 바로 실패해서,
        조용히 잘못된 값이 들어가는 것보다 낫다.
        """

    def rewrite_request(self, request: str, learned: dict[str, Any]) -> str:
        """다른 tool을 불러서 알아낸 사실(learned)을 원래 요청에 반영해 자연어로 다시 쓴다.

        예: "143.248.1.1이 위치한 나라의 대학 5개" + {"country": "United States"}
        -> "미국의 대학 5개를 알려줘". 사전에 고정 조합(예: `subscription_weather_flow`)으로
        묶어두지 않은 두 tool을 그때그때 이어야 할 때, `Orchestrator._resolve_missing_via_other_tool()`이
        이걸 불러 요청 텍스트 자체를 갱신한 뒤 처음부터(`choose_tool()`부터) 다시 태운다 —
        값을 kwargs에 직접 꽂는 게 아니라 "자연어가 base"라는 원칙을 그대로 지킨다.
        """


@dataclass
class Orchestrator:
    registry: ToolRegistry
    prompt_store: PromptStore
    agent_runner: AgentRunner

    def __post_init__(self) -> None:
        self.guardrails = GuardrailChain(self.registry)

    def _catalog(self) -> list[dict[str, Any]]:
        return [
            {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
            for spec in self.registry.tools().values()
        ]

    def handle(self, request: str, **kwargs: Any) -> dict[str, Any]:
        return self._handle(request, kwargs, depth=0)

    def _handle(self, request: str, kwargs: dict[str, Any], depth: int) -> dict[str, Any]:
        logger.info("request received: %r kwargs=%s depth=%d", request, kwargs, depth)
        with tracer.start_trace(name="orchestrator") as trace:
            prompt = self.prompt_store.common_prompt()
            tool_name = self.agent_runner.choose_tool(request, self._catalog(), prompt)
            logger.info("tool selected: %s (via %s)", tool_name, type(self.agent_runner).__name__)

            spec = self.registry.tools().get(tool_name)
            if spec is None:
                logger.error("agent chose unregistered tool '%s'", tool_name)
                raise KeyError(f"agent chose unregistered tool '{tool_name}'")

            # 호출자가 이미 명시적으로 준 kwargs에 없는 필드만 자연어에서 추측해 채운다 —
            # 전부 이미 있으면(예전처럼 main.py가 kwargs를 다 채워서 부르는 경우) 이 단계는
            # 아예 안 타므로 기존 호출 방식과 100% 호환된다.
            missing_schema = {name: type_ for name, type_ in spec.input_schema.items() if name not in kwargs}
            if missing_schema:
                extracted = self.agent_runner.extract_arguments(request, tool_name, missing_schema, kwargs)
                logger.info("arguments extracted from request: %s", extracted)
                kwargs = {**extracted, **kwargs}  # 호출자가 준 값이 항상 우선(추측값을 덮어쓰지 못함)

                # 요청 텍스트 자체에는 없어서 못 채운 필드가 남았다 — 사전에 고정 조합으로
                # 안 묶인 다른 tool을 불러 알아낸 뒤, 그 사실을 반영해 요청을 다시 써서
                # 처음부터(choose_tool부터) 재시도한다. depth로 무한 루프를 막는다.
                still_missing = [name for name in missing_schema if name not in kwargs]
                if still_missing and depth < MAX_RESOLUTION_DEPTH:
                    rewritten = self._resolve_missing_via_other_tool(request, tool_name, still_missing)
                    if rewritten is not None:
                        logger.info("request rewritten to resolve %s: %r -> %r", still_missing, request, rewritten)
                        return self._handle(rewritten, kwargs, depth + 1)
                elif still_missing:
                    logger.warning(
                        "gave up resolving %s for tool '%s' after depth=%d — will fail on missing argument",
                        still_missing, tool_name, depth,
                    )

            with tracer.span(name=tool_name, kind="tool"):
                try:
                    result = self.guardrails.run(tool_name, lambda: spec.func(**kwargs), kwargs)
                except AwaitingHumanAction as e:
                    return self._paused_response(tool_name, e)

            logger.info("request done: tool=%s result_keys=%s", tool_name, list(result))
            return result

    def _resolve_missing_via_other_tool(self, request: str, blocked_tool: str, missing_fields: list[str]) -> str | None:
        """요청 텍스트에서 못 찾은 필드를, 다른 tool을 불러서 알아낸 뒤 요청을 다시 쓴다.

        `subscription_weather_flow`처럼 사람이 미리 고정해둔 조합이 없는 두 tool을
        그때그때 이어야 하는 경우를 위한 마지막 수단이다. 적당한 tool을 못 찾거나,
        찾은 tool 호출 자체가 실패하면 `None`을 돌려주고 — 그러면 `_handle()`은 그냥
        원래 흐름대로 진행해서 필수 인자 누락으로 정직하게 실패한다(조용히 삼키지 않음).
        `AwaitingHumanAction`은 예외적으로 그대로 전파한다 — 이건 "이 시도가 실패했다"가
        아니라 "사람 판단이 필요하다"는 별개의 신호라서다.
        """
        field_hint = ", ".join(missing_fields)
        sub_request = f"다음 정보를 알아내려면 어떤 tool을 써야 하나: {field_hint} (원래 요청: {request!r})"
        try:
            sub_tool_name = self.agent_runner.choose_tool(sub_request, self._catalog(), self.prompt_store.common_prompt())
        except ValueError:
            logger.info("no supporting tool found for missing fields %s", missing_fields)
            return None
        if sub_tool_name == blocked_tool:
            logger.info("supporting tool search returned the same blocked tool '%s' — giving up", blocked_tool)
            return None

        sub_spec = self.registry.tools().get(sub_tool_name)
        if sub_spec is None:
            return None

        sub_kwargs = self.agent_runner.extract_arguments(request, sub_tool_name, sub_spec.input_schema, {})
        logger.info("resolving via supporting tool '%s' with args %s", sub_tool_name, sub_kwargs)
        try:
            sub_result = self.guardrails.run(sub_tool_name, lambda: sub_spec.func(**sub_kwargs), sub_kwargs)
        except AwaitingHumanAction:
            raise
        except Exception as e:
            logger.warning("supporting tool '%s' failed while resolving %s: %s", sub_tool_name, missing_fields, e)
            return None

        return self.agent_runner.rewrite_request(request, sub_result)

    def resume(self, tool_name: str, context: dict[str, Any], step: str, action: dict[str, Any]) -> dict[str, Any]:
        """`handle()`이 돌려준 일시정지 응답("context"/"step")에 사람의 answer를
        채워 넣고, 멈췄던 지점부터 이어서 실행한다.

        같은 대화 세션 안에서 호출자가 paused response의 context를 그대로 들고
        있다가 넘겨주는 걸 전제로 한다 — 별도 영속화 계층(세션 저장소 등)은 아직
        없다. `context["last_result"]`를 최종 반환값으로 삼는 관례에 기대므로,
        `subscription_status`처럼 그 관례를 따르는 tool에서만 쓸 수 있다
        (`subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool은
        아직 대상이 아니다).
        """
        tool_spec = self.registry.tools().get(tool_name)
        if tool_spec is None or tool_spec.workflow_registry is None:
            raise ValueError(
                f"tool '{tool_name}'에는 workflow_registry가 없다 — @tool(workflow_registry=...)로 "
                "연결된 tool만 resume() 대상이 될 수 있다"
            )

        context["human_action"] = action
        logger.info("resuming: tool=%s step=%s action=%s", tool_name, step, action)

        def run_from_paused() -> dict[str, Any]:
            StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)
            return context["last_result"]

        with tracer.start_trace(name="orchestrator-resume"):
            with tracer.span(name=tool_name, kind="tool"):
                try:
                    result = self.guardrails.run(tool_name, run_from_paused, context)
                except AwaitingHumanAction as e:
                    return self._paused_response(tool_name, e)

            logger.info("resume done: tool=%s result_keys=%s", tool_name, list(result))
            return result

    def _paused_response(self, tool_name: str, e: AwaitingHumanAction) -> dict[str, Any]:
        logger.info("request paused: tool=%s step=%s choices=%s", tool_name, e.step, e.choices)
        return {
            "status": "awaiting_human_action",
            "tool": tool_name,
            "step": e.step,
            "choices": list(e.choices),
            "context": e.context,
        }
