-- Сколько денег акция раздала покупателям: скидки и себестоимость подарков.
CREATE OR REPLACE TABLE mart_promo_spend AS
SELECT
    promo_id,
    count(DISTINCT receipt_id)                                        AS promo_receipts,
    sum(qty)                                                          AS promo_units,
    sum(CASE WHEN category = 'Подарок' THEN 0 ELSE discount END)      AS discount_spend,
    sum(CASE WHEN category = 'Подарок' THEN cost ELSE 0 END)          AS gift_cost,
    count(DISTINCT store_id)                                          AS stores
FROM checks
WHERE promo_id IS NOT NULL
GROUP BY promo_id
ORDER BY promo_id;
