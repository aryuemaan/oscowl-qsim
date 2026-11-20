"""Readout-error mitigation on the observed subspace (M3-style).

Builds the assignment matrix A[i, j] = P(observe s_i | true s_j) only between
bitstrings that were actually observed, solves A x = p_observed, clips negative
quasi-probabilities and renormalises. Cheap and effective for structured outputs.
"""
from __future__ import annotations

import math

import numpy as np

MAX_SUPPORT = 2048


def mitigate_readout(counts: dict[str, int], p01: float, p10: float) -> dict[str, float] | None:
    """Return mitigated probabilities over the observed outcomes, or None if not applicable."""
    if (p01 <= 0 and p10 <= 0) or not counts:
        return None
    keys = list(counts)
    if len(keys) > MAX_SUPPORT:
        return None
    shots = float(sum(counts.values()))
    obs = np.array([[ch == "1" for ch in k] for k in keys], dtype=float)  # (N, m)
    p_obs = np.array([counts[k] / shots for k in keys])
    eps = 1e-12
    l00, l01 = math.log(max(1 - p01, eps)), math.log(max(p01, eps))  # true 0 -> read 0 / 1
    l11, l10 = math.log(max(1 - p10, eps)), math.log(max(p10, eps))  # true 1 -> read 1 / 0
    o, t = obs, obs  # observed rows i, "true" columns j (same support)
    log_a = (o @ t.T) * l11 + (o @ (1 - t).T) * l01 + ((1 - o) @ t.T) * l10 + ((1 - o) @ (1 - t).T) * l00
    a = np.exp(log_a)
    a /= a.sum(axis=0, keepdims=True)  # columns as conditional distributions on the subspace
    x, *_ = np.linalg.lstsq(a, p_obs, rcond=None)
    x = np.clip(x, 0.0, None)
    if x.sum() <= 0:
        return None
    x /= x.sum()
    return {k: float(v) for k, v in zip(keys, x) if v > 1e-12}


def hellinger_fidelity(p: dict[str, float], q: dict[str, float], normalize_q: bool = True) -> float:
    """Classical (Hellinger) fidelity (sum_x sqrt(p(x) q(x)))^2.

    ``p`` is normalised. ``q`` is normalised too unless it already holds exact
    ideal probabilities (``normalize_q=False``), which is the more accurate mode."""
    tot_p = sum(p.values()) or 1.0
    tot_q = (sum(q.values()) or 1.0) if normalize_q else 1.0
    bc = sum(math.sqrt(max(p[k], 0.0) / tot_p * max(q.get(k, 0.0), 0.0) / tot_q) for k in p)
    return float(min(1.0, bc**2))
