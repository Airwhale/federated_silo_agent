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

    assert math.isclose(
        opendp_gaussian_rho(sensitivity=1.0, sigma=sigma),
        0.04,
        abs_tol=1e-8,
    )


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


def test_gaussian_mechanism_validates_across_full_rho_range() -> None:
    """The OpenDP map check tolerance must cover the rounding error in sigma.

    sigma is rounded to 6 decimal places in sigma_for_zcdp; the OpenDP map
    then recomputes rho from the rounded sigma. The recovered rho drifts
    from the requested rho by an amount proportional to the local derivative
    of rho = sensitivity^2 / (2 * sigma^2). The OPEN_DP_RHO_TOLERANCE must
    be loose enough to accept that drift across the full ledger range.
    """
    rng = np.random.default_rng(20260513)
    # Span the realistic ledger range: well below the default 0.02 alert-count
    # cost, up to the default rho_max=1.0. Each call must not raise.
    for rho in (0.005, 0.02, 0.04, 0.1, 0.5, 1.0):
        result = add_gaussian_noise(0.0, sensitivity=1.0, rho=rho, rng=rng)
        assert result.rho == rho


def test_flow_histogram_parallel_composition_matches_single_ledger_debit() -> None:
    """A disjoint amount histogram pays the max bucket rho, not the sum."""
    rho_debited = 0.03
    bucket_count = 5

    bucket_sigma = sigma_for_zcdp(sensitivity=1.0, rho=rho_debited)
    serial_sigma = sigma_for_zcdp(
        sensitivity=1.0,
        rho=rho_debited / bucket_count,
    )
    per_bucket_rhos = [
        opendp_gaussian_rho(sensitivity=1.0, sigma=bucket_sigma)
        for _ in range(bucket_count)
    ]

    assert math.isclose(max(per_bucket_rhos), rho_debited, abs_tol=1e-5)
    assert sum(per_bucket_rhos) > rho_debited
    assert bucket_sigma < serial_sigma


def test_pattern_aggregate_composition_matches_component_split() -> None:
    """F2 aggregates compose serially across components, parallel within buckets."""
    total_rho_debited = 0.04
    component_rho = total_rho_debited / 2.0

    edge_sigma = sigma_for_zcdp(sensitivity=math.sqrt(2.0), rho=component_rho)
    flow_sigma = sigma_for_zcdp(sensitivity=1.0, rho=component_rho)
    edge_bucket_rhos = [
        opendp_gaussian_rho(sensitivity=math.sqrt(2.0), sigma=edge_sigma)
        for _ in range(6)
    ]
    flow_bucket_rhos = [
        opendp_gaussian_rho(sensitivity=1.0, sigma=flow_sigma)
        for _ in range(5)
    ]

    edge_component_rho = max(edge_bucket_rhos)
    flow_component_rho = max(flow_bucket_rhos)

    assert math.isclose(edge_component_rho, component_rho, abs_tol=1e-5)
    assert math.isclose(flow_component_rho, component_rho, abs_tol=1e-5)
    assert math.isclose(
        edge_component_rho + flow_component_rho,
        total_rho_debited,
        abs_tol=1e-5,
    )
    assert sum(edge_bucket_rhos) + sum(flow_bucket_rhos) > total_rho_debited
