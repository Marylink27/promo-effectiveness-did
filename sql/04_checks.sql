-- Контроль качества витрин: каждая проверка возвращает 0 при успехе.
SELECT 'Выручка витрины магазинов совпадает с чеками' AS check_name,
       abs((SELECT sum(revenue) FROM mart_store_week)
           - (SELECT sum(qty * price - discount) FROM checks)) > 1 AS failed
UNION ALL
SELECT 'Выручка витрины групп совпадает с чеками',
       abs((SELECT sum(revenue) FROM mart_group_week)
           - (SELECT sum(qty * price - discount) FROM checks)) > 1
UNION ALL
SELECT 'Нет строк с нулевым или отрицательным количеством',
       (SELECT count(*) FROM checks WHERE qty <= 0) > 0
UNION ALL
SELECT 'Скидка не превышает сумму строки',
       (SELECT count(*) FROM checks WHERE discount > qty * price + 0.01) > 0
UNION ALL
SELECT 'В каждой паре магазин x неделя есть чеки',
       (SELECT count(*) FROM mart_store_week)
       <> (SELECT count(DISTINCT store_id) * count(DISTINCT week) FROM mart_store_week)
UNION ALL
SELECT 'Скидки акций есть только в магазинах и неделях акции',
       (SELECT count(*)
        FROM checks c
        LEFT JOIN promo_calendar pc ON pc.promo_id = c.promo_id
        LEFT JOIN promo_stores pst ON pst.promo_id = c.promo_id AND pst.store_id = c.store_id
        WHERE c.promo_id IS NOT NULL
          AND (pst.store_id IS NULL
               OR CAST(c.datetime AS DATE) NOT BETWEEN pc.start_date AND pc.end_date)) > 0;
