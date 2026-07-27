from __future__ import annotations

import abc
from typing import Any

from framework.semantic.mapping import SemanticMapping


class BaseAdapter(abc.ABC):
    """양면 어댑터: 프로토콜적 면과 의미론적 면을 분리해 독립적으로 변경 가능하게 한다.

    - 프로토콜적 면(call): 레거시의 실제 스펙(REST/gRPC, 인증)에 종속.
    - 의미론적 면(normalize): SemanticMapping을 통해 원시값을 정규화값으로
      변환하고, 모델에게 레거시의 지저분한 원시값을 그대로 노출하지 않는다.
    """

    def __init__(self, mapping: SemanticMapping) -> None:
        self.mapping = mapping

    @abc.abstractmethod
    def call(self, **kwargs: Any) -> dict[str, Any]:
        """레거시 API/DB 호출 + 응답을 원시 dict로 반환. 프로토콜 세부사항은 여기 갇힌다."""

    @abc.abstractmethod
    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        """원시 응답의 코드값들을 self.mapping을 통해 정규화값으로 치환해 반환."""

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return self.normalize(self.call(**kwargs))
