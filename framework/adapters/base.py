from __future__ import annotations

import abc
from typing import Any

from framework.harness.logging_setup import get_logger

logger = get_logger("adapter")


class BaseAdapter(abc.ABC):
    """양면 어댑터: 프로토콜적 면과 의미론적 면을 분리해 독립적으로 변경 가능하게 한다.

    - 프로토콜적 면(call): 레거시의 실제 스펙(REST/gRPC, 인증)에 종속.
    - 의미론적 면(normalize): 원시값을 정규화값으로 변환하고, 모델에게 레거시의
      지저분한 원시값을 그대로 노출하지 않는다. 원시 코드값 테이블을 정규화해야
      하는 어댑터는 `framework.semantic.mapping.SemanticMapping`을 자기
      `__init__`에서 직접 들고 있으면 된다 — 모든 어댑터가 이걸 가져야 하는 건
      아니다(예: 응답에 정규화할 코드값 자체가 없는 외부 API).
    """

    @abc.abstractmethod
    def call(self, **kwargs: Any) -> dict[str, Any]:
        """레거시 API/DB 호출 + 응답을 원시 dict로 반환. 프로토콜 세부사항은 여기 갇힌다."""

    @abc.abstractmethod
    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        """원시 응답을 정규화해 반환. 코드값이 있으면 SemanticMapping을 쓰든, 없으면 필요한 필드만 추리든 이 메서드 소관."""

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        name = type(self).__name__
        logger.debug("%s.call(%s)", name, kwargs)
        raw = self.call(**kwargs)
        logger.debug("%s.call() -> %s", name, raw)
        result = self.normalize(raw)
        logger.debug("%s.normalize() -> %s", name, result)
        return result
