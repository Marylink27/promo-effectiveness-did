"""Графики для отчёта. Заголовок каждого графика формулирует вывод."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from src import config
from src.did import build_panel

C = config
SHORT = {"P3-1": "Подарок к чеку", "P1-1": "1+1=3 газировка",
         "P2-1": "-20% соки", "P4-1": "2-й энергетик -50%",
         "P1-2": "1+1=3 газировка", "P2-2": "-20% соки", "P4-2": "2-й энергетик -50%"}


def fmt_rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def _style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.edgecolor": C.MUTED, "axes.labelcolor": C.INK, "text.color": C.INK,
        "xtick.color": C.INK, "ytick.color": C.INK,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": C.GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "axes.titleweight": "bold", "axes.titlesize": 11,
        "figure.dpi": 150, "savefig.dpi": 150, "savefig.bbox": "tight",
    })


def _save(fig, name: str):
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    path = C.FIGURES / name
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _main_outcome(pid: str) -> tuple[str, str]:
    return ("store_revenue", "выручка магазина") if pid.startswith("P3") else ("part_units", "продажи участников, шт")


def plot_trends(marts: dict, promo_ids: list[str]):
    """Индекс основного показателя: магазины акции против контрольных."""
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, pid in zip(axes.flat, promo_ids):
        outcome, label = _main_outcome(pid)
        p = build_panel(marts, pid)
        g = p.groupby(["week", "treat"])[outcome].mean().unstack()
        base = p[p.period == "до акции"].groupby("treat")[outcome].mean()
        idx = g / base * 100
        rel = idx.index - p.loc[p.rel_week == 0, "week"].iloc[0]
        ax.axvspan(-0.5, C.PROMO_WEEKS - 0.5, color=C.GRID, alpha=0.6, lw=0)
        ax.plot(rel, idx[0], color=C.MUTED, lw=2, marker="o", ms=4, label="контрольные магазины")
        ax.plot(rel, idx[1], color=C.ACCENT, lw=2.4, marker="o", ms=4, label="магазины акции")
        ax.set_title(SHORT[pid])
        ax.set_xlabel("неделя относительно старта")
        ax.set_ylabel(f"{label}, до акции = 100")
        ax.text(1, ax.get_ylim()[1], "акция", ha="center", va="top", color=C.MUTED, fontsize=9)
    axes.flat[0].legend(frameon=False, loc="upper left")
    fig.suptitle("До старта группы магазинов движутся вместе, расходятся только в недели акции",
                 fontweight="bold", fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    return _save(fig, "01_trends_treated_vs_control.png")


def plot_event_study(es: pd.DataFrame, promo_ids: list[str]):
    """Эффект по неделям с 95% доверительным интервалом."""
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, pid in zip(axes.flat, promo_ids):
        d = es[es.promo_id == pid]
        ax.axvspan(-0.5, C.PROMO_WEEKS - 0.5, color=C.GRID, alpha=0.6, lw=0)
        ax.axhline(0, color=C.INK, lw=1)
        colors = [C.ACCENT if 0 <= k < C.PROMO_WEEKS else C.MUTED for k in d.rel_week]
        ax.errorbar(d.rel_week, d.coef, yerr=[d.coef - d.ci_low, d.ci_high - d.coef],
                    fmt="none", ecolor=C.MUTED, elinewidth=1.2, capsize=3)
        ax.scatter(d.rel_week, d.coef, color=colors, zorder=3, s=30)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_pct(v, 0)))
        p_pre = d.pretrend_joint_p.iloc[0]
        ax.set_title(f"{SHORT[pid]}: тест трендов до акции p = {p_pre:.2f}".replace(".", ","))
        ax.set_xlabel("неделя относительно старта (опорная: -1)")
        ax.set_ylabel(f"эффект на {_main_outcome(pid)[1]}")
    fig.suptitle("Проверка параллельных трендов: до старта эффект около нуля, в недели акции резкий скачок",
                 fontweight="bold", fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    return _save(fig, "02_event_study.png")


def plot_margin_decomposition(effects: pd.DataFrame, n_stores: int):
    """Куда уходит маржа в товарных акциях: участники, неучастники, категория."""
    _style()
    k = n_stores * C.PROMO_WEEKS
    pids = ["P1-1", "P2-1", "P4-1"]
    comps = [("part_margin", "маржа участников"), ("nonpart_margin", "маржа неучастников категории"),
             ("category_margin", "итог по категории")]
    fig, ax = plt.subplots(figsize=(11, 5))
    width = 0.26
    x = np.arange(len(pids))
    for i, (key, label) in enumerate(comps):
        vals = []
        for pid in pids:
            e = effects[effects.promo_id == pid].set_index("outcome")
            if key == "nonpart_margin":
                v = (e.loc["category_margin", "coef"] - e.loc["part_margin", "coef"]) * k
            else:
                v = e.loc[key, "coef"] * k
            vals.append(v)
        color = [C.ACCENT, C.WARM, C.INK][i]
        bars = ax.bar(x + (i - 1) * width, vals, width, color=color, label=label)
        for b, v, pid in zip(bars, vals, pids):
            text = fmt_rub(v)
            if key == "nonpart_margin" and abs(v) < 1:
                text = "в акции\nвся категория"
            ax.text(b.get_x() + b.get_width() / 2, v + (4000 if v >= 0 else -4000),
                    text, ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5)
    ax.axhline(0, color=C.INK, lw=1)
    ax.set_xticks(x, [SHORT[p] for p in pids])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_rub(v)))
    ax.set_ylabel("изменение валовой маржи за волну, руб")
    lo = min(ax.get_ylim()[0], -170_000)
    ax.set_ylim(lo, max(ax.get_ylim()[1], 100_000))
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("В «1+1=3» и «втором энергетике» рост маржи участников съедает каннибализация соседних товаров",
                 loc="left")
    fig.tight_layout()
    return _save(fig, "03_margin_decomposition.png")


def plot_pnl(pnl: pd.DataFrame):
    """Инкрементальный P&L волны с подписью статуса."""
    _style()
    d = pnl.sort_values("incremental_pnl")
    fig, ax = plt.subplots(figsize=(11, 4.6))
    colors = [C.WARM if s == "убыточная" else C.ACCENT if s == "прибыльная" else C.MUTED for s in d.status]
    y = np.arange(len(d))
    ax.barh(y, d.incremental_pnl, color=colors, height=0.55)
    k_err = [d.incr_margin - d.incr_margin_ci_low, d.incr_margin_ci_high - d.incr_margin]
    ax.errorbar(d.incremental_pnl, y, xerr=k_err, fmt="none", ecolor=C.INK, elinewidth=1, capsize=3)
    for yi, (v, s, hi, lo) in enumerate(zip(d.incremental_pnl, d.status,
                                           d.incr_margin_ci_high - d.incr_margin,
                                           d.incr_margin - d.incr_margin_ci_low)):
        xpos = v + hi + 8000 if v >= 0 else v - lo - 8000
        ax.text(xpos, yi, f"{fmt_rub(v)} руб, {s}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.5)
    ax.axvline(0, color=C.INK, lw=1)
    ax.set_yticks(y, [SHORT[p] for p in d.promo_id])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_rub(v)))
    ax.set_xlabel("инкрементальный результат волны после фиксированных затрат, руб (линии: 95% интервал)")
    lo_lim = min((d.incremental_pnl - k_err[0]).min(), 0) - 160_000
    hi_lim = max((d.incremental_pnl + k_err[1]).max(), 0) + 160_000
    ax.set_xlim(lo_lim, hi_lim)
    n_bad = int((d.status == "убыточная").sum())
    n_good = int((d.status == "прибыльная").sum())
    n_none = len(d) - n_bad - n_good
    ax.set_title(f"Из {len(d)} акций убыточных {n_bad}, прибыльных {n_good}, "
                 f"без доказанного эффекта {n_none}", loc="left")
    fig.tight_layout()
    return _save(fig, "04_incremental_pnl.png")


def plot_planning(plan: pd.DataFrame, wape_naive: float, wape_did: float):
    """Ошибка плана второй волны: наивный подход против DiD."""
    _style()
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = np.arange(len(plan))
    w = 0.36
    b1 = ax.bar(x - w / 2, plan.ape_naive, w, color=C.MUTED, label="план по оценке «до/после»")
    b2 = ax.bar(x + w / 2, plan.ape_did, w, color=C.ACCENT, label="план по оценке DiD")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.002, fmt_pct(b.get_height()),
                    ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, [SHORT[p] for p in plan.promo_id])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_pct(v, 0)))
    ax.set_ylabel("ошибка плана продаж участников")
    ax.set_ylim(0, max(plan.ape_naive.max(), plan.ape_did.max()) * 1.35)
    ax.legend(frameon=False, loc="upper center", ncol=2)
    ax.set_title(f"Вторая волна: ошибка плана {fmt_pct(wape_naive)} при наивной оценке и "
                 f"{fmt_pct(wape_did)} при оценке DiD (WAPE)", loc="left")
    fig.tight_layout()
    return _save(fig, "05_planning_error.png")
