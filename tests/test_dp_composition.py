from __future__ import annotations

import math

import numpy as np

from backend.silos.dp import (
    add_gaussian_noise,
    epsilon_for_zcdp,
    opendp_gaussian_rho,
    sigma_for_zcdp,
)


def test_opendp_gaussian_map_matches_local_zcdp_formula() -> None:
    sigma = sigma_for_zcdp(sensitivity=1.0, rho=0.04)

    assert math.isclose(opendp_gaussian_rho(sensitivity=1.0, sigma=sigma), 0.04, abs_tol=1e-8)


def test_gaussian_helper_has_expected_empirical_mean_and_variance() -> None:
    rng = np.random.default_rng(20260513)
    rho = 0.5
    true_value = 100.0
    sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho)

    samples = np.array(
        [
            add_gaussian_noise(
                true_value,
                sensitivity=1.0,
                rho=rho,
                rng=rng,
            ).value
            for _ in range(300)
        ]
    )

    assert abs(samples.mean() - true_value) < 3 * sigma / math.sqrt(len(samples))
    assert abs(samples.var(ddof=1) - sigma**2) < 0.35 * sigma**2


def test_zcdp_epsilon_display_increases_with_rho() -> None:
    assert epsilon_for_zcdp(rho=0.02) < epsilon_for_zcdp(rho=0.04)
