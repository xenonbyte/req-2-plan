from __future__ import annotations
from pathlib import Path
from typing import Protocol


class AdapterProtocol(Protocol):
    ADAPTER_NAME: str
    ADAPTER_RULE_VERSION: str
    SUPPORTED_PLAN_SECTIONS: set[str]

    def adapt_plan(self, plan_path: Path, output_path: Path) -> str:
        ...


# Registry: name -> module
ADAPTER_REGISTRY: dict[str, str] = {
    "superpowers": "tools.workflow_cli.adapters.superpowers",
}


def get_adapter(name: str):
    """Load and return adapter module by name."""
    import importlib
    if name not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter: {name!r}. Available: {list(ADAPTER_REGISTRY)}")
    return importlib.import_module(ADAPTER_REGISTRY[name])


def list_adapters() -> list[str]:
    return list(ADAPTER_REGISTRY)
