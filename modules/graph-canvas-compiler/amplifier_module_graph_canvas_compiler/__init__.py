"""Graph canvas compiler - compiles graph canvas definitions."""

import logging as _logging

try:
    from .compile import compile_graph
    from .decompile import decompile_recipe
except ImportError:
    compile_graph = None  # type: ignore[assignment]
    decompile_recipe = None  # type: ignore[assignment]
    _logging.getLogger(__name__).debug(
        "graph-canvas-compiler: ruamel.yaml unavailable — compile/decompile disabled"
    )

from .layout import auto_layout

__all__ = ["compile_graph", "decompile_recipe", "auto_layout"]
