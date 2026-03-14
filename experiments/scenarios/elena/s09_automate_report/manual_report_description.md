# Monthly Revenue Report — What I Do Manually

## Steps (takes ~3 hours every 1st of the month)

1. Export orders from Metabase for the previous month → orders.csv
2. Export returns from warehouse system → returns.csv
3. Export customer tier data from CRM → tiers.csv

4. In Excel:
   - Remove duplicate order IDs (happens occasionally)
   - Filter out orders with status = 'pending' (not finalised)
   - Join returns onto orders by order_id, subtract refund_amount from amount
   - Join customer tiers onto the result by customer_id
   - Calculate net_revenue per order = amount - COALESCE(refund_amount, 0)

5. Build summary pivot:
   - Rows: customer tier (bronze, silver, gold, platinum, enterprise, null→"unassigned")
   - Columns: order_count, gross_revenue, total_refunds, net_revenue, avg_order_value
   - Sort by net_revenue DESC

6. Add month-over-month change columns by manually copying previous month's numbers

7. Paste summary into the shared Google Sheet "Monthly Revenue Report" (Finance tab)

8. Email a PDF version to: finance@company.com, ceo@company.com

## Pain points
- Step 6 is error-prone — I copy/paste wrong sometimes
- The whole thing breaks if the CSV column names change
- I always forget to filter pending orders until I notice the numbers look off
