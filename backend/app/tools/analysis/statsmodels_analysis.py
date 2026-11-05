"""Small, auditable wrappers around optional statsmodels analyses.

The wrappers intentionally return JSON-friendly dictionaries and keep the
dependency lazy. Ordinary queries and aggregation therefore do not import or
require statsmodels at runtime.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Sequence


class StatsmodelsUnavailableError(RuntimeError):
    """Raised when an analysis is requested without the optional dependency."""


def statsmodels_available() -> bool:
    try:
        import statsmodels  # noqa: F401
    except ImportError:
        return False
    return True


def run_trend_analysis(
    values: Sequence[float],
    *,
    time: Sequence[float] | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Estimate a linear trend and return slope, interval and diagnostics."""
    y, x = _paired_values(values, time)
    _validate_alpha(alpha)
    if len(y) < 3:
        raise ValueError("trend analysis requires at least 3 valid observations")
    result = _fit_ols(y, x, alpha=alpha)
    slope = result["coefficients"]["x"]
    return {
        "analysis": "linear_trend",
        "input_n": len(values),
        "n": result["n"],
        "missing_n": len(values) - result["n"],
        "slope": slope["estimate"],
        "slope_ci": slope["confidence_interval"],
        "p_value": slope["p_value"],
        "r_squared": result["r_squared"],
        "alpha": alpha,
        "x_range": [x[0], x[-1]],
    }


def run_regression_analysis(
    response: Sequence[float],
    predictor: Sequence[float],
    *,
    alpha: float = 0.05,
    robust: bool = False,
) -> dict[str, Any]:
    """Fit a one-predictor OLS model with optional HC3 robust errors."""
    y, x = _paired_values(response, predictor)
    _validate_alpha(alpha)
    if len(y) < 5:
        raise ValueError("regression analysis requires at least 5 valid observations")
    result = _fit_ols(y, x, alpha=alpha, robust=robust)
    result["input_n"] = len(response)
    result["missing_n"] = len(response) - result["n"]
    return result


def run_seasonal_decomposition(
    values: Sequence[float],
    *,
    period: int,
) -> dict[str, Any]:
    """Decompose a regular series with STL and return JSON-friendly arrays."""
    numeric = _finite_values(values)
    if period < 2:
        raise ValueError("period must be at least 2")
    if len(numeric) < period * 2:
        raise ValueError("seasonal decomposition requires at least two periods")
    try:
        from statsmodels.tsa.seasonal import STL
    except ImportError as exc:
        raise StatsmodelsUnavailableError(_INSTALL_MESSAGE) from exc
    fitted = STL(numeric, period=period, robust=True).fit()
    return {
        "analysis": "stl_decomposition",
        "input_n": len(values),
        "n": len(numeric),
        "missing_n": len(values) - len(numeric),
        "period": period,
        "observed": numeric,
        "trend": fitted.trend.tolist(),
        "seasonal": fitted.seasonal.tolist(),
        "resid": fitted.resid.tolist(),
    }


def _fit_ols(
    y: list[float],
    x: list[float],
    *,
    alpha: float,
    robust: bool = False,
) -> dict[str, Any]:
    try:
        import numpy as np
        import statsmodels.api as sm
    except ImportError as exc:
        raise StatsmodelsUnavailableError(_INSTALL_MESSAGE) from exc
    model = sm.OLS(np.asarray(y), sm.add_constant(np.asarray(x))).fit(
        cov_type="HC3" if robust else "nonrobust"
    )
    interval = model.conf_int(alpha=alpha)
    names = ["const", "x"]
    coefficients = {
        name: {
            "estimate": float(model.params[index]),
            "p_value": float(model.pvalues[index]),
            "confidence_interval": [float(interval[index, 0]), float(interval[index, 1])],
        }
        for index, name in enumerate(names)
    }
    return {
        "analysis": "ols_regression",
        "n": len(y),
        "robust_errors": robust,
        "alpha": alpha,
        "coefficients": coefficients,
        "r_squared": float(model.rsquared),
        "adjusted_r_squared": float(model.rsquared_adj),
        "f_p_value": float(model.f_pvalue),
    }


def _paired_values(
    values: Sequence[float],
    time: Sequence[float] | None,
) -> tuple[list[float], list[float]]:
    y = _finite_values(values)
    if time is None:
        x = list(range(len(y)))
    else:
        if len(time) != len(values):
            raise ValueError("time and values must have the same length")
        pairs = [(float(x_value), float(y_value)) for x_value, y_value in zip(time, values)]
        pairs = [(x_value, y_value) for x_value, y_value in pairs if isfinite(x_value) and isfinite(y_value)]
        x = [item[0] for item in pairs]
        y = [item[1] for item in pairs]
    if len(x) != len(y):
        raise ValueError("values contain non-numeric or non-finite observations")
    if len(set(x)) < 2:
        raise ValueError("predictor must contain at least two distinct values")
    return y, x


def _finite_values(values: Sequence[float]) -> list[float]:
    numeric = [float(value) for value in values]
    return [value for value in numeric if isfinite(value)]


def _validate_alpha(alpha: float) -> None:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")


_INSTALL_MESSAGE = (
    "statsmodels is not installed; add it to the backend_py311 environment "
    "before requesting regression or seasonal decomposition analysis"
)
