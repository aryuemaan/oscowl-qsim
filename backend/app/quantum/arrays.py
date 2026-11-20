"""Pick the array library for the MPS core: NumPy (default) or JAX (GPU/TPU).

JAX is optional. Install it with ``pip install "jax[cpu]"`` locally, or the
CUDA/TPU flavour on accelerator nodes, then set ``ARRAY_BACKEND=jax``.
"""
from __future__ import annotations

from functools import lru_cache
from types import ModuleType

import numpy as np


@lru_cache(maxsize=None)
def get_array_module(name: str = "numpy") -> ModuleType:
    if name == "numpy":
        return np
    if name == "jax":
        try:
            import jax
            import jax.numpy as jnp
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise RuntimeError('ARRAY_BACKEND=jax but JAX is not installed: pip install "jax[cpu]"') from exc
        jax.config.update("jax_enable_x64", True)  # complex128 for accurate amplitudes
        return jnp
    raise ValueError(f"Unknown array backend '{name}' (use 'numpy' or 'jax')")


def available_backends() -> list[str]:
    out = ["numpy"]
    try:
        import jax  # noqa: F401

        out.append("jax")
    except ImportError:
        pass
    return out
