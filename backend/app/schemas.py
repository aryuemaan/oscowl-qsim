"""Request models for the REST API (responses are plain JSON documented in docs/API.md)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NoiseIn(BaseModel):
    p1: float = Field(0.0, ge=0, le=0.5, description="1-qubit depolarizing error probability per gate")
    p2: float = Field(0.0, ge=0, le=0.5, description="2-qubit depolarizing error probability per gate")
    amplitude_damping: float = Field(0.0, ge=0, le=0.5, description="Amplitude damping (T1) probability per gate per qubit")
    readout_p01: float = Field(0.0, ge=0, le=0.5, description="Probability a 0 is read as 1")
    readout_p10: float = Field(0.0, ge=0, le=0.5, description="Probability a 1 is read as 0")


class OptionsIn(BaseModel):
    shots: int = Field(1024, ge=1)
    trajectories: int = Field(16, ge=1)
    backend: str = Field("auto", pattern="^(auto|statevector|mps)$")
    max_bond: int = Field(64, ge=2)
    seed: int | None = None


class QasmIn(BaseModel):
    qasm: str = Field(..., min_length=1, max_length=2_000_000)


class ValidateIn(QasmIn):
    use_ai: bool = False


class SimulateIn(QasmIn):
    noise: NoiseIn = NoiseIn()
    options: OptionsIn = OptionsIn()


class ExplainIn(SimulateIn):
    simulation: dict | None = Field(None, description="A previous /api/simulate result to explain (saves re-running)")
