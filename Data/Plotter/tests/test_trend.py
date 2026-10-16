"""Trend-line fits recover known models."""
import numpy as np
import pytest

from rsplot.plots.trend import confidence_band, fit_trend, lowess
from rsplot.spec import PlotSpec

X = np.linspace(1, 10, 40)


@pytest.mark.parametrize("kind,y,check", [
    ("linear", 2 + 3 * X, lambda f: np.allclose(f.coef, [3, 2])),
    ("quadratic", 1 - 2 * X + 0.5 * X ** 2, lambda f: np.allclose(f.coef, [0.5, -2, 1])),
    ("cubic", 0.1 * X ** 3 - X, lambda f: np.allclose(f.coef, [0.1, 0, -1, 0], atol=1e-8)),
    ("exponential", 2 * np.exp(0.3 * X), lambda f: np.allclose(f.coef, [2, 0.3])),
    ("logarithmic", 1 + 4 * np.log(X), lambda f: np.allclose(f.coef, [1, 4])),
    ("power", 3 * X ** 1.5, lambda f: np.allclose(f.coef, [3, 1.5])),
])
def test_parametric_fits_recover_parameters(kind, y, check):
    f = fit_trend(X, y, kind)
    assert not isinstance(f, str) and check(f) and f.r2 > 0.999999
    assert np.allclose(f.predict(X), y)


def test_lowess_follows_sine():
    x = np.linspace(0, 2 * np.pi, 200)
    y = np.sin(x) + np.random.default_rng(1).normal(0, 0.1, x.size)
    assert np.max(np.abs(lowess(x, y, 0.2) - np.sin(x))[10:-10]) < 0.15


def test_moving_median_ignores_spike():
    y = np.ones_like(X)
    y[20] = 50
    f = fit_trend(X, y, "moving median", window=5)
    assert np.allclose(f.predict(X), 1)


@pytest.mark.parametrize("kind,x,y,reason", [
    ("power", X - 5, X, "x > 0"), ("logarithmic", X - 5, X, "x > 0"),
    ("exponential", X, X - 5, "y > 0"), ("cubic", X[:4], X[:4], "at least 5"),
])
def test_invalid_data_gives_reason(kind, x, y, reason):
    r = fit_trend(x, y, kind)
    assert isinstance(r, str) and reason in r


def test_confidence_band_contains_fit():
    y = 2 + 3 * X + np.random.default_rng(0).normal(0, 1, X.size)
    lo, hi = confidence_band(X, y, 1, X)
    f = fit_trend(X, y, "linear")
    assert np.all(lo <= f.predict(X)) and np.all(f.predict(X) <= hi) and np.all(hi - lo > 0)


def test_old_fit_option_is_migrated():
    spec = PlotSpec.from_dict({"plot_type": "scatter", "options": {"fit": "linear"}})
    assert spec.options == {"trend": "linear"}
