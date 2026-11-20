"""Application settings, read from environment variables or a `.env` file.

Look for `.env` in the repo root first, then in `backend/`. See `.env.example`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AI ---------------------------------------------------------------
    gemini_api_key: str = Field("", validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    qsim_ai_mode: str = "auto"  # auto | gemini | offline
    gemini_flash_model: str = "gemini-3.8-flash"
    gemini_reasoning_model: str = "gemini-4-argon"
    gemma_provider: str = "auto"  # auto | gemini_api | ollama | off
    gemma_model: str = "gemma-4-26b-a4b-it"
    ollama_url: str = "http://localhost:11434"
    ollama_gemma_model: str = "gemma4"
    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    ai_timeout_s: float = 45.0

    # --- simulator limits -------------------------------------------------
    max_qubits: int = 128
    sv_auto_max: int = 16
    sv_hard_max: int = 24
    max_bond_limit: int = 256
    max_gates: int = 20000
    max_shots: int = 20000
    max_trajectories: int = 200
    time_budget_s: float = 90.0
    array_backend: str = "numpy"  # numpy | jax

    # --- web ----------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    static_dir: str = str(BACKEND_DIR / "static")
    benchmark_results: str = str(REPO_DIR / "benchmarks" / "results" / "latest.json")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
