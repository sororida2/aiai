from __future__ import annotations

import os

from openai import OpenAI

from framework.harness.logging_setup import get_logger

logger = get_logger("llm")

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def complete(*, system: str, user: str, model: str | None = None) -> str:
    """system/user 프롬프트 하나를 모델에 넘기고 텍스트만 돌려주는 얇은 wrapper.

    triage/tool 선택은 이제 SDK의 `Agent`/`Runner`가 담당한다(§ `main.py`) — 이 함수는
    그것과 별개로, `judged` 노드처럼 bounded choices 판단에 모델 호출이 직접 필요한
    지점에서만 opt-in으로 import해서 쓴다. 지금 실제로 쓰는 서비스는 없다(§ ARCHITECTURE.md
    "현재 스캐폴드의 한계" — judged() 자체가 아직 orphan).
    """
    resolved_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    logger.info("openai call: model=%s system_chars=%d user_chars=%d", resolved_model, len(system), len(user))
    logger.debug("openai system prompt: %s", system)
    logger.debug("openai user prompt: %s", user)
    response = get_client().chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    result = (response.choices[0].message.content or "").strip()
    logger.info("openai response: %r", result[:120])
    return result
