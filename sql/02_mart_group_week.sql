-- Витрина магазин x неделя x товарная группа акции.
-- Группы для каждой кампании с товарной механикой:
--   "<кампания> участники"       : SKU из списка акции;
--   "<кампания> не участники"    : остальные SKU той же категории (каннибализация);
--   "Прочие категории"           : категории, не задействованные ни в одной акции (эффект на корзину);
--   "Подарок"                    : подарочные строки акции P3.
-- Группа строится по списку SKU кампании, а не по флагу promo_id:
-- так в окно попадают и недели до акции, и магазины без акции.
CREATE OR REPLACE TABLE mart_group_week AS
WITH promo_cat AS (
    SELECT DISTINCT campaign, category
    FROM promo_calendar
    WHERE mechanic <> 'gift'
),
labeled AS (
    SELECT
        c.store_id,
        date_diff('week', DATE '2026-01-05', CAST(date_trunc('week', c.datetime) AS DATE)) AS week,
        CASE
            WHEN c.category = 'Подарок'   THEN 'Подарок'
            WHEN ps.campaign IS NOT NULL  THEN ps.campaign || ' участники'
            WHEN pc.campaign IS NOT NULL  THEN pc.campaign || ' не участники'
            ELSE 'Прочие категории'
        END AS promo_group,
        c.qty,
        c.qty * c.price - c.discount          AS revenue,
        c.qty * c.price - c.discount - c.cost AS margin,
        c.discount
    FROM checks c
    LEFT JOIN promo_skus ps ON ps.sku_id = c.sku_id
    LEFT JOIN promo_cat  pc ON pc.category = c.category
)
SELECT
    store_id,
    week,
    promo_group,
    sum(qty)      AS units,
    sum(revenue)  AS revenue,
    sum(margin)   AS margin,
    sum(discount) AS discount,
    count(*)      AS lines
FROM labeled
GROUP BY store_id, week, promo_group
ORDER BY store_id, week, promo_group;
