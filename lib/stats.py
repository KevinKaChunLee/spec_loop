"""Student's t distribution, Welch's two-sample test and paired tests for binary outcomes, without
SciPy."""

from __future__ import annotations

import itertools
import math
import random
import statistics

_TINY = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction of the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > _TINY else _TINY)
            c = 1 + aa / c
            c = c if abs(c) > _TINY else _TINY
            h *= d * c
        if abs(d * c - 1) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t: float, df: float) -> float:
    """P(|T| >= |t|) for Student's t with `df` degrees of freedom."""
    return betainc(df / 2, 0.5, df / (df + t * t))


def t_quantile(q: float, df: float) -> float:
    """The q-quantile of Student's t (0.5 < q < 1)."""
    target = 2 * (1 - q)
    hi = 1.0
    while t_two_sided_p(hi, df) > target:
        hi *= 2
    lo = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if t_two_sided_p(mid, df) > target else (lo, mid)
    return (lo + hi) / 2


def welch(a: list[float], b: list[float], alpha: float = 0.05) -> dict:
    """Welch's t test of mean(a) - mean(b), two-sided; df by Welch-Satterthwaite."""
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    diff, se = statistics.mean(a) - statistics.mean(b), math.sqrt(va + vb)
    if se == 0:
        return {"diff": round(diff, 2), "se": 0.0, "df": None, "t": None, "p": None, "t_crit": None,
                "critical_diff": None, "significant": False}
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    t, crit = diff / se, t_quantile(1 - alpha / 2, df)
    p = t_two_sided_p(t, df)
    return {"diff": round(diff, 2), "se": round(se, 2), "df": round(df, 1), "t": round(t, 2),
            "p": round(p, 4), "t_crit": round(crit, 2), "critical_diff": round(crit * se, 2),
            "significant": p < alpha}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pairs: b where only the first arm
    succeeds, c where only the second does (a binomial test of b against n = b + c, p = 1/2)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def sign_flip(diffs: list[float], max_exact: int = 20, rounds: int = 200_000, seed: int = 0) -> float:
    """Two-sided paired permutation p-value for mean(diffs) = 0: the share of sign assignments
    whose |sum| is at least the observed one. Exact up to `max_exact` pairs, sampled beyond."""
    observed = abs(sum(diffs))
    if not diffs or observed == 0:
        return 1.0
    eps = 1e-12 * max(1.0, observed)
    if len(diffs) <= max_exact:
        signs = itertools.product((1, -1), repeat=len(diffs))
        hits = sum(1 for s in signs if abs(sum(x * d for x, d in zip(s, diffs))) >= observed - eps)
        return hits / 2 ** len(diffs)
    rng = random.Random(seed)
    hits = sum(1 for _ in range(rounds)
               if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - eps)
    return (hits + 1) / (rounds + 1)
