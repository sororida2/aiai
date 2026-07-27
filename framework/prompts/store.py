from __future__ import annotations

import pathlib
from dataclasses import dataclass, field


@dataclass
class PromptStore:
    """프롬프트를 코드에서 분리해 계층으로 관리 — 공통 / 도메인별 tool / few-shot.

    런타임에 조합되어 모델 호출로 전달된다.
    """

    base_dir: pathlib.Path
    common_file: str = "common/orchestrator.md"

    def common_prompt(self) -> str:
        return (self.base_dir / self.common_file).read_text(encoding="utf-8")

    def tool_prompt(self, tool_name: str, tool_dir: pathlib.Path) -> str:
        path = tool_dir / f"{tool_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"no prompt file for tool '{tool_name}' at {path}")
        return path.read_text(encoding="utf-8")

    def compose(self, tool_name: str, tool_dir: pathlib.Path, few_shot: str | None = None) -> str:
        parts = [self.common_prompt(), self.tool_prompt(tool_name, tool_dir)]
        if few_shot:
            parts.append(few_shot)
        return "\n\n---\n\n".join(parts)
