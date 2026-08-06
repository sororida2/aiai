from __future__ import annotations

import pathlib
from typing import Any

from framework.adapters.base import BaseAdapter
from framework.semantic.mapping import SemanticMapping

MAPPING_PATH = pathlib.Path(__file__).parent / "mapping.json"

# 실제 레거시 목록 조회 API 연동 전 스텁 — 20명의 청약 신청자를 고정 데이터로 둔다.
# status_code는 subscription_status와 같은 5단계 체계(10/20/30/40/99)를 임의로 배분한 것.
_STUB_APPLICANTS = [
    {"applicant_id": "A101", "name": "김민준", "status_code": "10"},
    {"applicant_id": "A102", "name": "이서연", "status_code": "30"},
    {"applicant_id": "A103", "name": "박도윤", "status_code": "20"},
    {"applicant_id": "A104", "name": "최지우", "status_code": "40"},
    {"applicant_id": "A105", "name": "정하은", "status_code": "30"},
    {"applicant_id": "A106", "name": "강주원", "status_code": "10"},
    {"applicant_id": "A107", "name": "조서준", "status_code": "40"},
    {"applicant_id": "A108", "name": "윤지호", "status_code": "20"},
    {"applicant_id": "A109", "name": "임하윤", "status_code": "30"},
    {"applicant_id": "A110", "name": "한소율", "status_code": "99"},
    {"applicant_id": "A111", "name": "오예준", "status_code": "10"},
    {"applicant_id": "A112", "name": "서지안", "status_code": "40"},
    {"applicant_id": "A113", "name": "신도현", "status_code": "30"},
    {"applicant_id": "A114", "name": "권나윤", "status_code": "20"},
    {"applicant_id": "A115", "name": "황시우", "status_code": "10"},
    {"applicant_id": "A116", "name": "안유나", "status_code": "30"},
    {"applicant_id": "A117", "name": "송민서", "status_code": "40"},
    {"applicant_id": "A118", "name": "유준서", "status_code": "99"},
    {"applicant_id": "A119", "name": "전지유", "status_code": "20"},
    {"applicant_id": "A120", "name": "홍은우", "status_code": "30"},
]


class ApplicantListAdapter(BaseAdapter):
    """청약 신청자 목록 어댑터. call()은 레거시 목록 조회 API(현재 스텁)에 종속되고,
    normalize()는 mapping.json으로 각 신청자의 status_code를 정규화한다.
    """

    def __init__(self) -> None:
        self.mapping = SemanticMapping.from_json(MAPPING_PATH)

    def call(self) -> dict[str, Any]:
        # TODO: 실제 레거시 목록 조회 API로 교체. 지금은 스캐폴드용 스텁 응답.
        return {"applicants": _STUB_APPLICANTS}

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        normalized = []
        for applicant in raw_response["applicants"]:
            mapped = self.mapping.normalize(applicant["status_code"])
            normalized.append(
                {
                    "applicant_id": applicant["applicant_id"],
                    "name": applicant["name"],
                    "status": mapped.value,
                    "status_confidence": mapped.confidence,
                }
            )
        return {"applicants": normalized}
