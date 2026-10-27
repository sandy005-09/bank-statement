
#!/usr/bin/env python3
"""Bank Statement Analyzer - internship assignment."""

import argparse
import csv
import json
import os
import re
import sys
import calendar
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation


MIN_ROUND_TRIP = Decimal("100000.00")
MAX_ROUND_TRIP_HOURS = 48

CATEGORY_RULES = {
    "Rent & Facilities": [
        r"\brent\b", r"\bmortgage\b", r"\blease\b",
        r"\bproperty\b", r"\bhousing\b", r"\broyal estates\b",
    ],
    "Loan & EMI": [
        r"\bloan\b", r"\bemi\b", r"\becs dr\b", r"\binterest\b",
    ],
    "Payroll & Salary": [
        r"\bsalary\b", r"\bpayroll\b", r"\bwage\b",
        r"\bstipend\b", r"\bbatch payout\b",
    ],
    "Taxes & Compliance": [
        r"\bgst\b", r"\btax\b", r"\bchallan\b", r"\btds\b", r"\bgovt\b",
    ],
    "Utilities": [
        r"\belectricity\b", r"\belectric\b", r"\bgas utility\b",
        r"\bpower\b", r"\bwater\b", r"\binternet\b",
        r"\btelecom\b", r"\bisp\b", r"\bbroadband\b",
        r"\butility\b", r"\benergy\b",
    ],
    "Logistics & Transport": [
        r"\btransport\b", r"\blogistics\b", r"\bfuel\b",
        r"\bmetro fuel\b", r"\buber\b", r"\blyft\b",
        r"\bshell\b", r"\bchevron\b", r"\bgas station\b",
        r"\btransit\b", r"\bparking\b",
    ],
    "Packaging & Raw Materials": [
        r"\bpackaging\b", r"\bsupplies\b", r"\bwholesale\b",
    ],
    "Hardware & Electricals": [
        r"\belectrical\b", r"\bhardware\b", r"\belectronics\b",
    ],
    "Office & Printing": [
        r"\boffice mart\b", r"\bstationer\b", r"\bprinter\b",
        r"\bpaper\b",
    ],
    "Bank Charges & Fees": [
        r"\brtn chgs?\b", r"\bchq rtn\b", r"\bbank charge\b",
        r"\bpenalty\b", r"\bfee\b", r"\bservice charge\b",
    ],
    "Dining & Catering": [
        r"\bcaterer\b", r"\bstarbucks\b", r"\bcoffee\b",
        r"\bcafe\b", r"\bchipotle\b", r"\bmcdonald\b",
        r"\bbistro\b", r"\btrattoria\b", r"\brestaurant\b",
        r"\bdiner\b", r"\bpizza\b", r"\bgrill\b", r"\bfood\b",
    ],
    "Groceries": [
        r"\bwhole foods\b", r"\btrader joe\b", r"\bwalmart\b",
        r"\bmarket\b", r"\bgrocery\b", r"\bsupermarket\b",
        r"\bkroger\b", r"\bsafeway\b", r"\bcostco\b",
    ],
    "Entertainment": [
        r"\bnetflix\b", r"\bspotify\b", r"\bhulu\b",
        r"\bdisney\b", r"\bsteam\b", r"\bgames\b",
        r"\bcinema\b", r"\bmovies\b", r"\btheatre\b",
    ],
    "Healthcare": [
        r"\bpharmacy\b", r"\bprescription\b", r"\bdental\b",
        r"\bclinic\b", r"\bdoctor\b", r"\bhospital\b",
        r"\bhealth\b", r"\bmedical\b",
    ],
    "Revenue & Sales Inflow": [
        r"\bneft-cr\b", r"\bupi-cr\b", r"\bchq dep\b",
        r"\bdirect dep\b", r"\bfreelance\b", r"\bsales\b",
        r"\bclient\b", r"\breceipt\b",
    ],
    "Transfers": [
        r"\btransfer\b", r"\bwire\b", r"\bzelle\b",
        r"\bvenmo\b", r"\bpaypal\b", r"\bopening balance\b",
    ],
}


def money(value):
    """Convert an amount to exact two-decimal currency."""
    if value is None or str(value).strip() == "":
        return Decimal("0.00")

    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return Decimal("0.00")

    try:
        result = Decimal(text)
        if negative:
            result = -result
        return result.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary amount: {value}") from exc


