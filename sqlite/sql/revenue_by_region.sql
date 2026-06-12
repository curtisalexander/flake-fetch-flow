-- The "right-sized" query, SQLite dialect: the database does the heavy
-- lifting, and only 4 small rows come back — perfect for an LLM.
SELECT
    region,
    COUNT(*)                                        AS orders,
    CAST(ROUND(SUM(quantity * unit_price)) AS INT)  AS revenue
FROM demo_orders
GROUP BY region
ORDER BY revenue DESC;
