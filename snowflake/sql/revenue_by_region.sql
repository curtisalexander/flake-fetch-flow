-- The "right-sized" query: Snowflake does the heavy lifting,
-- and only 4 small rows come back — perfect for an LLM to reason about.
SELECT
    region,
    COUNT(*)                            AS orders,
    ROUND(SUM(quantity * unit_price))   AS revenue
FROM demo_orders
GROUP BY region
ORDER BY revenue DESC;
