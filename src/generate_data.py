"""Генерация синтетических чеков в формате построчной выгрузки из 1С.

Каждая строка: одна позиция чека (receipt_id, datetime, store_id, sku_id,
category, qty, price, discount, cost, promo_id).

В данные заложены механики, которые встречаются в реальных акциях:
- рост продаж участников за счёт новых покупок;
- переключение покупателей с соседних товаров категории (каннибализация);
- субсидирование тех, кто купил бы и без акции (скидка уходит всем);
- рост среднего чека и трафика у акции "подарок к чеку".
Истинные параметры эффектов модель DiD не видит: она оценивает их по данным.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config

# Категории: (название, число SKU, диапазон цен, доля маржи в цене,
# амплитуда сезонного роста к лету, базовая доля строк чека)
CATEGORIES = [
    ("Газированные напитки", 60, (60, 160), 0.40, 0.60, 0.18),
    ("Соки и нектары", 45, (90, 190), 0.50, 0.30, 0.12),
    ("Вода", 35, (35, 90), 0.45, 0.60, 0.12),
    ("Энергетики", 30, (80, 150), 0.40, 0.50, 0.07),
    ("Холодный чай", 25, (70, 130), 0.42, 0.60, 0.07),
    ("Снеки", 45, (60, 180), 0.38, 0.05, 0.18),
    ("Шоколад и конфеты", 40, (50, 250), 0.35, -0.05, 0.16),
    ("Молочные продукты", 20, (60, 140), 0.25, 0.00, 0.10),
]

# Кампании: код, название, механика, категория, волны (номер, первая неделя)
CAMPAIGNS = [
    ("P3", "Подарок к чеку от 800 руб", "gift", None, [(1, 4)]),
    ("P1", "1+1=3 на газированные напитки", "3for2", "Газированные напитки", [(1, 11), (2, 23)]),
    ("P2", "-20% на соки и нектары", "pct20", "Соки и нектары", [(1, 14), (2, 23)]),
    ("P4", "Второй энергетик за полцены", "second50", "Энергетики", [(1, 17), (2, 23)]),
]

N_PARTICIPANTS = {"P1": 10, "P4": 8}   # число SKU-участников (P2: вся категория)
N_TREATED = 8                           # магазинов в каждой волне

# Истинные параметры поведения покупателей
SWITCH_PROB = {"P1": 0.35, "P4": 0.40}          # переход с соседних SKU категории
INCREMENTAL_PROB = {"P1": 0.05, "P2": 0.25, "P4": 0.03}  # доп. покупка в чеке
DEAL_QTY_PROB = {"P1": 0.65, "P4": 0.60}        # доля строк, купленных "по механике"
GIFT_THRESHOLD = 800
GIFT_PRICE, GIFT_COST = 89, 45
GIFT_TRAFFIC_UPLIFT = 0.06
GIFT_UPGRADE_PROB = 0.55
GIFT_NEAR_FROM = 600

DOW_FACTOR = np.array([0.90, 0.90, 0.95, 1.00, 1.15, 1.20, 1.00])
LINES_MU = 1.8


def _round_price(x: np.ndarray) -> np.ndarray:
    """Цена полки вида 89, 119, 149."""
    return np.maximum(np.round(x / 10) * 10 - 1, 19)


def build_reference(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Справочники: товары, магазины, календарь акций, участники."""
    rows = []
    sku_no = 1
    for cat, n, (lo, hi), margin, _, _ in CATEGORIES:
        prices = _round_price(rng.uniform(lo, hi, n))
        pop = rng.lognormal(0, 0.8, n)
        for p, w in zip(prices, pop):
            unit_cost = round(p * (1 - margin) * rng.uniform(0.92, 1.08), 2)
            rows.append((f"SKU{sku_no:04d}", cat, float(p), unit_cost, float(w)))
            sku_no += 1
    sku = pd.DataFrame(rows, columns=["sku_id", "category", "price", "unit_cost", "popularity"])

    stores = pd.DataFrame({
        "store_id": [f"S{i:02d}" for i in range(1, config.N_STORES + 1)],
        "base_receipts_per_day": rng.uniform(70, 140, config.N_STORES).round(1),
    })

    start = pd.Timestamp(config.START_DATE)
    cal, promo_stores, promo_skus = [], [], []
    for code, name, mech, cat, waves in CAMPAIGNS:
        if mech in ("3for2", "second50"):
            cat_skus = sku[sku.category == cat].sort_values("popularity", ascending=False)
            # участники: популярные товары из верхней половины категории
            top = cat_skus.head(len(cat_skus) // 2)
            parts = rng.choice(top.sku_id.values, N_PARTICIPANTS[code], replace=False)
        elif mech == "pct20":
            parts = sku.loc[sku.category == cat, "sku_id"].values
        else:
            parts = np.array([], dtype=object)
        for s in parts:
            promo_skus.append((code, s))
        for wave, w0 in waves:
            pid = f"{code}-{wave}"
            treated = rng.choice(stores.store_id.values, N_TREATED, replace=False)
            for s in sorted(treated):
                promo_stores.append((pid, s))
            d0 = start + pd.Timedelta(weeks=w0)
            d1 = d0 + pd.Timedelta(days=7 * config.PROMO_WEEKS - 1)
            cal.append((pid, code, name, mech, cat or "Весь чек", wave, w0,
                        w0 + config.PROMO_WEEKS - 1, d0.date(), d1.date()))
    calendar = pd.DataFrame(cal, columns=[
        "promo_id", "campaign", "name", "mechanic", "category", "wave",
        "start_week", "end_week", "start_date", "end_date"])
    return {
        "sku": sku,
        "stores": stores,
        "promo_calendar": calendar,
        "promo_stores": pd.DataFrame(promo_stores, columns=["promo_id", "store_id"]),
        "promo_skus": pd.DataFrame(promo_skus, columns=["campaign", "sku_id"]),
    }


def generate_checks(ref: dict[str, pd.DataFrame], rng: np.random.Generator) -> pd.DataFrame:
    """Построчная генерация чеков по магазинам и дням."""
    sku = ref["sku"]
    cat_names = [c[0] for c in CATEGORIES]
    cat_idx = {c: i for i, c in enumerate(cat_names)}
    sku_cat = sku.category.map(cat_idx).values
    price = sku.price.values
    unit_cost = sku.unit_cost.values
    base_share = np.array([c[5] for c in CATEGORIES])
    amp = np.array([c[4] for c in CATEGORIES])

    # условные вероятности SKU внутри категории
    cat_members, cat_cum = [], []
    for i in range(len(cat_names)):
        m = np.where(sku_cat == i)[0]
        w = sku.popularity.values[m]
        cat_members.append(m)
        cat_cum.append(np.cumsum(w / w.sum()))

    def sample_sku(cats: np.ndarray) -> np.ndarray:
        out = np.empty(len(cats), dtype=np.int64)
        for i in range(len(cat_names)):
            mask = cats == i
            k = mask.sum()
            if k:
                pos = np.searchsorted(cat_cum[i], rng.random(k))
                out[mask] = cat_members[i][np.minimum(pos, len(cat_members[i]) - 1)]
        return out

    sku_index = {s: i for i, s in enumerate(sku.sku_id)}
    parts = {c: np.array([sku_index[s] for s in g.sku_id])
             for c, g in ref["promo_skus"].groupby("campaign")}
    parts_cum = {c: np.cumsum(sku.popularity.values[p] / sku.popularity.values[p].sum())
                 for c, p in parts.items()}

    def sample_part(code: str, k: int) -> np.ndarray:
        pos = np.searchsorted(parts_cum[code], rng.random(k))
        return parts[code][np.minimum(pos, len(parts[code]) - 1)]

    is_part = {c: np.isin(np.arange(len(sku)), p) for c, p in parts.items()}

    cal = ref["promo_calendar"]
    active = {}  # (store, week) -> list of (campaign, promo_id)
    for _, r in cal.merge(ref["promo_stores"], on="promo_id").iterrows():
        for w in range(r.start_week, r.end_week + 1):
            active.setdefault((r.store_id, w), []).append((r.campaign, r.promo_id))

    start = pd.Timestamp(config.START_DATE)
    n_days = config.N_WEEKS * 7
    # общие для всех магазинов недельные шоки категорий (погода и т.п.)
    cat_week_shock = rng.lognormal(0, 0.05, (config.N_WEEKS, len(cat_names)))

    chunks = []
    receipt_counter = 0
    for _, st in ref["stores"].iterrows():
        store_week_shock = rng.lognormal(0, 0.04, config.N_WEEKS)
        store_cat_shock = rng.lognormal(0, 0.05, (config.N_WEEKS, len(cat_names)))
        for d in range(n_days):
            week = d // 7
            day = start + pd.Timedelta(days=d)
            ramp = (d / (n_days - 1)) ** 1.2
            promos = dict(active.get((st.store_id, week), []))

            lam = (st.base_receipts_per_day * DOW_FACTOR[day.dayofweek]
                   * (1 + 0.15 * ramp) * store_week_shock[week])
            if "P3" in promos:
                lam *= 1 + GIFT_TRAFFIC_UPLIFT
            n_rec = rng.poisson(lam)
            if n_rec == 0:
                continue

            cat_w = (base_share * (1 + amp * ramp)
                     * cat_week_shock[week] * store_cat_shock[week])
            mu = LINES_MU * cat_w.sum() / base_share.sum()
            n_lines = 1 + rng.poisson(mu, n_rec)
            rec = np.repeat(np.arange(n_rec), n_lines)
            cats = rng.choice(len(cat_names), len(rec), p=cat_w / cat_w.sum())
            skus = sample_sku(cats)
            qty = 1 + rng.poisson(0.25, len(rec))

            # P1 и P4: переключение с соседних товаров и доп. покупки участников
            for code in ("P1", "P4"):
                if code not in promos:
                    continue
                cat_i = cat_idx[CAMPAIGNS[[c[0] for c in CAMPAIGNS].index(code)][3]]
                neigh = (cats == cat_i) & ~is_part[code][skus]
                sw = neigh & (rng.random(len(rec)) < SWITCH_PROB[code])
                skus[sw] = sample_part(code, sw.sum())
                add = np.where(rng.random(n_rec) < INCREMENTAL_PROB[code])[0]
                rec = np.concatenate([rec, add])
                cats = np.concatenate([cats, np.full(len(add), cat_i)])
                skus = np.concatenate([skus, sample_part(code, len(add))])
                qty = np.concatenate([qty, 1 + rng.poisson(0.25, len(add))])
                deal = is_part[code][skus] & (rng.random(len(rec)) < DEAL_QTY_PROB[code])
                qty[deal] = 3 if code == "P1" else 2

            # P2: новые покупки соков
            if "P2" in promos:
                cat_i = cat_idx["Соки и нектары"]
                add = np.where(rng.random(n_rec) < INCREMENTAL_PROB["P2"])[0]
                rec = np.concatenate([rec, add])
                cats = np.concatenate([cats, np.full(len(add), cat_i)])
                skus = np.concatenate([skus, sample_sku(np.full(len(add), cat_i))])
                qty = np.concatenate([qty, 1 + rng.poisson(0.4, len(add))])

            line_price = price[skus]
            discount = np.zeros(len(rec))
            promo_id = np.full(len(rec), None, dtype=object)
            if "P1" in promos:
                m = is_part["P1"][skus] & (qty >= 3)
                discount[m] = (qty[m] // 3) * line_price[m]
                promo_id[m] = promos["P1"]
            if "P4" in promos:
                m = is_part["P4"][skus] & (qty >= 2)
                discount[m] = (qty[m] // 2) * 0.5 * line_price[m]
                promo_id[m] = promos["P4"]
            if "P2" in promos:
                m = cats == cat_idx["Соки и нектары"]
                discount[m] = 0.2 * line_price[m] * qty[m]
                promo_id[m] = promos["P2"]

            # P3: докупка до порога и подарок
            gift_rec = np.array([], dtype=np.int64)
            if "P3" in promos:
                for _ in range(3):
                    total = np.bincount(rec, weights=line_price * qty - discount, minlength=n_rec)
                    near = np.where((total >= GIFT_NEAR_FROM) & (total < GIFT_THRESHOLD))[0]
                    near = near[rng.random(len(near)) < GIFT_UPGRADE_PROB]
                    if not len(near):
                        break
                    add_cats = rng.choice(len(cat_names), len(near), p=base_share / base_share.sum())
                    add_skus = sample_sku(add_cats)
                    rec = np.concatenate([rec, near])
                    cats = np.concatenate([cats, add_cats])
                    skus = np.concatenate([skus, add_skus])
                    qty = np.concatenate([qty, np.ones(len(near), dtype=np.int64)])
                    line_price = np.concatenate([line_price, price[add_skus]])
                    discount = np.concatenate([discount, np.zeros(len(near))])
                    promo_id = np.concatenate([promo_id, np.full(len(near), None, dtype=object)])
                total = np.bincount(rec, weights=line_price * qty - discount, minlength=n_rec)
                gift_rec = np.where(total >= GIFT_THRESHOLD)[0]

            minutes = rng.integers(8 * 60, 23 * 60, n_rec)
            ts = day + pd.to_timedelta(minutes, unit="m")
            df = pd.DataFrame({
                "receipt_id": receipt_counter + rec,
                "datetime": ts[rec],
                "store_id": st.store_id,
                "sku_id": sku.sku_id.values[skus],
                "category": np.array(cat_names, dtype=object)[cats],
                "qty": qty,
                "price": line_price,
                "discount": discount.round(2),
                "cost": (unit_cost[skus] * qty).round(2),
                "promo_id": promo_id,
            })
            if len(gift_rec):
                df = pd.concat([df, pd.DataFrame({
                    "receipt_id": receipt_counter + gift_rec,
                    "datetime": ts[gift_rec],
                    "store_id": st.store_id,
                    "sku_id": "GIFT01",
                    "category": "Подарок",
                    "qty": 1,
                    "price": float(GIFT_PRICE),
                    "discount": float(GIFT_PRICE),
                    "cost": float(GIFT_COST),
                    "promo_id": promos["P3"],
                })], ignore_index=True)
            chunks.append(df)
            receipt_counter += n_rec

    checks = pd.concat(chunks, ignore_index=True)
    checks = checks.sort_values(["datetime", "receipt_id"], kind="stable").reset_index(drop=True)
    checks["qty"] = checks.qty.astype("int32")
    return checks


def main() -> None:
    rng = np.random.default_rng(config.SEED)
    ref = build_reference(rng)
    for d in (config.DATA_RAW, config.DATA_REF, config.ROOT / "data" / "sample"):
        d.mkdir(parents=True, exist_ok=True)
    for name, df in ref.items():
        df.to_csv(config.DATA_REF / f"{name}.csv", index=False)
    checks = generate_checks(ref, rng)
    checks.to_parquet(config.DATA_RAW / "checks.parquet", index=False, compression="zstd")
    checks.head(500).to_csv(config.ROOT / "data" / "sample" / "checks_sample.csv", index=False)
    print(f"Строк чеков: {len(checks):,}, чеков: {checks.receipt_id.nunique():,}")


if __name__ == "__main__":
    main()
