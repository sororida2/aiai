from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from framework.registry.decorators import ServiceConsistencyError


def discover_services(package: ModuleType) -> None:
    """services/<name>/workflow.py를 전부 import해 @tool·@workflow_step 등록을 트리거한다.

    main.py가 서비스 하나하나를 `from services.<name> import workflow as _`로 나열하지
    않아도 되게 하는 대신, workflow.py가 없는 서비스 폴더는 여기서 바로 fail-fast한다 —
    조용히 무시되면 "서비스는 있는데 tool로는 안 잡히는" 상태가 되기 때문.
    """
    for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:
            continue
        module_name = f"{package.__name__}.{name}.workflow"
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # exc.name으로 정확히 workflow.py 자체가 없는 경우만 골라낸다 — workflow.py는
            # 있지만 그 안에서 다른 모듈 import가 실패한 경우(진짜 버그)까지 오진하지 않기 위해.
            if exc.name == module_name:
                raise ServiceConsistencyError(
                    f"services/{name}/ 에 workflow.py가 없다 (등록 트리거 모듈 누락)"
                ) from exc
            raise