def amount_text(value):
    """JSON-friendly currency string."""
    return str(money(value))


def parse_date(value):
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
        "%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y",
        "%b %d, %Y", "%B %d, %Y",
        "%d %b %Y", "%d %B %Y",
    ]
    value = (value or "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def normalize_counterparty(description):
    """Remove common bank transfer prefixes before matching names."""
    text = (description or "").strip().upper()
    text = re.sub(
        r"^\s*(?:NEFT|RTGS|IMPS|UPI)\s*[-/ ]\s*"
        r"(?:CR|DR|CREDIT|DEBIT)\s*[-/ ]?",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -/")


def extract_cheque_number(description):
    """Extract a cheque identifier from common narration formats."""
    text = (description or "").upper()

    patterns = [
        r"\b(?:CHQ|CHEQUE|CHECK)\s*"
        r"(?:RTN|RETURN|DEP|DEPOSIT|NO\.?|NUMBER|#)?"
        r"\s*[-:# ]*([A-Z0-9-]*\d[A-Z0-9-]*)",
        r"\b(?:RTN CHGS?|RETURN CHARGES?)\b.*?"
        r"\b(?:CHQ|CHEQUE|CHECK)\s*"
        r"(?:NO\.?|NUMBER|#)?\s*[-:# ]*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            identifier = match.group(1).strip("- ")
            if identifier.isdigit() or (
                any(c.isdigit() for c in identifier)
                and len(identifier) >= 4
            ):
                return identifier

    return None


class BankStatementAnalyzer:
    def __init__(self, category_rules=None):
        self.category_rules = category_rules or CATEGORY_RULES
        self.transactions = []
        self.starting_balance = None
        self.invalid_rows = []

    @staticmethod
    def _clean_amount(value):
        return float(money(value))

    @staticmethod
    def _parse_date(value):
        return parse_date(value)

    def auto_categorize(self, description, explicit_category=None,
                        is_income=False):
        if explicit_category and explicit_category.strip():
            category = explicit_category.strip()
            if category.lower() not in {
                "none", "null", "undefined", "misc", "uncategorized"
            }:
                return category

        for category, patterns in self.category_rules.items():
            for pattern in patterns:
                if re.search(pattern, description or "", re.IGNORECASE):
                    return category

        return "Revenue & Sales Inflow" if is_income else "Miscellaneous"

    def load_csv(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        self.transactions = []
        self.starting_balance = None
        self.invalid_rows = []

        with open(filepath, "r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError("CSV is empty or has no header.")

            fields = {}
            aliases = {
                "date": ["date", "txn_date", "transaction date",
                         "posting date"],
                "description": ["description", "narration", "details",
                                "memo", "payee", "particulars"],
                "category": ["category"],
                "debit": ["debit", "withdrawal", "outflow", "expense"],
                "credit": ["credit", "deposit", "inflow", "income"],
                "amount": ["amount"],
                "type": ["type", "transaction type", "cr/dr"],
                "balance": ["balance", "running balance"],
            }

            for original in reader.fieldnames:
                cleaned = original.strip().lower()
                for key, names in aliases.items():
                    if cleaned in names:
                        fields[key] = original
                        break

            if "date" not in fields or "description" not in fields:
                raise ValueError(
                    "CSV must contain Date and Description columns."
                )

            for line_number, row in enumerate(reader, start=2):
                raw_date = row.get(fields["date"]) or ""
                dt = parse_date(raw_date)

                if dt is None:
                    self.invalid_rows.append({
                        "line_number": line_number,
                        "reason": "Invalid or missing date",
                    })
                    continue

                description = (
                    row.get(fields["description"]) or ""
                ).strip()

                try:
                    if "debit" in fields or "credit" in fields:
                        debit = money(
                            row.get(fields["debit"], "")
                            if "debit" in fields else ""
                        )
                        credit = money(
                            row.get(fields["credit"], "")
                            if "credit" in fields else ""
                        )
                    elif "amount" in fields:
                        raw_amount = money(row.get(fields["amount"], ""))
                        txn_type = (
                            row.get(fields["type"], "").strip().lower()
                            if "type" in fields else ""
                        )

                        if txn_type in {
                            "debit", "dr", "expense", "withdrawal"
                        }:
                            debit, credit = abs(raw_amount), Decimal("0.00")
                        elif txn_type in {
                            "credit", "cr", "income", "deposit"
                        }:
                            debit, credit = Decimal("0.00"), abs(raw_amount)
                        elif raw_amount < 0:
                            debit, credit = abs(raw_amount), Decimal("0.00")
                        else:
                            debit, credit = Decimal("0.00"), raw_amount
                    else:
                        raise ValueError(
                            "CSV needs Debit/Credit or Amount columns."
                        )

                    raw_balance = (
                        row.get(fields["balance"], "")
                        if "balance" in fields else ""
                    )
                    balance = (
                        money(raw_balance)
                        if str(raw_balance).strip() else None
                    )

                except ValueError as exc:
                    self.invalid_rows.append({
                        "line_number": line_number,
                        "reason": str(exc),
                    })
                    continue

                # A zero-movement row with a balance is treated as
                # an opening-balance record, not an ordinary transaction.
                if debit == 0 and credit == 0:
                    if balance is not None and self.starting_balance is None:
                        self.starting_balance = balance
                    continue

                explicit_category = (
                    row.get(fields["category"], "")
                    if "category" in fields else None
                )
                is_income = credit > 0 and debit == 0

                self.transactions.append({
                    "id": len(self.transactions) + 1,
                    "line_number": line_number,
                    "date": dt.strftime("%Y-%m-%d"),
                    "datetime": dt,
                    "month": dt.strftime("%Y-%m"),
                    "description": description,
                    "category": self.auto_categorize(
                        description, explicit_category, is_income
                    ),
                    "type": "Credit" if is_income else "Debit",
                    "debit": debit,
                    "credit": credit,
                    "amount": credit if is_income else debit,
                    "balance": balance,
                })

        # Keep CSV order for balance validation. Date-based methods
        # sort their own data when necessary.
        return self.transactions

    def calculate_monthly_average(self):
        """Average daily closing balance across each full calendar month."""
        if not self.transactions:
            return {}

        by_date = defaultdict(list)
        for txn in self.transactions:
            if txn["balance"] is not None:
                by_date[txn["date"]].append(txn)

        if not by_date:
            return {}

        first_date = min(t["date"] for t in self.transactions)
        last_date = max(t["date"] for t in self.transactions)
        months = sorted({t["month"] for t in self.transactions})
        result = {}

        for month in months:
            year, mon = map(int, month.split("-"))
            days = calendar.monthrange(year, mon)[1]
            running = self.starting_balance or Decimal("0.00")
            total = Decimal("0.00")

            for day in range(1, days + 1):
                date = f"{year:04d}-{mon:02d}-{day:02d}"

                # The opening balance is the only safe carry-forward
                # before the first known daily closing balance.
                if date in by_date:
                    ordered = sorted(
                        by_date[date], key=lambda t: t["line_number"]
                    )
                    running = ordered[-1]["balance"]
                elif date < first_date:
                    running = self.starting_balance or Decimal("0.00")

                total += running

            result[month] = {
                "days": days,
                "average_daily_closing_balance": amount_text(
                    total / Decimal(days)
                ),
            }

        return result

    def find_balance_breaks(self):
        """Validate each transaction balance against prior printed balance."""
        result = []
        previous = self.starting_balance

        for txn in sorted(self.transactions, key=lambda t: t["line_number"]):
            printed = txn["balance"]

            if printed is None:
                continue

            if previous is not None:
                expected = (
                    previous + txn["credit"] - txn["debit"]
                ).quantize(Decimal("0.01"))

                if expected != printed:
                    result.append({
                        "line_number": txn["line_number"],
                        "date": txn["date"],
                        "description": txn["description"],
                        "expected_balance": amount_text(expected),
                        "printed_balance": amount_text(printed),
                        "difference": amount_text(printed - expected),
                    })

            previous = printed

        return result

    def find_bounced_cheques(self):
        """Link cheque deposits, return entries, and return-charge entries."""
        groups = defaultdict(list)

        for txn in self.transactions:
            cheque = extract_cheque_number(txn["description"])
            if cheque:
                groups[cheque].append(txn)

        results = []
        for cheque, items in groups.items():
            returns = [
                t for t in items
                if re.search(
                    r"\bCHQ\s*RTN\b|\bCHEQUE\s*RETURN\b|"
                    r"\bCHECK\s*RETURN\b",
                    t["description"], re.IGNORECASE
                )
            ]

            for returned in returns:
                earlier_deposits = [
                    t for t in items
                    if t["credit"] > 0
                    and t["datetime"] <= returned["datetime"]
                    and t is not returned
                    and not re.search(
                        r"\bRTN CHGS?\b|\bRETURN CHARGES?\b",
                        t["description"], re.IGNORECASE
                    )
                ]
                later_charges = [
                    t for t in items
                    if t["datetime"] >= returned["datetime"]
                    and re.search(
                        r"\bRTN CHGS?\b|\bRETURN CHARGES?\b",
                        t["description"], re.IGNORECASE
                    )
                ]

                deposit = max(
                    earlier_deposits,
                    key=lambda t: t["datetime"],
                    default=None,
                )
                charge = min(
                    later_charges,
                    key=lambda t: t["datetime"],
                    default=None,
                )

                results.append({
                    "cheque_number": cheque,
                    "deposit_line": (
                        deposit["line_number"] if deposit else None
                    ),
                    "return_line": returned["line_number"],
                    "charge_line": (
                        charge["line_number"] if charge else None
                    ),
                    "return_date": returned["date"],
                })

        return results

    def find_round_trips(self):
        """Find equal incoming/outgoing transfers to the same party in 48h."""
        credits = sorted(
            [t for t in self.transactions if t["credit"] >= MIN_ROUND_TRIP],
            key=lambda t: t["datetime"],
        )
        debits = [
            t for t in self.transactions if t["debit"] >= MIN_ROUND_TRIP
        ]

        results = []
        used_debits = set()

        for credit in credits:
            party = normalize_counterparty(credit["description"])
            if not party:
                continue

            candidates = []
            for debit in debits:
                if debit["id"] in used_debits:
                    continue
                if debit["debit"] != credit["credit"]:
                    continue
                if normalize_counterparty(debit["description"]) != party:
                    continue

                elapsed = (
                    debit["datetime"] - credit["datetime"]
                ).total_seconds()

                if 0 <= elapsed <= MAX_ROUND_TRIP_HOURS * 3600:
                    candidates.append(debit)

            if candidates:
                debit = min(candidates, key=lambda t: t["datetime"])
                used_debits.add(debit["id"])
                results.append({
                    "counterparty": party,
                    "amount": amount_text(credit["credit"]),
                    "credit_line": credit["line_number"],
                    "debit_line": debit["line_number"],
                    "credit_date": credit["date"],
                    "debit_date": debit["date"],
                    "hours_apart": round(
                        (debit["datetime"] - credit["datetime"])
                        .total_seconds() / 3600, 2
                    ),
                })

        return results

    def analyze(self):
        """Produce the assignment report plus the existing financial summary."""
        txns = self.transactions
        debits = [t for t in txns if t["debit"] > 0]
        credits = [t for t in txns if t["credit"] > 0]

        total_income = sum((t["credit"] for t in txns), Decimal("0.00"))
        total_expenses = sum((t["debit"] for t in txns), Decimal("0.00"))
        net = total_income - total_expenses

        months = defaultdict(
            lambda: {
                "income": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "transaction_count": 0,
            }
        )
        categories = defaultdict(
            lambda: {"total": Decimal("0.00"), "count": 0}
        )

        for t in txns:
            months[t["month"]]["income"] += t["credit"]
            months[t["month"]]["expenses"] += t["debit"]
            months[t["month"]]["transaction_count"] += 1

            if t["debit"] > 0:
                categories[t["category"]]["total"] += t["debit"]
                categories[t["category"]]["count"] += 1

        monthly_trends = {}
        for month, values in sorted(months.items()):
            income = values["income"]
            expenses = values["expenses"]
            monthly_trends[month] = {
                "income": float(income),
                "expenses": float(expenses),
                "net_savings": float(income - expenses),
                "savings_rate_pct": round(
                    float((income - expenses) / income * 100), 2
                ) if income else 0,
                "transaction_count": values["transaction_count"],
            }

        category_breakdown = []
        for name, values in sorted(
            categories.items(), key=lambda item: item[1]["total"],
            reverse=True
        ):
            total = values["total"]
            count = values["count"]
            category_breakdown.append({
                "category": name,
                "total_spent": float(total),
                "percentage_of_expenses": round(
                    float(total / total_expenses * 100), 2
                ) if total_expenses else 0,
                "transaction_count": count,
                "average_transaction": float(total / count) if count else 0,
            })

        first_date = min((t["datetime"] for t in txns), default=None)
        last_date = max((t["datetime"] for t in txns), default=None)
        days = (
            (last_date - first_date).days + 1
            if first_date and last_date else 0
        )

        recurring = defaultdict(list)
        for t in debits:
            recurring[(t["description"], t["debit"])].append(t)

        recurring_expenses = []
        for (description, amount), items in recurring.items():
            if len(items) >= 2:
                recurring_expenses.append({
                    "description": description,
                    "amount": float(amount),
                    "frequency": len(items),
                    "total_spent": float(amount * len(items)),
                    "dates": [t["date"] for t in items],
                })

        recurring_expenses.sort(
            key=lambda item: item["total_spent"], reverse=True
        )

        largest_expense = max(debits, key=lambda t: t["debit"], default=None)
        largest_income = max(credits, key=lambda t: t["credit"], default=None)

        summary = {
            "statement_period": {
                "start_date": first_date.strftime("%Y-%m-%d") if first_date else None,
                "end_date": last_date.strftime("%Y-%m-%d") if last_date else None,
                "total_days": days,
            },
            "total_transactions": len(txns),
            "expense_transaction_count": len(debits),
            "income_transaction_count": len(credits),
            "total_income": float(total_income),
            "total_expenses": float(total_expenses),
            "net_cash_flow": float(net),
            "savings_rate_pct": round(
                float(net / total_income * 100), 2
            ) if total_income else 0,
            "average_daily_spend": float(total_expenses / days) if days else 0,
            "starting_balance": (
                float(self.starting_balance)
                if self.starting_balance is not None else None
            ),
            "ending_balance": (
                float(txns[-1]["balance"])
                if txns and txns[-1]["balance"] is not None else None
            ),
            "largest_expense": (
                {
                    "date": largest_expense["date"],
                    "description": largest_expense["description"],
                    "amount": float(largest_expense["debit"]),
                } if largest_expense else None
            ),
            "largest_income": (
                {
                    "date": largest_income["date"],
                    "description": largest_income["description"],
                    "amount": float(largest_income["credit"]),
                } if largest_income else None
            ),
        }

        return {
            "summary": summary,
            "category_breakdown": category_breakdown,
            "monthly_trends": monthly_trends,
            "recurring_expenses": recurring_expenses,
            "top_expenses": [
                {
                    "date": t["date"],
                    "description": t["description"],
                    "amount": float(t["debit"]),
                }
                for t in sorted(
                    debits, key=lambda t: t["debit"], reverse=True
                )[:5]
            ],
            "monthly_average_balance": self.calculate_monthly_average(),
            "bounces": self.find_bounced_cheques(),
            "round_trips": self.find_round_trips(),
            "balance_breaks": self.find_balance_breaks(),
            "invalid_rows": self.invalid_rows,
        }

    def export_json(self, output_filepath):
        report = self.analyze()
        parent = os.path.dirname(os.path.abspath(output_filepath))
        os.makedirs(parent, exist_ok=True)
        with open(output_filepath, "w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)

    def print_cli_summary(self, report=None):
        report = report or self.analyze()
        summary = report["summary"]

        print("\nBANK STATEMENT ANALYSIS REPORT")
        print("=" * 65)
        print("Transactions:", summary["total_transactions"])
        print("Total income:", f'{summary["total_income"]:,.2f}')
        print("Total expenses:", f'{summary["total_expenses"]:,.2f}')
        print("\nREQUIRED CHECKS")
        print("Monthly averages:", len(report["monthly_average_balance"]))
        print("Bounced cheques:", len(report["bounces"]))
        print("Round trips:", len(report["round_trips"]))
        print("Balance breaks:", len(report["balance_breaks"]))
        print("Invalid rows:", len(report["invalid_rows"]))
        print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Bank Statement Analyzer"
    )
    parser.add_argument(
        "input", nargs="?", default="statement_A.csv",
        help="Input CSV file"
    )
    parser.add_argument(
        "-o", "--output", default="report.json",
        help="Output JSON report"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Do not print summary"
    )
    args = parser.parse_args()

    try:
        analyzer = BankStatementAnalyzer()
        analyzer.load_csv(args.input)
        report = analyzer.analyze()
        analyzer.export_json(args.output)

        if not args.quiet:
            analyzer.print_cli_summary(report)
            print(f"Report saved to: {args.output}")

    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
