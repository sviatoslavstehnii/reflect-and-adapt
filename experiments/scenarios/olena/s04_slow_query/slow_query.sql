-- Find customers who placed more than 3 orders in the last 90 days
-- and have a lifetime value above the median LTV
-- Currently runs ~40s on prod (orders table: 8M rows, customers: 420k rows)

SELECT
    c.id,
    c.email,
    c.segment,
    COUNT(o.id)          AS order_count_90d,
    SUM(o.amount)        AS revenue_90d,
    c.lifetime_value
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE
    o.created_at >= NOW() - INTERVAL '90 days'
    AND o.status = 'completed'
    AND c.lifetime_value > (
        -- Correlated scalar subquery recalculated for every row  <-- main problem
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lifetime_value)
        FROM customers
    )
GROUP BY c.id, c.email, c.segment, c.lifetime_value
HAVING COUNT(o.id) > 3
ORDER BY revenue_90d DESC;
