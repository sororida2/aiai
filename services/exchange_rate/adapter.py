from __future__ import annotations

from typing import Any

import requests

from framework.adapters.base import BaseAdapter

RATES_URL = "https://api.frankfurter.dev/v1/latest"


class ExchangeRateAdapter(BaseAdapter):
    """Frankfurter(ECB 환율) 어댑터, 인증 불필요. 응답이 통화 코드→환율 숫자라
    정규화할 레거시 코드 테이블이 없다 — SemanticMapping을 쓰지 않는다.
    """

    def call(self, *, base: str, symbols: str) -> dict[str, Any]:
        response = requests.get(RATES_URL, params={"base": base, "symbols": symbols}, timeout=10)
        response.raise_for_status()
        return response.json()

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        return {"base": raw_response["base"], "date": raw_response["date"], "rates": raw_response["rates"]}
