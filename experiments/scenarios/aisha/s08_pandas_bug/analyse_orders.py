import pandas as pd

df = pd.read_csv("orders.csv")

# BUG: groupby on "order_id" instead of "customer_id"
# This gives one row per order (average of a single value = the value itself)
# then the overall .mean() averages those, producing a number close to the
# mean of all order_id integers, not mean order value per customer
avg_order_value = df.groupby("order_id")["amount"].sum().mean()

print(f"Average order value per customer: £{avg_order_value:.2f}")

# This would be the correct version:
# avg_order_value = df.groupby("customer_id")["amount"].sum().mean()
