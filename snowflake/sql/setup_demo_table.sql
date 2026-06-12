-- One-time setup: a demo table with 100,000 synthetic orders.
-- Run this yourself in Snowsight (or via scripts/query_to_console.py).
-- 100k rows is deliberately "too big to dump into an LLM" — that's the lesson.

CREATE OR REPLACE TABLE demo_orders (
    order_id   INTEGER,
    order_ts   TIMESTAMP_NTZ,
    region     VARCHAR,
    product    VARCHAR,
    quantity   INTEGER,
    unit_price NUMBER(10, 2)
);

INSERT INTO demo_orders
SELECT
    SEQ4()                                                AS order_id,
    DATEADD('minute', -SEQ4(), CURRENT_TIMESTAMP())       AS order_ts,
    DECODE(MOD(SEQ4(), 4),
           0, 'North', 1, 'South', 2, 'East', 'West')     AS region,
    DECODE(MOD(SEQ4(), 5),
           0, 'Anvil', 1, 'Rocket Skates', 2, 'Tornado Seeds',
           3, 'Earthquake Pills', 'Giant Magnet')         AS product,
    UNIFORM(1, 10, RANDOM())                              AS quantity,
    UNIFORM(500, 50000, RANDOM()) / 100                   AS unit_price
FROM TABLE(GENERATOR(ROWCOUNT => 100000));
