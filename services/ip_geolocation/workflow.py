from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from services.ip_geolocation.adapter import IpGeolocationAdapter

IP_GEOLOCATION_OUTPUT_SCHEMA = {
    "ip": Any,
    "country": Any,
    "region": Any,
    "city": Any,
    "lat": Any,
    "lon": Any,
    "timezone": Any,
    "isp": Any,
}


@tool(
    name="ip_geolocation",
    description="지정한 IP 주소(ip)의 대략적인 지리적 위치(국가/지역/도시/좌표/타임존/ISP)를 조회한다.",
)
@guardrail(output_schema=IP_GEOLOCATION_OUTPUT_SCHEMA)
def ip_geolocation(ip: str) -> dict[str, Any]:
    return IpGeolocationAdapter().execute(ip=ip)
