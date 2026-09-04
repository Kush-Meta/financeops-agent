"""Tool registry and shared result types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    tool: str
    ok: bool
    data: Any
    summary: str
    records_accessed: list[dict] = field(default_factory=list)
    calculations: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


ToolFn = Callable[..., ToolResult]

TOOL_REGISTRY: dict[str, ToolFn] = {}


def register_tool(name: str):
    def decorator(fn: ToolFn):
        TOOL_REGISTRY[name] = fn
        return fn

    return decorator


def get_tool(name: str) -> ToolFn:
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    return TOOL_REGISTRY[name]


def list_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())
