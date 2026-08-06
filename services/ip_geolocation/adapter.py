from __future__ import annotations

from typing import Any

import requests

from framework.adapters.base import BaseAdapter

GEOLOCATION_URL = "http://ip-api.com/json"


class IpGeolocationAdapter(BaseAdapter):
    """ip-api.com 어댑터, 인증 불필요(무료 등급은 HTTPS 미지원이라 HTTP로 호출).
    응답이 국가명/도시명 등 이미 사람이 읽을 수 있는 값이라 SemanticMapping을 쓰지 않는다.
    """

    def call(self, *, ip: str) -> dict[str, Any]:
        response = requests.get(f"{GEOLOCATION_URL}/{ip}", timeout=10)
        response.raise_for_status()
        return response.json()

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        if raw_response["status"] != "success":
            # ip-api.com은 실패해도 HTTP 200과 함께 {"status": "fail", "message": "..."}만 준다 —
            # HTTP 레벨에서는 안 걸러지므로 여기서 직접 fail-fast 시킨다.
            raise ValueError(
                f"ip geolocation failed for {raw_response.get('query')!r}: {raw_response.get('message')}"
            )
        return {
            "ip": raw_response["query"],
            "country": raw_response["country"],
            "region": raw_response["regionName"],
            "city": raw_response["city"],
            "lat": raw_response["lat"],
            "lon": raw_response["lon"],
            "timezone": raw_response["timezone"],
            "isp": raw_response["isp"],
        }
