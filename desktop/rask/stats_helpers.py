"""stats_helpers.py — Statistical helper functions for Rask analytics.

Provides pure-Python implementations of common statistical functions used
by the analytics module and stats screen. No external dependencies.

Functions:
  - mean, median, mode
  - variance, stdev, population_stdev
  - percentile (p25, p50, p75, p90, p95, p99)
  - quartiles, iqr
  - min, max, range
  - sum, count
  - correlation (Pearson, Spearman)
  - linear_regression
  - moving_average, exponential_smoothing
  - detect_trend, detect_outliers
  - normalize, standardize
  - histogram_bins
  - entropy (Shannon)
  - gini_coefficient
"""
from __future__ import annotations
import math
from typing import Optional, Sequence


# =====================================================================
# === BASIC STATISTICS ===
# =====================================================================
def mean(values: Sequence[float]) -> float:
    """Arithmetic mean (average)."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def median(values: Sequence[float]) -> float:
    """Median (middle value when sorted)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return float(sorted_vals[n // 2])
    return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0


def mode(values: Sequence[float]) -> list[float]:
    """Mode (most frequent value(s)). Returns a list (may have multiple)."""
    if not values:
        return []
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    max_count = max(counts.values())
    return sorted([v for v, c in counts.items() if c == max_count])


def variance(values: Sequence[float], sample: bool = True) -> float:
    """Variance. If sample=True, uses n-1 denominator (sample variance)."""
    if not values:
        return 0.0
    m = mean(values)
    n = len(values)
    denom = n - 1 if sample and n > 1 else n
    return sum((v - m) ** 2 for v in values) / denom


def stdev(values: Sequence[float], sample: bool = True) -> float:
    """Standard deviation. If sample=True, uses n-1 denominator."""
    return math.sqrt(variance(values, sample))


def population_stdev(values: Sequence[float]) -> float:
    """Population standard deviation (uses n denominator)."""
    return stdev(values, sample=False)


def min_val(values: Sequence[float]) -> float:
    """Minimum value."""
    return min(values) if values else 0.0


def max_val(values: Sequence[float]) -> float:
    """Maximum value."""
    return max(values) if values else 0.0


def range_val(values: Sequence[float]) -> float:
    """Range (max - min)."""
    if not values:
        return 0.0
    return max(values) - min(values)


def sum_val(values: Sequence[float]) -> float:
    """Sum of all values."""
    return sum(values)


def count_val(values: Sequence[float]) -> int:
    """Count of values."""
    return len(values)


# =====================================================================
# === PERCENTILES ===
# =====================================================================
def percentile(values: Sequence[float], p: float) -> float:
    """Compute the p-th percentile (0 <= p <= 100) using linear interpolation.
    
    Uses the same method as numpy's default (linear interpolation between
    closest ranks).
    """
    if not values:
        return 0.0
    if p < 0:
        p = 0
    elif p > 100:
        p = 100
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    # Rank (1-indexed)
    rank = (p / 100) * (n - 1) + 1
    lower_idx = int(math.floor(rank)) - 1
    upper_idx = int(math.ceil(rank)) - 1
    if lower_idx == upper_idx:
        return float(sorted_vals[lower_idx])
    # Linear interpolation
    lower_val = sorted_vals[lower_idx]
    upper_val = sorted_vals[upper_idx]
    frac = rank - (lower_idx + 1)
    return lower_val + (upper_val - lower_val) * frac


def p25(values: Sequence[float]) -> float:
    """25th percentile (first quartile)."""
    return percentile(values, 25)


def p50(values: Sequence[float]) -> float:
    """50th percentile (median)."""
    return percentile(values, 50)


def p75(values: Sequence[float]) -> float:
    """75th percentile (third quartile)."""
    return percentile(values, 75)


def p90(values: Sequence[float]) -> float:
    """90th percentile."""
    return percentile(values, 90)


def p95(values: Sequence[float]) -> float:
    """95th percentile."""
    return percentile(values, 95)


def p99(values: Sequence[float]) -> float:
    """99th percentile."""
    return percentile(values, 99)


def quartiles(values: Sequence[float]) -> tuple[float, float, float]:
    """Return (Q1, Q2, Q3) — i.e., p25, p50, p75."""
    return (p25(values), p50(values), p75(values))


def iqr(values: Sequence[float]) -> float:
    """Interquartile range (Q3 - Q1)."""
    q1, _, q3 = quartiles(values)
    return q3 - q1


# =====================================================================
# === CORRELATION ===
# =====================================================================
def pearson_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Pearson correlation coefficient (-1 to 1)."""
    if len(x) != len(y) or not x:
        return 0.0
    n = len(x)
    mx = mean(x)
    my = mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def spearman_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation coefficient (-1 to 1)."""
    if len(x) != len(y) or not x:
        return 0.0
    # Convert to ranks
    x_ranks = _rank(x)
    y_ranks = _rank(y)
    return pearson_correlation(x_ranks, y_ranks)


def _rank(values: Sequence[float]) -> list[float]:
    """Return ranks (1-indexed, with ties getting average rank)."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        # Find ties
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        # Average rank for tied values
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


# =====================================================================
# === LINEAR REGRESSION ===
# =====================================================================
def linear_regression(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float]:
    """Simple linear regression: y = slope * x + intercept.
    
    Returns (slope, intercept, r_squared).
    """
    if len(x) != len(y) or len(x) < 2:
        return (0.0, 0.0, 0.0)
    n = len(x)
    mx = mean(x)
    my = mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = sum((xi - mx) ** 2 for xi in x)
    if den == 0:
        return (0.0, my, 0.0)
    slope = num / den
    intercept = my - slope * mx
    # R-squared
    r = pearson_correlation(x, y)
    r_squared = r * r
    return (slope, intercept, r_squared)


# =====================================================================
# === TIME SERIES ===
# =====================================================================
def moving_average(values: Sequence[float], window: int = 7) -> list[float]:
    """Simple moving average with the given window size."""
    if window < 1:
        window = 1
    if not values:
        return []
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start:i + 1]
        result.append(mean(window_vals))
    return result


def exponential_smoothing(values: Sequence[float], alpha: float = 0.3) -> list[float]:
    """Exponential smoothing (single-parameter).
    
    alpha: smoothing factor (0 < alpha < 1). Higher = more weight on recent values.
    """
    if not values:
        return []
    alpha = max(0.0, min(1.0, alpha))
    result = [values[0]]
    for i in range(1, len(values)):
        smoothed = alpha * values[i] + (1 - alpha) * result[-1]
        result.append(smoothed)
    return result


def detect_trend(values: Sequence[float]) -> str:
    """Detect trend direction: 'up', 'down', or 'flat'.
    
    Uses linear regression slope with a small threshold.
    """
    if len(values) < 2:
        return "flat"
    slope, _, r_sq = linear_regression(list(range(len(values))), values)
    # Threshold: 1% of the mean
    threshold = abs(mean(values)) * 0.01
    if slope > threshold:
        return "up"
    if slope < -threshold:
        return "down"
    return "flat"


def detect_outliers(values: Sequence[float], threshold: float = 1.5) -> list[int]:
    """Detect outlier indices using the IQR method.
    
    Returns indices of values that are < Q1 - threshold*IQR or > Q3 + threshold*IQR.
    """
    if len(values) < 4:
        return []
    q1, _, q3 = quartiles(values)
    iqr_val = q3 - q1
    lower = q1 - threshold * iqr_val
    upper = q3 + threshold * iqr_val
    return [i for i, v in enumerate(values) if v < lower or v > upper]


# =====================================================================
# === NORMALIZATION ===
# =====================================================================
def normalize(values: Sequence[float]) -> list[float]:
    """Min-max normalize to [0, 1]."""
    if not values:
        return []
    mn = min(values)
    mx = max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def standardize(values: Sequence[float]) -> list[float]:
    """Z-score standardize (mean=0, stdev=1)."""
    if not values:
        return []
    m = mean(values)
    s = stdev(values)
    if s == 0:
        return [0.0] * len(values)
    return [(v - m) / s for v in values]


# =====================================================================
# === HISTOGRAM ===
# =====================================================================
def histogram_bins(values: Sequence[float], n_bins: int = 10) -> list[tuple[float, float, int]]:
    """Compute histogram bins.
    
    Returns list of (bin_start, bin_end, count) tuples.
    """
    if not values or n_bins < 1:
        return []
    mn = min(values)
    mx = max(values)
    if mx == mn:
        return [(mn, mx, len(values))]
    bin_width = (mx - mn) / n_bins
    bins = [(mn + i * bin_width, mn + (i + 1) * bin_width, 0) for i in range(n_bins)]
    counts = [0] * n_bins
    for v in values:
        idx = int((v - mn) / bin_width)
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1
    return [(bins[i][0], bins[i][1], counts[i]) for i in range(n_bins)]


def optimal_bin_count(n: int) -> int:
    """Compute optimal histogram bin count using Sturges' rule.
    
    Returns max(1, ceil(log2(n) + 1)).
    """
    if n < 1:
        return 1
    return max(1, int(math.ceil(math.log2(n) + 1)))


# =====================================================================
# === ENTROPY (Shannon) ===
# =====================================================================
def shannon_entropy(probabilities: Sequence[float]) -> float:
    """Shannon entropy (base 2) given a list of probabilities."""
    if not probabilities:
        return 0.0
    entropy = 0.0
    for p in probabilities:
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def normalized_entropy(values: Sequence[float]) -> float:
    """Shannon entropy normalized to [0, 1].
    
    Useful for balance scores — 1 means perfectly uniform distribution.
    """
    if not values:
        return 0.0
    total = sum(values)
    if total == 0:
        return 0.0
    probs = [v / total for v in values if v > 0]
    if not probs:
        return 0.0
    entropy = shannon_entropy(probs)
    max_entropy = math.log2(len(probs)) if len(probs) > 1 else 1
    return entropy / max_entropy if max_entropy > 0 else 0.0


# =====================================================================
# === GINI COEFFICIENT ===
# =====================================================================
def gini_coefficient(values: Sequence[float]) -> float:
    """Gini coefficient (0 = perfect equality, 1 = perfect inequality).
    
    Measures distribution inequality — useful for "balance" assessment.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return 0.0
    cumulative = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    return (2 * cumulative) / (n * total) - (n + 1) / n


# =====================================================================
# === CHANGE POINT DETECTION ===
# =====================================================================
def detect_change_points(values: Sequence[float], threshold: float = 2.0) -> list[int]:
    """Detect change points in a time series.
    
    A change point is an index where the value differs from the previous by
    more than `threshold` standard deviations.
    """
    if len(values) < 3:
        return []
    s = stdev(values)
    if s == 0:
        return []
    change_points = []
    for i in range(1, len(values)):
        diff = abs(values[i] - values[i - 1])
        if diff > threshold * s:
            change_points.append(i)
    return change_points


# =====================================================================
# === AUTOCORRELATION ===
# =====================================================================
def autocorrelation(values: Sequence[float], lag: int = 1) -> float:
    """Compute autocorrelation at the given lag."""
    if len(values) <= lag:
        return 0.0
    m = mean(values)
    num = sum((values[i] - m) * (values[i + lag] - m) for i in range(len(values) - lag))
    den = sum((v - m) ** 2 for v in values)
    if den == 0:
        return 0.0
    return num / den


# =====================================================================
# === SUMMARY STATS ===
# =====================================================================
def summary(values: Sequence[float]) -> dict:
    """Compute a comprehensive summary of a numeric series.
    
    Returns dict with: count, sum, mean, median, mode, min, max, range,
    variance, stdev, p25, p50, p75, p90, p95, p99, iqr.
    """
    if not values:
        return {
            "count": 0, "sum": 0.0, "mean": 0.0, "median": 0.0,
            "mode": [], "min": 0.0, "max": 0.0, "range": 0.0,
            "variance": 0.0, "stdev": 0.0,
            "p25": 0.0, "p50": 0.0, "p75": 0.0,
            "p90": 0.0, "p95": 0.0, "p99": 0.0, "iqr": 0.0,
        }
    return {
        "count": len(values),
        "sum": sum(values),
        "mean": mean(values),
        "median": median(values),
        "mode": mode(values),
        "min": min(values),
        "max": max(values),
        "range": range_val(values),
        "variance": variance(values),
        "stdev": stdev(values),
        "p25": p25(values),
        "p50": p50(values),
        "p75": p75(values),
        "p90": p90(values),
        "p95": p95(values),
        "p99": p99(values),
        "iqr": iqr(values),
    }


def format_summary(stats: dict, lang: str = "fa") -> str:
    """Format a stats summary dict as a human-readable string."""
    from .i18n import to_fa_digits
    lines = []
    for key, val in stats.items():
        if isinstance(val, list):
            val_str = ", ".join(str(v) for v in val)
        elif isinstance(val, float):
            val_str = f"{val:.2f}"
        else:
            val_str = str(val)
        if lang == "fa":
            val_str = to_fa_digits(val_str)
        lines.append(f"{key}: {val_str}")
    return "\n".join(lines)
