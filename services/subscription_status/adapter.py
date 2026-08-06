from __future__ import annotations

import pathlib
from typing import Any

from framework.adapters.base import BaseAdapter
from framework.semantic.mapping import SemanticMapping

MAPPING_PATH = pathlib.Path(__file__).parent / "mapping.json"


class SubscriptionStatusAdapter(BaseAdapter):
    """레거시 청약 시스템 어댑터. call()은 실제 스펙(REST/DB)에 종속되고,
    normalize()는 mapping.json의 confirmed/inferred 구분에 종속된다.
    """

    def __init__(self) -> None:
        self.mapping = SemanticMapping.from_json(MAPPING_PATH)

    def call(self, *, applicant_id: str) -> dict[str, Any]:
        # TODO: 실제 레거시 REST/DB 호출로 교체. 지금은 스캐폴드용 스텁 응답.
        return {"applicant_id": applicant_id, "status_code": "20", "region": "Seoul"}

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        mapped = self.mapping.normalize(raw_response["status_code"])
        return {
            "applicant_id": raw_response["applicant_id"],
            "status": mapped.value,
            "status_confidence": mapped.confidence,
            "region": raw_response["region"],
        }
