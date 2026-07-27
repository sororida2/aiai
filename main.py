from __future__ import annotations

import os
import pathlib
from typing import Any

from dotenv import load_dotenv

import services
from framework.llm.openai_client import complete
from framework.orchestrator import Orchestrator
from framework.prompts.store import PromptStore
from framework.registry.decorators import registry
from framework.registry.discovery import discover_services

load_dotenv()

FRAMEWORK_DIR = pathlib.Path(__file__).parent / "framework"

discover_services(services)  # services/<name>/workflow.py를 전부 import해 등록 트리거
registry.validate()  # 등록된 tool/workflow_step/judged/guardrail 사이 참조 무결성 검사


class FirstMatchRunner:
    """OpenAI Agents SDK Agent/Runner를 대체하는 스캐폴드용 스텁. OPENAI_API_KEY가
    없을 때(오프라인 샘플 테스트) build_orchestrator()의 기본 fallback으로 쓰인다.

    실제 배포 시에는 이 Protocol 구현체만 SDK 기반으로 교체하면 되고,
    orchestrator.py의 라우팅 엔진 코드는 건드리지 않는다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str:
        # 이름이 긴 tool부터 검사한다 — 짧은 이름이 긴 이름의 substring인 경우
        # (예: "weather"가 "subscription_weather_flow" 안에 포함됨) 오탐을 막기 위함.
        for entry in sorted(tool_catalog, key=lambda e: len(e["name"]), reverse=True):
            if entry["name"] in request:
                return entry["name"]
        raise ValueError(f"no tool matched request: {request!r}")


class OpenAIRunner:
    """AgentRunner Protocol의 OpenAI 기반 구현체.

    orchestrator.py는 이 클래스를 모른다 — Protocol에만 의존하므로 여기 교체는
    main.py(조립 지점)에서만 일어난다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str:
        names = {entry["name"] for entry in tool_catalog}
        catalog_text = "\n".join(f"- {entry['name']}: {entry['description']}" for entry in tool_catalog)
        user = (
            f"등록된 tool 목록:\n{catalog_text}\n\n"
            f"요청: {request}\n\n"
            "위 tool 중 이 요청에 가장 적합한 tool의 name만 정확히 출력하라. "
            "적합한 tool이 없으면 NONE이라고만 출력하라."
        )
        choice = complete(system=prompt, user=user)
        if choice not in names:
            raise ValueError(f"no tool matched request: {request!r} (model returned {choice!r})")
        return choice


def build_orchestrator() -> Orchestrator:
    agent_runner: Any = OpenAIRunner() if os.environ.get("OPENAI_API_KEY") else FirstMatchRunner()
    return Orchestrator(
        registry=registry,
        prompt_store=PromptStore(base_dir=FRAMEWORK_DIR / "prompts"),
        agent_runner=agent_runner,
    )


if __name__ == "__main__":
    orchestrator = build_orchestrator()
    print(orchestrator.handle("subscription_status 조회해줘", applicant_id="A123"))
    print(orchestrator.handle("weather 조회해줘", location="Seoul"))
    print(orchestrator.handle("subscription_weather_flow 조회해줘", applicant_id="A123"))
