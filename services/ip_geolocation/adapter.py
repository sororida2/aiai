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
        if not response.content:
            # 204 No Content처럼 본문이 비어 있으면 response.json()이 JSONDecodeError로
            # 애매하게 죽는 대신, 여기서 원인을 짐작할 수 있는 메시지로 명확히 실패시킨다 —
            # 무료 HTTP(비-HTTPS) 엔드포인트라 사내망/프록시가 본문을 지우는 경우가 실제로 있다.
            raise ValueError(
                f"ip-api.com returned an empty body (HTTP {response.status_code}) for ip={ip!r} — "
                "네트워크/프록시가 HTTP(비-HTTPS) 응답 본문을 막았을 가능성이 있다"
            )
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
            # ip-api.com 응답에 이미 ISO 3166-1 alpha-2(예: "KR")가 그대로 들어있다 —
            # 이 프로젝트의 국가 정준 표현(§ limitation.md "업계 비교" 절, public_holiday/
            # university_search가 이미 alpha-2로 통일)과 다리를 새로 놓을 필요 없이 바로
            # 맞아떨어져서 그대로 노출한다. 다른 tool과 조합할 때(예: university_search)
            # 이 필드를 그대로 country_code 인자에 넘기면 된다.
            "country_code": raw_response["countryCode"],
            "region": raw_response["regionName"],
            "city": raw_response["city"],
            "lat": raw_response["lat"],
            "lon": raw_response["lon"],
            "timezone": raw_response["timezone"],
            "isp": raw_response["isp"],
        }
