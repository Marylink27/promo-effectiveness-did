"""Полный пересчёт проекта одной командой: python -m src.run_pipeline"""
from __future__ import annotations

import pandas as pd

from src import analysis, config, generate_data, mart, plots, report_excel


def main(regenerate: bool = True) -> dict:
    if regenerate or not (config.DATA_RAW / "checks.parquet").exists():
        print("1/5 Генерация чеков")
        generate_data.main()
    print("2/5 Витрины DuckDB и проверки качества")
    built = mart.build_marts()
    print(built["quality_checks"].to_string(index=False))
    marts = mart.load_marts()

    print("3/5 Оценка эффектов (DiD), P&L, точность плана")
    effects = analysis.effects_table(marts)
    pnl = analysis.pnl_table(marts, effects)
    plan = analysis.planning_accuracy(marts)
    wape_naive = analysis.wape(plan.plan_naive, plan.actual_units)
    wape_did = analysis.wape(plan.plan_did, plan.actual_units)
    es = analysis.event_studies(marts)
    pretrends = analysis.pretrend_test(es)

    config.REPORTS.mkdir(parents=True, exist_ok=True)
    effects.round(4).to_csv(config.REPORTS / "did_effects.csv", index=False)
    pnl.round(4).to_csv(config.REPORTS / "promo_pnl.csv", index=False)
    plan.round(4).to_csv(config.REPORTS / "planning_accuracy.csv", index=False)
    es.round(4).to_csv(config.REPORTS / "event_study.csv", index=False)
    pretrends.round(4).to_csv(config.REPORTS / "pretrend_tests.csv", index=False)

    print("4/5 Графики")
    order = analysis.WAVE1
    plots.plot_trends(marts, order)
    plots.plot_event_study(es, order)
    plots.plot_margin_decomposition(effects, int(pnl.stores.iloc[0]))
    plots.plot_pnl(pnl)
    plots.plot_planning(plan, wape_naive, wape_did)

    print("5/5 Excel-отчёт")
    sw = marts["mart_store_week"]
    start = pd.Timestamp(config.START_DATE)
    end = start + pd.Timedelta(days=7 * config.N_WEEKS - 1)
    info = {"period": f"{start:%d.%m.%Y}-{end:%d.%m.%Y}",
            "receipts": int(sw.receipts.sum()),
            "lines": int(marts["mart_group_week"]["lines"].sum())}
    report_excel.build_report(pnl, effects, plan, pretrends, wape_naive, wape_did, info)

    print("\nИтоги по акциям:")
    print(pnl[["promo_id", "name", "incremental_pnl", "p_value", "status"]].round(3).to_string(index=False))
    print(f"\nОшибка плана второй волны (WAPE): до/после {wape_naive:.1%}, DiD {wape_did:.1%}")
    return {"effects": effects, "pnl": pnl, "plan": plan, "event_study": es, "pretrends": pretrends}


if __name__ == "__main__":
    main()
