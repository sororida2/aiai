from __future__ import annotations

import os

from openai import OpenAI

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def complete(*, system: str, user: str, model: str | None = None) -> str:
    """system/user 프롬프트 하나를 모델에 넘기고 텍스트만 돌려주는 얇은 wrapper.

    framework 엔진(orchestrator.py 등)은 이 모듈을 모른다 — AgentRunner 구현체나
    judged 노드처럼 실제로 모델 호출이 필요한 지점에서만 import해서 쓴다.
    """
    response = get_client().chat.completions.create(
        model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()
