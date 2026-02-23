"""Cross-Study Statistical Synthesis Engine.

Pure Python + numpy implementation of meta-analytic methods.
NO LLM involved — deterministic statistical computation.

Implements:
- Effect size extraction from text via regex heuristics
- Inverse-variance fixed-effects meta-analysis
- DerSimonian-Laird random-effects meta-analysis
- Heterogeneity measures (Q, I-squared, tau-squared)
- Forest plot data pre-computation
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

# ── Normal distribution helpers (no scipy dependency) ─────────────────


def _norm_cdf(x: float) -> float:
    """Approximate standard normal CDF using Abramowitz & Stegun (1964).

    Maximum error < 7.5e-8 across the entire real line.
    """
    # Symmetry: Phi(-x) = 1 - Phi(x)
    if x < 0:
        return 1.0 - _norm_cdf(-x)

    # Constants for the rational approximation
    p = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429

    t = 1.0 / (1.0 + p * x)
    t2 = t * t
    t3 = t2 * t
    t4 = t3 * t
    t5 = t4 * t

    pdf = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)
    cdf = 1.0 - pdf * (b1 * t + b2 * t2 + b3 * t3 + b4 * t4 + b5 * t5)
    return max(0.0, min(1.0, cdf))


def _norm_ppf(p: float) -> float:
    """Approximate inverse normal CDF (percent-point function).

    Uses the rational approximation from Abramowitz & Stegun.
    Accurate to about 4.5e-4 for 0 < p < 1.
    """
    if p <= 0:
        return -10.0
    if p >= 1:
        return 10.0
    if p < 0.5:
        return -_norm_ppf(1.0 - p)

    # Rational approximation for 0.5 <= p < 1
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308

    return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)


def _chi2_sf(x: float, df: int) -> float:
    """Approximate chi-squared survival function P(X > x) for df degrees of freedom.

    Uses the Wilson-Hilferty normal approximation for the chi-squared distribution.
    Sufficiently accurate for meta-analytic Q-test p-values.
    """
    if x <= 0 or df <= 0:
        return 1.0
    # Wilson-Hilferty transformation
    z = ((x / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    return 1.0 - _norm_cdf(z)


def _z_to_p(z: float) -> float:
    """Two-tailed p-value from z-score."""
    return 2.0 * (1.0 - _norm_cdf(abs(z)))


# ── Data Classes ──────────────────────────────────────────────────────


@dataclass
class StudyEffect:
    """Extracted effect from a single study."""

    study_id: str
    study_label: str  # "Author et al., Year"
    effect_size: float  # standardized (Cohen's d, log OR, etc.)
    se: float  # standard error
    ci_lower: float  # 95% CI lower
    ci_upper: float  # 95% CI upper
    n: int  # total sample size
    weight: float  # inverse-variance weight
    study_design: str  # RCT, cohort, etc.


@dataclass
class SynthesisResult:
    """Result of meta-analytic synthesis."""

    # Overall effect
    pooled_effect: float
    pooled_se: float
    pooled_ci_lower: float
    pooled_ci_upper: float
    pooled_z: float
    pooled_p: float

    # Heterogeneity
    q_statistic: float  # Cochran's Q
    q_p_value: float
    i_squared: float  # I-squared (0-100%)
    tau_squared: float  # between-study variance

    # Per-study
    studies: list[StudyEffect] = field(default_factory=list)

    # Model info
    model: str = "fixed"  # "fixed" or "random"
    effect_measure: str = "SMD"  # "SMD", "OR", "RR", "MD"
    k: int = 0  # number of studies
    total_n: int = 0  # total participants

    # Forest plot data (pre-computed for rendering)
    forest_plot_data: list[dict] = field(default_factory=list)


# ── Regex Patterns for Effect Size Extraction ─────────────────────────

# Effect size patterns — ordered by specificity
EFFECT_PATTERNS: list[tuple[str, str]] = [
    # Cohen's d
    (r"(?:Cohen'?s?\s+)?d\s*=\s*([-+]?\d+\.?\d*)", "SMD"),
    # Hedges' g
    (r"(?:Hedges'?\s+)?g\s*=\s*([-+]?\d+\.?\d*)", "SMD"),
    # Odds ratio
    (r"(?:odds\s+ratio|OR)\s*[=:]\s*([-+]?\d+\.?\d*)", "OR"),
    # Risk ratio / Relative risk
    (r"(?:risk\s+ratio|RR|relative\s+risk)\s*[=:]\s*([-+]?\d+\.?\d*)", "RR"),
    # Hazard ratio
    (r"(?:hazard\s+ratio|HR)\s*[=:]\s*([-+]?\d+\.?\d*)", "HR"),
    # Mean difference
    (r"(?:mean\s+diff(?:erence)?|MD)\s*[=:]\s*([-+]?\d+\.?\d*)", "MD"),
    # Correlation coefficient
    (r"r\s*=\s*([-+]?0?\.\d+)", "r"),
    # Eta squared
    (r"[Ee]ta[- ]?squared|η[²p]?\s*=\s*([-+]?\d+\.?\d*)", "eta2"),
    # Generic effect size
    (r"effect\s+size\s*[=:]\s*([-+]?\d+\.?\d*)", "SMD"),
    # Percentage improvement/reduction patterns
    (r"(\d+\.?\d*)%\s+(?:improvement|increase|reduction|decrease)", "pct"),
]

# CI patterns
CI_PATTERNS = [
    r"95%?\s*CI\s*[=:]?\s*\[?\(?([-+]?\d+\.?\d*)\s*[,;to–-]+\s*([-+]?\d+\.?\d*)\)?\]?",
    r"CI\s*[=:]?\s*\(?([-+]?\d+\.?\d*)\s*[,;to–-]+\s*([-+]?\d+\.?\d*)\)?",
]

# P-value patterns
P_VALUE_PATTERNS = [
    r"p\s*<\s*(0?\.\d+)",
    r"p\s*=\s*(0?\.\d+)",
    r"p\s*>\s*(0?\.\d+)",
    r"p[-\s]*value\s*[=:<>]\s*(0?\.\d+)",
]

# Sample size patterns
SAMPLE_SIZE_PATTERNS = [
    r"[Nn]\s*=\s*(\d[\d,]*)",
    r"(\d[\d,]*)\s+participants",
    r"(\d[\d,]*)\s+subjects",
    r"(\d[\d,]*)\s+patients",
    r"sample\s+(?:size|of)\s+(\d[\d,]*)",
    r"(\d[\d,]*)\s+(?:individuals|respondents|cases)",
]

# Standard error patterns
SE_PATTERNS = [
    r"SE\s*=\s*([-+]?\d+\.?\d*)",
    r"standard\s+error\s*[=:]\s*([-+]?\d+\.?\d*)",
]

# Study design patterns
DESIGN_PATTERNS = [
    (r"\bRCT\b|randomized\s+controlled\s+trial", "RCT"),
    (r"\bmeta[-\s]?analysis\b", "Meta-analysis"),
    (r"\bsystematic\s+review\b", "Systematic Review"),
    (r"\bcohort\b", "Cohort"),
    (r"\bcase[-\s]?control\b", "Case-control"),
    (r"\bcross[-\s]?sectional\b", "Cross-sectional"),
    (r"\blongitudinal\b", "Longitudinal"),
    (r"\bprospective\b", "Prospective"),
    (r"\bretrospective\b", "Retrospective"),
    (r"\bobservational\b", "Observational"),
    (r"\bsurvey\b", "Survey"),
    (r"\bexperimental?\b", "Experimental"),
    (r"\breview\b", "Review"),
    (r"\bqualitative\b", "Qualitative"),
]

# Significance direction patterns
DIRECTION_PATTERNS = [
    (r"\b(?:significant(?:ly)?\s+)?(?:increase[ds]?|improve[ds]?|higher|greater|positive|beneficial|effective)\b", +1),
    (r"\b(?:significant(?:ly)?\s+)?(?:decrease[ds]?|reduce[ds]?|lower|less|negative|harmful|ineffective)\b", -1),
    (r"\b(?:no\s+(?:significant\s+)?(?:difference|effect|change|improvement)|not\s+significant|n\.?s\.?)\b", 0),
]


class StatisticalSynthesis:
    """Cross-study statistical synthesis engine.

    Performs meta-analytic computations entirely with numpy.
    No LLM involved — pure deterministic statistics.
    """

    def extract_effects(self, studies: list[dict]) -> list[StudyEffect]:
        """Extract effect sizes from structured study data.

        Input: list of dicts with keys from the extraction table
        (sample_size, key_finding, outcome, method, source, authors, year, confidence).

        Uses heuristics to extract numeric effects:
        - Parse direct effect sizes (d, OR, RR, etc.)
        - Parse confidence intervals
        - Estimate effect size from p-value + sample size when direct effect not available
        - Use sample size to compute SE when not provided
        """
        effects: list[StudyEffect] = []

        for i, study in enumerate(studies):
            # Combine text fields for pattern searching
            text = " ".join(str(study.get(field, "")) for field in ("key_finding", "outcome", "method", "source"))

            # Build study label
            authors = study.get("authors", "")
            year = study.get("year", "")
            label = f"{authors}, {year}" if authors and year else f"Study {i + 1}"

            # Extract sample size
            n = self._extract_sample_size(study, text)

            # Extract study design
            design = self._extract_design(study, text)

            # Extract effect size, SE, CI
            effect_size, effect_type, se, ci_lower, ci_upper = self._extract_effect(study, text, n)

            if effect_size is None:
                continue  # Skip studies where we cannot determine an effect

            # Ensure SE is computed
            if se is None or se <= 0:
                se = self._estimate_se(effect_size, n, ci_lower, ci_upper)

            if se is None or se <= 0:
                continue  # Cannot compute weight without SE

            # Compute CI if not yet available
            if ci_lower is None or ci_upper is None:
                ci_lower = effect_size - 1.96 * se
                ci_upper = effect_size + 1.96 * se

            # Compute inverse-variance weight
            weight = 1.0 / (se * se)

            effects.append(
                StudyEffect(
                    study_id=study.get("source_id", f"study_{i}"),
                    study_label=label,
                    effect_size=round(effect_size, 4),
                    se=round(se, 4),
                    ci_lower=round(ci_lower, 4),
                    ci_upper=round(ci_upper, 4),
                    n=n if n and n > 0 else 0,
                    weight=round(weight, 4),
                    study_design=design,
                )
            )

        return effects

    def _extract_sample_size(self, study: dict, text: str) -> int | None:
        """Extract sample size from study dict or text."""
        # First check structured field
        raw_n = study.get("sample_size", "")
        if raw_n:
            raw_str = str(raw_n).replace(",", "").strip()
            # Extract first number from the field
            m = re.search(r"(\d+)", raw_str)
            if m:
                n = int(m.group(1))
                if n > 0:
                    return n

        # Then try text patterns
        for pattern in SAMPLE_SIZE_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                n = int(m.group(1).replace(",", ""))
                if n > 0:
                    return n

        return None

    def _extract_design(self, study: dict, text: str) -> str:
        """Extract study design."""
        method = study.get("method", "")
        search_text = f"{method} {text}"

        for pattern, design_name in DESIGN_PATTERNS:
            if re.search(pattern, search_text, re.IGNORECASE):
                return design_name

        return method if method else "Unknown"

    def _extract_effect(
        self, study: dict, text: str, n: int | None
    ) -> tuple[float | None, str, float | None, float | None, float | None]:
        """Extract effect size from text patterns.

        Returns: (effect_size, effect_type, se, ci_lower, ci_upper)
        """
        effect_size = None
        effect_type = "SMD"
        se = None
        ci_lower = None
        ci_upper = None

        # Try direct effect size patterns
        for pattern, etype in EFFECT_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m and m.group(1):
                try:
                    raw_val = float(m.group(1))
                    effect_type = etype

                    # Convert ratio measures to log scale for meta-analysis
                    if etype in ("OR", "RR", "HR"):
                        if raw_val > 0:
                            effect_size = math.log(raw_val)
                        else:
                            continue
                    elif etype == "r":
                        # Fisher's z transformation for correlations
                        if -1 < raw_val < 1:
                            effect_size = 0.5 * math.log((1 + raw_val) / (1 - raw_val))
                        else:
                            continue
                    elif etype == "eta2":
                        # Convert eta-squared to Cohen's d
                        if 0 < raw_val < 1:
                            effect_size = 2.0 * math.sqrt(raw_val / (1 - raw_val))
                        else:
                            continue
                    elif etype == "pct":
                        # Convert percentage to approximate d
                        effect_size = raw_val / 100.0 * 2.0  # rough heuristic
                    else:
                        effect_size = raw_val

                    break
                except (ValueError, ZeroDivisionError):
                    continue

        # Try to extract CI
        for ci_pat in CI_PATTERNS:
            m = re.search(ci_pat, text, re.IGNORECASE)
            if m:
                try:
                    ci_lower = float(m.group(1))
                    ci_upper = float(m.group(2))

                    # Convert ratio CIs to log scale
                    if effect_type in ("OR", "RR", "HR") and ci_lower > 0 and ci_upper > 0:
                        ci_lower = math.log(ci_lower)
                        ci_upper = math.log(ci_upper)

                    # Derive SE from CI if we have it
                    if ci_lower is not None and ci_upper is not None:
                        se = (ci_upper - ci_lower) / (2 * 1.96)

                    break
                except (ValueError, IndexError):
                    continue

        # Try to extract SE directly
        if se is None:
            for se_pat in SE_PATTERNS:
                m = re.search(se_pat, text, re.IGNORECASE)
                if m:
                    try:
                        se = float(m.group(1))
                        break
                    except ValueError:
                        continue

        # If no direct effect size found, try to estimate from p-value + N
        if effect_size is None:
            effect_size, se = self._estimate_from_p_value(text, n)
            if effect_size is not None:
                # Determine direction from text
                direction = self._extract_direction(text)
                effect_size = abs(effect_size) * direction

        return (effect_size, effect_type, se, ci_lower, ci_upper)

    def _extract_direction(self, text: str) -> int:
        """Extract the direction of the effect from text."""
        for pattern, direction in DIRECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return direction if direction != 0 else 1
        return 1  # Default positive

    def _estimate_from_p_value(self, text: str, n: int | None) -> tuple[float | None, float | None]:
        """Estimate effect size from p-value and sample size.

        Uses: d = 2t / sqrt(N), where t = Phi_inv(1 - p/2)
        """
        p_value = None
        is_less_than = False

        for pattern in P_VALUE_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    p_value = float(m.group(1))
                    is_less_than = "<" in pattern
                    break
                except ValueError:
                    continue

        if p_value is None or n is None or n < 3:
            return (None, None)

        # For "p < X", use X as an upper bound (conservative)
        if is_less_than and p_value > 0:
            p_value = p_value  # Use the stated threshold

        # Clamp p-value
        if p_value <= 0:
            p_value = 0.0001
        if p_value >= 1:
            return (None, None)

        # Convert p-value to t-statistic
        t_stat = _norm_ppf(1.0 - p_value / 2.0)

        # Approximate degrees of freedom
        df = n - 2

        if df <= 0:
            return (None, None)

        # Estimate Cohen's d
        d = 2.0 * t_stat / math.sqrt(df)

        # SE of d = sqrt(1/n1 + 1/n2 + d^2 / (2*(n1+n2)))
        # Assuming equal groups: n1 = n2 = N/2
        n_half = max(n / 2.0, 1.0)
        se = math.sqrt(1.0 / n_half + 1.0 / n_half + d * d / (2.0 * n))

        return (d, se)

    def _estimate_se(
        self,
        effect_size: float,
        n: int | None,
        ci_lower: float | None,
        ci_upper: float | None,
    ) -> float | None:
        """Estimate standard error from available information."""
        # From CI
        if ci_lower is not None and ci_upper is not None:
            se = (ci_upper - ci_lower) / (2 * 1.96)
            if se > 0:
                return se

        # From sample size (for SMD)
        if n is not None and n > 2:
            # SE of Cohen's d ~ sqrt(1/n1 + 1/n2 + d^2/(2*N))
            n_half = max(n / 2.0, 1.0)
            se = math.sqrt(1.0 / n_half + 1.0 / n_half + effect_size * effect_size / (2.0 * n))
            if se > 0:
                return se

        return None

    def fixed_effects_meta(self, effects: list[StudyEffect]) -> SynthesisResult:
        """Inverse-variance fixed-effects meta-analysis.

        Formulas:
            w_i = 1 / SE_i^2
            pooled = sum(w_i * theta_i) / sum(w_i)
            SE_pooled = 1 / sqrt(sum(w_i))
            Q = sum(w_i * (theta_i - pooled)^2)
            I^2 = max(0, (Q - (k-1)) / Q * 100)
        """
        k = len(effects)
        if k == 0:
            return self._empty_result("fixed")

        theta = np.array([e.effect_size for e in effects], dtype=np.float64)
        se_arr = np.array([e.se for e in effects], dtype=np.float64)

        # Weights
        w = 1.0 / (se_arr**2)

        # Pooled effect
        pooled = float(np.sum(w * theta) / np.sum(w))

        # SE of pooled effect
        pooled_se = float(1.0 / np.sqrt(np.sum(w)))

        # 95% CI
        pooled_ci_lower = pooled - 1.96 * pooled_se
        pooled_ci_upper = pooled + 1.96 * pooled_se

        # Z-test
        pooled_z = pooled / pooled_se if pooled_se > 0 else 0.0
        pooled_p = _z_to_p(pooled_z)

        # Cochran's Q statistic
        q_stat = float(np.sum(w * (theta - pooled) ** 2))

        # Q p-value (chi-squared with k-1 df)
        q_p = _chi2_sf(q_stat, k - 1) if k > 1 else 1.0

        # I-squared
        i_sq = max(0.0, (q_stat - (k - 1)) / q_stat * 100.0) if q_stat > 0 else 0.0

        # Tau-squared (DerSimonian-Laird estimator, for reference)
        sum_w = float(np.sum(w))
        sum_w2 = float(np.sum(w**2))
        c = sum_w - sum_w2 / sum_w if sum_w > 0 else 1.0
        tau_sq = max(0.0, (q_stat - (k - 1)) / c) if c > 0 else 0.0

        # Update study weights as percentages
        total_w = float(np.sum(w))
        for j, eff in enumerate(effects):
            eff.weight = round(float(w[j]) / total_w * 100.0, 2) if total_w > 0 else 0.0

        total_n = sum(e.n for e in effects)

        result = SynthesisResult(
            pooled_effect=round(pooled, 4),
            pooled_se=round(pooled_se, 4),
            pooled_ci_lower=round(pooled_ci_lower, 4),
            pooled_ci_upper=round(pooled_ci_upper, 4),
            pooled_z=round(pooled_z, 4),
            pooled_p=round(pooled_p, 6),
            q_statistic=round(q_stat, 4),
            q_p_value=round(q_p, 6),
            i_squared=round(i_sq, 2),
            tau_squared=round(tau_sq, 4),
            studies=effects,
            model="fixed",
            effect_measure=self._determine_effect_measure(effects),
            k=k,
            total_n=total_n,
        )

        result.forest_plot_data = self.compute_forest_plot_data(result)
        return result

    def random_effects_meta(self, effects: list[StudyEffect]) -> SynthesisResult:
        """DerSimonian-Laird random-effects meta-analysis.

        First computes fixed-effects Q, then:
            tau^2 = max(0, (Q - k + 1) / (sum(w) - sum(w^2)/sum(w)))
            w_i* = 1 / (SE_i^2 + tau^2)
            pooled* = sum(w_i* * theta_i) / sum(w_i*)
        """
        k = len(effects)
        if k == 0:
            return self._empty_result("random")

        theta = np.array([e.effect_size for e in effects], dtype=np.float64)
        se_arr = np.array([e.se for e in effects], dtype=np.float64)

        # Fixed-effects weights for Q computation
        w_fixed = 1.0 / (se_arr**2)

        # Fixed-effects pooled (for Q computation)
        pooled_fixed = float(np.sum(w_fixed * theta) / np.sum(w_fixed))

        # Cochran's Q
        q_stat = float(np.sum(w_fixed * (theta - pooled_fixed) ** 2))

        # Tau-squared
        sum_w = float(np.sum(w_fixed))
        sum_w2 = float(np.sum(w_fixed**2))
        c = sum_w - sum_w2 / sum_w if sum_w > 0 else 1.0
        tau_sq = max(0.0, (q_stat - (k - 1)) / c) if c > 0 else 0.0

        # Random-effects weights
        w_star = 1.0 / (se_arr**2 + tau_sq)

        # Random-effects pooled
        pooled = float(np.sum(w_star * theta) / np.sum(w_star))

        # SE of pooled
        pooled_se = float(1.0 / np.sqrt(np.sum(w_star)))

        # 95% CI
        pooled_ci_lower = pooled - 1.96 * pooled_se
        pooled_ci_upper = pooled + 1.96 * pooled_se

        # Z-test
        pooled_z = pooled / pooled_se if pooled_se > 0 else 0.0
        pooled_p = _z_to_p(pooled_z)

        # Q p-value
        q_p = _chi2_sf(q_stat, k - 1) if k > 1 else 1.0

        # I-squared
        i_sq = max(0.0, (q_stat - (k - 1)) / q_stat * 100.0) if q_stat > 0 else 0.0

        # Update study weights as percentages (using random-effects weights)
        total_w_star = float(np.sum(w_star))
        for j, eff in enumerate(effects):
            eff.weight = round(float(w_star[j]) / total_w_star * 100.0, 2) if total_w_star > 0 else 0.0

        total_n = sum(e.n for e in effects)

        result = SynthesisResult(
            pooled_effect=round(pooled, 4),
            pooled_se=round(pooled_se, 4),
            pooled_ci_lower=round(pooled_ci_lower, 4),
            pooled_ci_upper=round(pooled_ci_upper, 4),
            pooled_z=round(pooled_z, 4),
            pooled_p=round(pooled_p, 6),
            q_statistic=round(q_stat, 4),
            q_p_value=round(q_p, 6),
            i_squared=round(i_sq, 2),
            tau_squared=round(tau_sq, 4),
            studies=effects,
            model="random",
            effect_measure=self._determine_effect_measure(effects),
            k=k,
            total_n=total_n,
        )

        result.forest_plot_data = self.compute_forest_plot_data(result)
        return result

    def auto_synthesize(self, studies: list[dict]) -> SynthesisResult:
        """Full pipeline: extract effects -> choose model -> synthesize.

        Steps:
        1. Extract effects from study data
        2. Run fixed-effects first to get I-squared
        3. If I-squared > 50%, use random effects; else fixed effects
        4. Return full result with forest plot data
        """
        effects = self.extract_effects(studies)

        if len(effects) < 2:
            if len(effects) == 1:
                # Single study — return its effect as the "pooled" result
                e = effects[0]
                e.weight = 100.0
                result = SynthesisResult(
                    pooled_effect=e.effect_size,
                    pooled_se=e.se,
                    pooled_ci_lower=e.ci_lower,
                    pooled_ci_upper=e.ci_upper,
                    pooled_z=round(e.effect_size / e.se if e.se > 0 else 0.0, 4),
                    pooled_p=round(_z_to_p(e.effect_size / e.se) if e.se > 0 else 1.0, 6),
                    q_statistic=0.0,
                    q_p_value=1.0,
                    i_squared=0.0,
                    tau_squared=0.0,
                    studies=effects,
                    model="single",
                    effect_measure="SMD",
                    k=1,
                    total_n=e.n,
                )
                result.forest_plot_data = self.compute_forest_plot_data(result)
                return result

            return self._empty_result("none")

        # Step 1: Run fixed-effects to check heterogeneity
        fixed_result = self.fixed_effects_meta(list(effects))

        # Step 2: Decide model based on I-squared
        if fixed_result.i_squared > 50.0:
            # Substantial heterogeneity — use random effects
            # Re-create effects list since fixed_effects_meta mutated weights
            effects = self.extract_effects(studies)
            return self.random_effects_meta(effects)
        else:
            return fixed_result

    def compute_forest_plot_data(self, result: SynthesisResult) -> list[dict]:
        """Pre-compute forest plot rendering data.

        Returns a list of dicts, one per study plus a summary row:
        {
            type: 'study' | 'summary',
            label, effect, ci_lower, ci_upper,
            weight_pct, row_index
        }
        """
        plot_data: list[dict] = []

        for i, study in enumerate(result.studies):
            plot_data.append(
                {
                    "type": "study",
                    "label": study.study_label,
                    "effect": study.effect_size,
                    "ci_lower": study.ci_lower,
                    "ci_upper": study.ci_upper,
                    "weight_pct": study.weight,
                    "n": study.n,
                    "se": study.se,
                    "design": study.study_design,
                    "row_index": i,
                }
            )

        # Summary diamond
        plot_data.append(
            {
                "type": "summary",
                "label": f"Overall ({result.model.title()} Effects)",
                "effect": result.pooled_effect,
                "ci_lower": result.pooled_ci_lower,
                "ci_upper": result.pooled_ci_upper,
                "weight_pct": 100.0,
                "n": result.total_n,
                "se": result.pooled_se,
                "design": "",
                "row_index": len(result.studies),
            }
        )

        return plot_data

    def _determine_effect_measure(self, effects: list[StudyEffect]) -> str:
        """Determine the effect measure label based on effect sizes."""
        # For now, default to SMD. Could be extended to detect OR/RR/etc.
        return "SMD"

    def _empty_result(self, model: str) -> SynthesisResult:
        """Return an empty synthesis result when no effects can be extracted."""
        return SynthesisResult(
            pooled_effect=0.0,
            pooled_se=0.0,
            pooled_ci_lower=0.0,
            pooled_ci_upper=0.0,
            pooled_z=0.0,
            pooled_p=1.0,
            q_statistic=0.0,
            q_p_value=1.0,
            i_squared=0.0,
            tau_squared=0.0,
            studies=[],
            model=model,
            effect_measure="SMD",
            k=0,
            total_n=0,
            forest_plot_data=[],
        )

    def result_to_dict(self, result: SynthesisResult) -> dict:
        """Serialize SynthesisResult to a JSON-friendly dict."""
        return {
            "pooled_effect": result.pooled_effect,
            "pooled_se": result.pooled_se,
            "pooled_ci_lower": result.pooled_ci_lower,
            "pooled_ci_upper": result.pooled_ci_upper,
            "pooled_z": result.pooled_z,
            "pooled_p": result.pooled_p,
            "q_statistic": result.q_statistic,
            "q_p_value": result.q_p_value,
            "i_squared": result.i_squared,
            "tau_squared": result.tau_squared,
            "studies": [
                {
                    "study_id": s.study_id,
                    "study_label": s.study_label,
                    "effect_size": s.effect_size,
                    "se": s.se,
                    "ci_lower": s.ci_lower,
                    "ci_upper": s.ci_upper,
                    "n": s.n,
                    "weight": s.weight,
                    "study_design": s.study_design,
                }
                for s in result.studies
            ],
            "model": result.model,
            "effect_measure": result.effect_measure,
            "k": result.k,
            "total_n": result.total_n,
            "forest_plot_data": result.forest_plot_data,
        }
