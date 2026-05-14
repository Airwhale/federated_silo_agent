"""Light OpenDP-backed Gaussian helpers for bank-local primitives."""

from __future__ import annotations

import math

import numpy as np
import opendp.prelude as dp
from pydantic import BaseModel, ConfigDict, Field


DEFAULT_DELTA = 1e-6
OPEN_DP_RHO_TOLERANCE = 1e-8

dp.enable_features("contrib")


class DpModel(BaseModel):
    """Strict Pydantic base for P7 DP helper values."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class GaussianMechanismResult(DpModel):
    """One Gaussian mechanism release and its accounting metadata."""

    value: float
    sigma: float = Field(gt=0.0)
    rho: float = Field(gt=0.0)
    eps_delta_display: tuple[float, float]


def sigma_for_zcdp(*, sensitivity: float, rho: float) -> float:
    """Return zCDP Gaussian sigma for a sensitivity and rho budget."""
    if sensitivity <= 0.0:
        raise ValueError("sensitivity must be positive")
    if rho <= 0.0:
        raise ValueError("rho must be positive")
    return round(sensitivity / math.sqrt(2.0 * rho), 6)


def epsilon_for_zcdp(*, rho: float, delta: float = DEFAULT_DELTA) -> float:
    """Convert zCDP rho to the approximate-DP epsilon display value."""
    if rho < 0.0:
        raise ValueError("rho must be non-negative")
    if not 0.0 < delta < 1.0:
        raise ValueError("delta must be between 0 and 1")
    if rho == 0.0:
        return 0.0
    return rho + 2.0 * math.sqrt(rho * math.log(1.0 / delta))


def eps_delta_display(*, rho: float, delta: float = DEFAULT_DELTA) -> tuple[float, float]:
    return (round(epsilon_for_zcdp(rho=rho, delta=delta), 6), delta)


def opendp_gaussian_rho(*, sensitivity: float, sigma: float) -> float:
    """Ask OpenDP to map Gaussian scale and sensitivity to zCDP rho."""
    if sensitivity <= 0.0:
        raise ValueError("sensitivity must be positive")
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")

    input_space = dp.atom_domain(T=float, nan=False), dp.absolute_distance(T=float)
    measurement = dp.m.make_gaussian(*input_space, scale=sigma)
    return float(measurement.map(d_in=float(sensitivity)))


def validate_opendp_gaussian_map(*, sensitivity: float, rho: float, sigma: float) -> None:
    """Verify local sigma math against OpenDP's Gaussian privacy map."""
    opendp_rho = opendp_gaussian_rho(sensitivity=sensitivity, sigma=sigma)
    if not math.isclose(opendp_rho, rho, abs_tol=OPEN_DP_RHO_TOLERANCE):
        raise ValueError(
            "OpenDP Gaussian map mismatch: "
            f"expected rho={rho}, got {opendp_rho} for sigma={sigma}"
        )


def add_gaussian_noise(
    value: float,
    *,
    sensitivity: float,
    rho: float,
    rng: np.random.Generator,
    delta: float = DEFAULT_DELTA,
) -> GaussianMechanismResult:
    """Release a value with Gaussian noise using OpenDP-validated calibration."""
    sigma = sigma_for_zcdp(sensitivity=sensitivity, rho=rho)
    validate_opendp_gaussian_map(sensitivity=sensitivity, rho=rho, sigma=sigma)
    noisy_value = float(value + rng.normal(loc=0.0, scale=sigma))
    return GaussianMechanismResult(
        value=noisy_value,
        sigma=sigma,
        rho=rho,
        eps_delta_display=eps_delta_display(rho=rho, delta=delta),
    )
