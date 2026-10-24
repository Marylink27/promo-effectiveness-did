-- Витрина магазин x неделя: трафик, выручка, валовая маржа, средний чек.
-- Источник: построчная выгрузка чеков (view checks).
-- Выручка строки = qty * price - discount; маржа = выручка - себестоимость.
CREATE OR REPLACE TABLE mart_store_week AS
WITH lines AS (
    SELECT
        store_id,
        receipt_id,
        date_diff('week', DATE '2026-01-05', CAST(date_trunc('week', datetime) AS DATE)) AS week,
        qty,
        qty * price - discount AS revenue,
        qty * price - discount - cost AS margin,
        discount
    FROM checks
)
SELECT
    store_id,
    week,
    count(DISTINCT receipt_id)                          AS receipts,
    sum(revenue)                                        AS revenue,
    sum(margin)                                         AS margin,
    sum(discount)                                       AS discount,
    sum(qty)                                            AS units,
    sum(revenue) / count(DISTINCT receipt_id)           AS avg_check
FROM lines
GROUP BY store_id, week
ORDER BY store_id, week;
