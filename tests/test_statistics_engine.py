"""Tests for the Statistical Synthesis Engine."""

from __future__ import annotations

import pytest

from evidentia.core.statistics import StatisticalSynthesis


@pytest.fixture
def engine():
    return StatisticalSynthesis()


def test_auto_synthesize_basic(engine):
    """auto_synthesize produces valid results with structured studies."""
    studies = [
        {
            "source_id": "s1",
            "authors": "Smith et al.",
            "year": "2023",
            "key_finding": "Treatment improved outcomes, d = 0.45, 95% CI [0.20, 0.70], N = 120",
            "sample_size": "120",
            "method": "RCT",
            "outcome": "positive",
            "source": "Smith 2023",
        },
        {
            "source_id": "s2",
            "authors": "Jones et al.",
            "year": "2022",
            "key_finding": "Significant effect found, Cohen's d = 0.38, N = 85, p < 0.01",
            "sample_size": "85",
            "method": "RCT",
            "outcome": "positive",
            "source": "Jones 2022",
        },
        {
            "source_id": "s3",
            "authors": "Lee et al.",
            "year": "2024",
            "key_finding": "Effect size d = 0.52, SE = 0.12, 200 participants",
            "sample_size": "200",
            "method": "Cohort",
            "outcome": "improved outcomes",
            "source": "Lee 2024",
        },
    ]
    result = engine.auto_synthesize(studies)
    assert result.k >= 2
    assert result.pooled_effect != 0.0
    assert result.pooled_se > 0
    assert result.pooled_ci_lower < result.pooled_effect < result.pooled_ci_upper
    assert 0.0 <= result.i_squared <= 100.0
    assert result.model in ("fixed", "random")
    assert len(result.forest_plot_data) > 0
    summary_rows = [r for r in result.forest_plot_data if r["type"] == "summary"]
    assert len(summary_rows) == 1


def test_empty_studies(engine):
    """auto_synthesize with empty list raises or returns empty result."""
    result = engine.auto_synthesize([])
    assert result.k == 0
    assert result.pooled_effect == 0.0


def test_single_study(engine):
    """auto_synthesize with one extractable study returns single-study result."""
    studies = [
        {
            "source_id": "s1",
            "authors": "Alpha",
            "year": "2024",
            "key_finding": "d = 0.6, N = 50",
            "sample_size": "50",
            "method": "RCT",
            "outcome": "",
            "source": "Alpha 2024",
        },
    ]
    result = engine.auto_synthesize(studies)
    assert result.k == 1
    assert abs(result.pooled_effect - 0.6) < 0.1
