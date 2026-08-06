from __future__ import annotations

import pathlib
from typing import Any

import requests

from framework.adapters.base import BaseAdapter
from framework.semantic.mapping import SemanticMapping

MAPPING_PATH = pathlib.Path(__file__).parent / "mapping.json"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherAdapter(BaseAdapter):
    """Open-Meteo 어댑터 (인증 불필요, RapidAPI 키 없이 바로 호출).

    call()은 두 단계(지오코딩 → 현재 날씨)로 Open-Meteo REST 스펙에 종속되고,
    normalize()는 mapping.json의 WMO weather code(공식 문서화된 고정 표) 매핑에 종속된다.
    """

    def __init__(self) -> None:
        self.mapping = SemanticMapping.from_json(MAPPING_PATH)

    def call(self, *, location: str) -> dict[str, Any]:
        geo = requests.get(GEOCODING_URL, params={"name": location, "count": 1}, timeout=10)
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            raise ValueError(f"no geocoding match for location {location!r}")
        place = results[0]

        forecast = requests.get(
            FORECAST_URL,
            params={"latitude": place["latitude"], "longitude": place["longitude"], "current_weather": "true"},
            timeout=10,
        )
        forecast.raise_for_status()
        current = forecast.json()["current_weather"]
        return {
            "resolved_name": place["name"],
            "weathercode": current["weathercode"],
            "temperature": current["temperature"],
        }

    def normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        mapped = self.mapping.normalize(str(raw_response["weathercode"]))
        return {
            "location": raw_response["resolved_name"],
            "condition": mapped.value,
            "condition_confidence": mapped.confidence,
            "temperature": raw_response["temperature"],
        }
