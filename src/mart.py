"""Сборка аналитических витрин из чеков с помощью DuckDB."""
from __future__ import annotations

import duckdb
import pandas as pd

from src import config


def connect() -> duckdb.DuckDBPyConnection:
    """Подключение с представлениями над сырыми данными и справочниками."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW checks AS SELECT * FROM read_parquet('{config.DATA_RAW / 'checks.parquet'}')")
    for name in ("promo_calendar", "promo_stores", "promo_skus", "sku", "stores"):
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{config.DATA_REF / (name + '.csv')}')")
    return con


def build_marts() -> dict[str, pd.DataFrame]:
    """Выполняет SQL-скрипты, проверяет витрины и сохраняет их в data/mart."""
    con = connect()
    for script in ("01_mart_store_week.sql", "02_mart_group_week.sql", "03_mart_promo_spend.sql"):
        con.execute((config.SQL_DIR / script).read_text(encoding="utf-8"))
    checks = con.execute((config.SQL_DIR / "04_checks.sql").read_text(encoding="utf-8")).df()
    failed = checks[checks.failed]
    if len(failed):
        raise ValueError(f"Не пройдены проверки витрин: {failed.check_name.tolist()}")

    config.DATA_MART.mkdir(parents=True, exist_ok=True)
    marts = {}
    for name in ("mart_store_week", "mart_group_week", "mart_promo_spend"):
        df = con.execute(f"SELECT * FROM {name}").df()
        df.round(2).to_csv(config.DATA_MART / f"{name}.csv", index=False)
        marts[name] = df
    marts["quality_checks"] = checks
    return marts


def load_marts() -> dict[str, pd.DataFrame]:
    """Читает готовые витрины и справочники."""
    out = {name: pd.read_csv(config.DATA_MART / f"{name}.csv")
           for name in ("mart_store_week", "mart_group_week", "mart_promo_spend")}
    for name in ("promo_calendar", "promo_stores", "promo_skus"):
        out[name] = pd.read_csv(config.DATA_REF / f"{name}.csv")
    return out


if __name__ == "__main__":
    m = build_marts()
    print(m["quality_checks"].to_string(index=False))
