import json
from pathlib import Path

import pandas as pd
import streamlit as st


# Keep the dashboard separate from the existing analyzer.
REPORT_PATH = Path(__file__).with_name("report.json")

st.set_page_config(
    page_title="Bank Statement Analyzer",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 Bank Statement Analyzer")
st.caption("Financial overview, transaction insights, and statement checks")


def format_money(value):
    """Format a number as Indian rupees."""
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


# Read the report created by analyzer.py.
if not REPORT_PATH.exists():
    st.error("report.json was not found in the project folder.")
    st.info(
        "Run your analyzer first: "
        "python analyzer.py statement_A.csv -o report.json"
    )
    st.stop()

try:
    with REPORT_PATH.open("r", encoding="utf-8") as file:
        report = json.load(file)
except (json.JSONDecodeError, OSError) as error:
    st.error(f"Could not read report.json: {error}")
    st.stop()


summary = report.get("summary", {})
monthly = report.get("monthly_trends", {})
categories = report.get("category_breakdown", [])

# Optional statement period.
period = summary.get("statement_period", {})
if period:
    st.caption(
        f"Statement period: {period.get('start_date', 'N/A')} "
        f"to {period.get('end_date', 'N/A')}"
    )

# Top-level financial summary.
st.subheader("Financial Summary")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Total Income", format_money(summary.get("total_income", 0)))
c2.metric("Total Expenses", format_money(summary.get("total_expenses", 0)))
c3.metric("Net Cash Flow", format_money(summary.get("net_cash_flow", 0)))
c4.metric("Transactions", summary.get("total_transactions", 0))

s1, s2, s3 = st.columns(3)
s1.metric(
    "Savings Rate",
    f"{summary.get('savings_rate_pct', 0):.2f}%",
)
s2.metric(
    "Average Daily Spend",
    format_money(summary.get("average_daily_spend", 0)),
)
s3.metric(
    "Ending Balance",
    format_money(summary.get("ending_balance", 0)),
)

st.divider()

# Monthly income and expense charts.
st.subheader("Monthly Trends")

if monthly:
    monthly_rows = []

    for month, values in sorted(monthly.items()):
        monthly_rows.append({
            "Month": month,
            "Income": values.get("income", 0),
            "Expenses": values.get("expenses", 0),
            "Net Savings": values.get("net_savings", 0),
        })

    monthly_df = pd.DataFrame(monthly_rows).set_index("Month")

    left, right = st.columns(2)

    with left:
        st.markdown("**Income vs. Expenses**")
        st.bar_chart(monthly_df[["Income", "Expenses"]])

    with right:
        st.markdown("**Monthly Net Savings**")
        st.line_chart(monthly_df[["Net Savings"]])

    with st.expander("View monthly figures"):
        st.dataframe(
            monthly_df.style.format(format_money),
            use_container_width=True,
        )
else:
    st.info("No monthly trend data was found in the report.")

st.divider()

# Expense category breakdown.
st.subheader("Expense Categories")

if categories:
    category_df = pd.DataFrame(categories)

    if "category" in category_df.columns and "total_spent" in category_df.columns:
        category_chart = category_df.set_index("category")[["total_spent"]]
        st.bar_chart(category_chart)

    display_columns = [
        column for column in [
            "category",
            "total_spent",
            "percentage_of_expenses",
            "transaction_count",
            "average_transaction",
        ]
        if column in category_df.columns
    ]

    st.dataframe(
        category_df[display_columns],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No expense category data was found.")

st.divider()

# Largest expenses.
st.subheader("Top Expenses")

top_expenses = report.get("top_expenses", [])

if top_expenses:
    expenses_df = pd.DataFrame(top_expenses)

    if "amount" in expenses_df.columns:
        expenses_df["amount"] = expenses_df["amount"].map(format_money)

    st.dataframe(
        expenses_df,
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No top expense data was found.")

st.divider()

# Required checks from the analyzer.
st.subheader("Statement Checks")

bounces = report.get("bounces", [])
round_trips = report.get("round_trips", [])
balance_breaks = report.get("balance_breaks", [])
invalid_rows = report.get("invalid_rows", [])

a, b, c, d = st.columns(4)
a.metric("Bounced Cheques", len(bounces))
b.metric("Possible Round Trips", len(round_trips))
c.metric("Balance Discrepancies", len(balance_breaks))
d.metric("Invalid Rows", len(invalid_rows))

if bounces or round_trips or balance_breaks or invalid_rows:
    st.warning(
        "Some transactions or balances require review. "
        "These flags do not automatically prove fraud or wrongdoing."
    )
else:
    st.success("No issues were flagged by these checks.")

with st.expander("View bounced cheque details"):
    if bounces:
        st.dataframe(pd.DataFrame(bounces), hide_index=True, use_container_width=True)
    else:
        st.write("No bounced cheques were flagged.")

with st.expander("View possible round trips"):
    if round_trips:
        st.dataframe(pd.DataFrame(round_trips), hide_index=True, use_container_width=True)
    else:
        st.write("No possible round trips were flagged.")

with st.expander("View balance discrepancies"):
    if balance_breaks:
        st.dataframe(pd.DataFrame(balance_breaks), hide_index=True, use_container_width=True)
    else:
        st.write("No balance discrepancies were flagged.")

with st.expander("View invalid rows"):
    if invalid_rows:
        st.dataframe(pd.DataFrame(invalid_rows), hide_index=True, use_container_width=True)
    else:
        st.write("No invalid rows were found.")

st.caption("Data source: report.json generated by your existing analyzer.py")
