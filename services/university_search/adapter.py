from __future__ import annotations

import pathlib
from typing import Any

import requests

from framework.adapters.base import BaseAdapter
from framework.semantic.mapping import SemanticMapping

MAPPING_PATH = pathlib.Path(__file__).parent / "mapping.json"
UNIVERSITIES_URL = "http://universities.hipolabs.com/search"


class UniversitySearchAdapter(BaseAdapter):
    """Hipolabs Universities 어댑터, 인증 불필요.

    Hipolabs API 자체는 ISO alpha-2 코드로 필터링을 지원하지 않고(자체 확인 —
    ?alpha_two_code=US를 줘도 무시하고 전체 데이터셋을 반환한다) country 파라미터에
    자기 데이터셋의 국가명 문자열을 그대로 요구한다. 이 프로젝트의 다른 tool
    (public_holiday)은 ISO alpha-2를 입력으로 받으므로, 여기서는 SemanticMapping을
    "입력값 정규화"(alpha-2 코드 → Hipolabs 국가명 문자열)에 쓴다 — 지금까지의
    출력값 정규화 용례와는 방향이 반대지만 같은 원시값→정규화값 개념이다.
    """

    def __init__(self) -> None:
        self.mapping = SemanticMapping.from_json(MAPPING_PATH)

    def call(self, *, country_code: str) -> dict[str, Any]:
        country_name = self.mapping.normalize(country_code).require_confirmed()
        response = requests.get(UNIVERSITIES_URL, params={"country": country_name}, timeout=10)
        response.raise_for_status()
        return {"universities": response.json()}

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        return {
            "universities": [
                {
                    "name": u["name"],
                    "domains": u["domains"],
                    "website": u["web_pages"][0] if u["web_pages"] else None,
                }
                for u in raw_response["universities"]
            ]
        }
