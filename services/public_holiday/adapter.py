from __future__ import annotations

from typing import Any

import requests

from framework.adapters.base import BaseAdapter

HOLIDAYS_URL = "https://date.nager.at/api/v3/PublicHolidays"


class PublicHolidayAdapter(BaseAdapter):
    """Nager.Date 어댑터 (인증 불필요). 응답 필드(날짜/이름)가 이미 사람이 바로 읽을
    수 있는 값이라 정규화할 레거시 코드 테이블이 없다 — SemanticMapping을 쓰지 않는다.
    """

    def call(self, *, year: int, country_code: str) -> dict[str, Any]:
        response = requests.get(f"{HOLIDAYS_URL}/{year}/{country_code}", timeout=10)
        response.raise_for_status()
        return {"holidays": response.json()}

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        return {
            "holidays": [
                {"date": h["date"], "name": h["name"], "local_name": h["localName"]}
                for h in raw_response["holidays"]
            ]
        }
