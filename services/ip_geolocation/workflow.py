from __future__ import annotations

from typing import Any

from framework.harness.guardrail import validate_tool_output
from framework.registry.decorators import tool
from services.ip_geolocation.adapter import IpGeolocationAdapter

IP_GEOLOCATION_OUTPUT_SCHEMA = {
    "ip": Any,
    "country": Any,
    "country_code": Any,  # ISO 3166-1 alpha-2 — 다른 국가 코드 기반 tool과 조합할 때 이걸 쓴다
    "region": Any,
    "city": Any,
    "lat": Any,
    "lon": Any,
    "timezone": Any,
    "isp": Any,
}


@tool(
    name="ip_geolocation",
    description=(
        "지정한 IP 주소(ip)의 대략적인 지리적 위치(국가/국가코드/지역/도시/좌표/타임존/ISP)를 "
        "조회한다. country_code는 ISO 3166-1 alpha-2."
    ),
    output_schema=IP_GEOLOCATION_OUTPUT_SCHEMA,
)
def ip_geolocation(ip: str) -> dict[str, Any]:
    result = IpGeolocationAdapter().execute(ip=ip)
    return validate_tool_output("ip_geolocation", result)
