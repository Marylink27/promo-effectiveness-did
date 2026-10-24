"""Сводные расчёты: эффекты по акциям, инкрементальный P&L, точность планирования."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src import config
from src.did import (BASKET_OUTCOMES, CATEGORY_OUTCOMES, build_panel, did_estimate,
                     event_study, naive_before_after)

warnings.filterwarnings("ignore", category=UserWarning)

ALPHA = 0.05
WAVE1 = ["P3-1", "P1-1", "P2-1", "P4-1"]
WAVE2 = ["P1-2", "P2-2", "P4-2"]
WAVE2_PRE_WEEKS = 3  # неделя 19 занята первой волной P4, поэтому берём 20-22


def _is_basket(marts: dict, promo_id: str) -> bool:
    return marts["promo_calendar"].set_index("promo_id").loc[promo_id, "mechanic"] == "gift"


def effects_table(marts: dict, promo_ids: list[str] = WAVE1) -> pd.DataFrame:
    """Все DiD-оценки по акциям первой волны."""
    rows = []
    for pid in promo_ids:
        panel = build_panel(marts, pid)
        outcomes = BASKET_OUTCOMES if _is_basket(marts, pid) else CATEGORY_OUTCOMES
        for key, label in outcomes.items():
            if key == "nonpart_revenue" and panel[key].sum() == 0:
                continue  # акция на всю категорию: неучастников нет
            r = did_estimate(panel, key)
            r.update({"promo_id": pid, "label": label})
            rows.append(r)
    return pd.DataFrame(rows)


def pnl_table(marts: dict, effects: pd.DataFrame) -> pd.DataFrame:
    """Инкрементальный P&L волны.

    Товарные акции: эффект на маржу всей категории (скидки, рост участников и
    каннибализация уже внутри) плюс эффект на прочие категории, если он
    статистически значим. Акция на чек: эффект на маржу магазина с подарками.
    Из результата вычитаются фиксированные затраты волны.
    """
    cal = marts["promo_calendar"].set_index("promo_id")
    spend = marts["mart_promo_spend"].set_index("promo_id")
    rows = []
    for pid in effects.promo_id.unique():
        e = effects[effects.promo_id == pid].set_index("outcome")
        n_stores = int(spend.loc[pid, "stores"])
        k = n_stores * config.PROMO_WEEKS
        if _is_basket(marts, pid):
            main = e.loc["store_margin"]
            halo, halo_used = 0.0, False
        else:
            main = e.loc["category_margin"]
            halo_row = e.loc["halo_margin"]
            halo_used = halo_row.p_value < ALPHA
            halo = halo_row.coef * k if halo_used else 0.0
        incr_margin = main.coef * k
        pnl = incr_margin + halo - config.FIXED_COST_PER_WAVE
        if main.p_value < ALPHA:
            status = "прибыльная" if pnl > 0 else "убыточная"
        else:
            status = "эффект не доказан"
        given = spend.loc[pid, "discount_spend"] + spend.loc[pid, "gift_cost"]
        rows.append({
            "promo_id": pid,
            "name": cal.loc[pid, "name"],
            "stores": n_stores,
            "weeks": config.PROMO_WEEKS,
            "incr_margin": incr_margin,
            "incr_margin_ci_low": main.ci_low * k,
            "incr_margin_ci_high": main.ci_high * k,
            "p_value": main.p_value,
            "halo_margin": halo,
            "halo_included": halo_used,
            "fixed_cost": config.FIXED_COST_PER_WAVE,
            "incremental_pnl": pnl,
            "discount_and_gifts": given,
            "pnl_per_100_rub_given": 100 * pnl / given if given else np.nan,
            "status": status,
        })
    return pd.DataFrame(rows)


def planning_accuracy(marts: dict) -> pd.DataFrame:
    """Точность плана продаж участников во второй волне.

    База (продажи без акции) у обоих подходов одна: продажи магазинов волны 2
    за 3 недели до старта, умноженные на динамику контрольных магазинов.
    Подходы отличаются только оценкой эффекта акции по первой волне:
    наивный "до/после" против DiD.
    """
    rows = []
    for pid2 in WAVE2:
        pid1 = pid2.replace("-2", "-1")
        p1 = build_panel(marts, pid1)
        naive = naive_before_after(p1, "part_units")
        did = did_estimate(p1, "part_units", log=True)["effect_pct"]

        p2 = build_panel(marts, pid2, pre_weeks=WAVE2_PRE_WEEKS, post_weeks=0)
        pre, promo = p2[p2.period == "до акции"], p2[p2.period == "акция"]
        ctrl_growth = (promo[promo.treat == 0].part_units.mean()
                       / pre[pre.treat == 0].part_units.mean())
        base = (pre[pre.treat == 1].groupby("store_id").part_units.mean().sum()
                * ctrl_growth * config.PROMO_WEEKS)
        actual = promo[promo.treat == 1].part_units.sum()
        rows.append({
            "promo_id": pid2,
            "uplift_naive": naive,
            "uplift_did": did,
            "baseline_units": base,
            "plan_naive": base * (1 + naive),
            "plan_did": base * (1 + did),
            "actual_units": actual,
        })
    df = pd.DataFrame(rows)
    df["ape_naive"] = (df.plan_naive - df.actual_units).abs() / df.actual_units
    df["ape_did"] = (df.plan_did - df.actual_units).abs() / df.actual_units
    df["bias_naive"] = df.plan_naive / df.actual_units - 1
    df["bias_did"] = df.plan_did / df.actual_units - 1
    return df


def wape(plan: pd.Series, actual: pd.Series) -> float:
    """Взвешенная ошибка плана по всем акциям."""
    return float((plan - actual).abs().sum() / actual.sum())


def event_studies(marts: dict, promo_ids: list[str] = WAVE1) -> pd.DataFrame:
    """Event study по главному показателю каждой акции."""
    out = []
    for pid in promo_ids:
        outcome = "store_revenue" if _is_basket(marts, pid) else "part_units"
        es = event_study(build_panel(marts, pid), outcome)
        es["promo_id"], es["outcome"] = pid, outcome
        out.append(es)
    return pd.concat(out, ignore_index=True)


def pretrend_test(es: pd.DataFrame) -> pd.DataFrame:
    """Проверка параллельных трендов: совместный тест недель до старта.

    p-value больше 0,05 означает, что до акции магазины двух групп
    менялись одинаково и контрольная группа подходит для сравнения.
    """
    pre = es[es.rel_week < -1]
    out = (pre.groupby("promo_id")
              .agg(max_abs_pre_effect=("coef", lambda s: s.abs().max()),
                   joint_p_value=("pretrend_joint_p", "first"))
              .reset_index())
    out["parallel_trends_ok"] = out.joint_p_value > ALPHA
    return out
