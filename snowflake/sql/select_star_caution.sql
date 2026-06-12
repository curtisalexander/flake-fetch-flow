-- The cautionary example: 100,000 raw rows.
-- Fine to write to a file or a DataFrame; a terrible thing to print into
-- an LLM's context (~millions of tokens, and the model gets WORSE, not
-- smarter, when you firehose it). See docs/index.html — "Right-sizing".
SELECT *
FROM demo_orders;
