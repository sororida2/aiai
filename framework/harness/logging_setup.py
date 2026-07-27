from __future__ import annotations

import logging
import os

_FORMAT = "%(asctime)s %(levelname)-8s %(name)-28s | %(message)s"
_ROOT_NAME = "agent_loop"


def configure_logging() -> None:
    """LOG_LEVEL 환경변수(기본 INFO)로 로깅을 한 번 설정한다.

    main.py가 기동 시 가장 먼저 호출해야 한다 — 그래야 이후 discover_services()/
    registry.validate()/orchestrator.handle() 전 과정이 같은 레벨로 로깅된다.
    idempotent: 이미 핸들러가 붙어 있으면 logging.basicConfig()는 아무것도 하지 않는다.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT)
    logging.getLogger(_ROOT_NAME).setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """framework 내부 모듈이 공용으로 쓰는 로거. 전부 'agent_loop.' 네임스페이스 아래 모인다."""
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
