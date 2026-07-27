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


class AgentRunner(Protocol):
    """LLM 라우팅 판단 자체는 SDK(OpenAI Agents SDK 등)의 몫.

    오케스트레이터 엔진은 특정 SDK에 커플링되지 않도록 이 Protocol만 요구한다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str: ...


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
        logger.info("request received: %r kwargs=%s", request, kwargs)
        with tracer.start_trace(name="orchestrator") as trace:
            prompt = self.prompt_store.common_prompt()
            tool_name = self.agent_runner.choose_tool(request, self._catalog(), prompt)
            logger.info("tool selected: %s (via %s)", tool_name, type(self.agent_runner).__name__)

            spec = self.registry.tools().get(tool_name)
            if spec is None:
                logger.error("agent chose unregistered tool '%s'", tool_name)
                raise KeyError(f"agent chose unregistered tool '{tool_name}'")

            with tracer.span(name=tool_name, kind="tool"):
                try:
                    result = self.guardrails.run(tool_name, lambda: spec.func(**kwargs), kwargs)
                except AwaitingHumanAction as e:
                    return self._paused_response(tool_name, e)

            logger.info("request done: tool=%s result_keys=%s", tool_name, list(result))
            return result

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
        context["human_action"] = action
        logger.info("resuming: tool=%s step=%s action=%s", tool_name, step, action)

        def run_from_paused() -> dict[str, Any]:
            StateMachine(registry=self.registry, entry=step).run(context)
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
