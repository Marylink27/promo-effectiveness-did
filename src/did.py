"""Оценка эффекта акций методом разности разностей (Difference-in-Differences).

Модель для показателя y магазина s в неделю t:
    y_st = b * (treat_s * post_t) + a_s + g_t + e_st
a_s: фиксированный эффект магазина (разный масштаб точек),
g_t: фиксированный эффект недели (сезон, погода, общие события),
b:   эффект акции, ошибки кластеризуются по магазинам.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src import config

# Показатели для кампаний с товарной механикой и для акции на весь чек
CATEGORY_OUTCOMES = {
    "part_units": "Продажи участников, шт",
    "part_revenue": "Выручка участников, руб",
    "part_margin": "Маржа участников, руб",
    "nonpart_revenue": "Выручка неучастников категории, руб",
    "category_margin": "Маржа категории, руб",
    "halo_margin": "Маржа прочих категорий, руб",
}
BASKET_OUTCOMES = {
    "store_revenue": "Выручка магазина, руб",
    "store_margin": "Маржа магазина с учётом подарков, руб",
    "receipts": "Число чеков",
    "avg_check": "Средний чек, руб",
}


def build_panel(marts: dict[str, pd.DataFrame], promo_id: str,
                pre_weeks: int = config.PRE_WEEKS,
                post_weeks: int = config.POST_WEEKS) -> pd.DataFrame:
    """Панель магазин x неделя вокруг волны акции с флагами treat и post."""
    cal = marts["promo_calendar"].set_index("promo_id").loc[promo_id]
    campaign = cal.campaign
    w0, w1 = int(cal.start_week), int(cal.end_week)
    weeks = range(w0 - pre_weeks, w1 + post_weeks + 1)

    sw = marts["mart_store_week"]
    panel = sw[sw.week.isin(weeks)][["store_id", "week", "revenue", "margin", "receipts", "avg_check"]]
    panel = panel.rename(columns={"revenue": "store_revenue", "margin": "store_margin"})

    gw = marts["mart_group_week"]
    gw = gw[gw.week.isin(weeks)]
    piv = gw.pivot_table(index=["store_id", "week"], columns="promo_group",
                         values=["units", "revenue", "margin"], aggfunc="sum", fill_value=0)

    def col(metric: str, group: str) -> pd.Series:
        key = (metric, group)
        return piv[key] if key in piv.columns else pd.Series(0.0, index=piv.index)

    grp = pd.DataFrame({
        "part_units": col("units", f"{campaign} участники"),
        "part_revenue": col("revenue", f"{campaign} участники"),
        "part_margin": col("margin", f"{campaign} участники"),
        "nonpart_revenue": col("revenue", f"{campaign} не участники"),
        "nonpart_margin": col("margin", f"{campaign} не участники"),
        "halo_margin": col("margin", "Прочие категории"),
    }).reset_index()
    grp["category_margin"] = grp.part_margin + grp.nonpart_margin
    panel = panel.merge(grp, on=["store_id", "week"], how="left")

    treated = set(marts["promo_stores"].query("promo_id == @promo_id").store_id)
    panel["treat"] = panel.store_id.isin(treated).astype(int)
    panel["rel_week"] = panel.week - w0
    panel["post"] = panel.week.between(w0, w1).astype(int)
    panel["period"] = np.select(
        [panel.week < w0, panel.week <= w1], ["до акции", "акция"], "после акции")
    panel["promo_id"] = promo_id
    return panel.sort_values(["store_id", "week"]).reset_index(drop=True)


def did_estimate(panel: pd.DataFrame, outcome: str, log: bool = False) -> dict:
    """DiD на окне "до акции + акция" с FE магазина и недели."""
    d = panel[panel.period != "после акции"].copy()
    d["y"] = np.log(d[outcome]) if log else d[outcome]
    d["treat_post"] = d.treat * d.post
    fit = smf.ols("y ~ treat_post + C(store_id) + C(week)", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d.store_id.astype("category").cat.codes})
    b, se, p = fit.params["treat_post"], fit.bse["treat_post"], fit.pvalues["treat_post"]
    lo, hi = fit.conf_int().loc["treat_post"]
    actual = d.loc[(d.treat == 1) & (d.post == 1), outcome].mean()
    if log:
        pct, cf = np.expm1(b), actual / np.exp(b)
    else:
        cf = actual - b
        pct = b / cf if cf else np.nan
    return {"outcome": outcome, "coef": b, "se": se, "p_value": p, "ci_low": lo, "ci_high": hi,
            "treated_actual_mean": actual, "counterfactual_mean": cf, "effect_pct": pct,
            "n_obs": int(fit.nobs)}


def event_study(panel: pd.DataFrame, outcome: str, log: bool = True) -> pd.DataFrame:
    """Эффекты по неделям относительно старта (опорная неделя -1).

    Коэффициенты до старта акции должны быть около нуля: это проверка
    допущения о параллельных трендах.
    """
    d = panel.copy()
    d["y"] = np.log(d[outcome]) if log else d[outcome]
    ks = sorted(k for k in d.rel_week.unique() if k != -1)
    terms = []
    for k in ks:
        name = f"ev_{'m' if k < 0 else 'p'}{abs(k)}"
        d[name] = ((d.rel_week == k) & (d.treat == 1)).astype(int)
        terms.append((k, name))
    formula = "y ~ " + " + ".join(n for _, n in terms) + " + C(store_id) + C(week)"
    fit = smf.ols(formula, data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d.store_id.astype("category").cat.codes})
    ci = fit.conf_int()
    rows = [{"rel_week": k, "coef": fit.params[n], "ci_low": ci.loc[n, 0], "ci_high": ci.loc[n, 1],
             "p_value": fit.pvalues[n]} for k, n in terms]
    rows.append({"rel_week": -1, "coef": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": np.nan})
    out = pd.DataFrame(rows).sort_values("rel_week").reset_index(drop=True)
    # совместный тест: все коэффициенты до старта равны нулю
    leads = [n for k, n in terms if k < -1]
    wald = fit.wald_test(" , ".join(f"{n} = 0" for n in leads), scalar=True)
    out["pretrend_joint_p"] = float(wald.pvalue)
    if log:
        for c in ("coef", "ci_low", "ci_high"):
            out[c] = np.expm1(out[c])
    return out


def naive_before_after(panel: pd.DataFrame, outcome: str) -> float:
    """Наивная оценка "до/после" по магазинам акции: рост в период акции к прошлым неделям."""
    t = panel[panel.treat == 1]
    return t.loc[t.period == "акция", outcome].mean() / t.loc[t.period == "до акции", outcome].mean() - 1
