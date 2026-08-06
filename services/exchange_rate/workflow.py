from __future__ import annotations

from typing import Any

from framework.registry.decorators import guardrail, tool
from services.exchange_rate.adapter import ExchangeRateAdapter

EXCHANGE_RATE_OUTPUT_SCHEMA = {"base": Any, "date": Any, "rates": Any}


@tool(
    name="exchange_rate",
    description=(
        "기준 통화(base, 예: USD)에 대한 다른 통화들(symbols, 쉼표로 구분된 통화 코드 목록, "
        "예: 'KRW,EUR,JPY')의 최신 환율을 조회한다."
    ),
)
@guardrail(output_schema=EXCHANGE_RATE_OUTPUT_SCHEMA)
def exchange_rate(base: str, symbols: str) -> dict[str, Any]:
    return ExchangeRateAdapter().execute(base=base, symbols=symbols)
