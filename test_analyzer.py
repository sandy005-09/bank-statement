"""
Unit tests for BankStatementAnalyzer
Tests data parsing, auto-categorization, analytics metrics, recurring transaction detection,
and JSON export.
Supports execution via pytest, standard unittest, or standalone execution.
"""

import json
import os
import sys
import tempfile
from datetime import datetime

try:
    import unittest
    BaseTestCase = unittest.TestCase
except ImportError:
    # Lightweight fallback for minimal environments without unittest module
    class BaseTestCase:
        def assertEqual(self, a, b, msg=None):
            assert a == b, msg or f"{a!r} != {b!r}"

        def assertAlmostEqual(self, a, b, places=2, msg=None):
            assert round(abs(a - b), places) == 0, msg or f"{a!r} !~= {b!r}"

        def assertTrue(self, expr, msg=None):
            assert expr, msg or "Expected True"

        def assertFalse(self, expr, msg=None):
            assert not expr, msg or "Expected False"

        def assertIn(self, item, container, msg=None):
            assert item in container, msg or f"{item!r} not in {container!r}"

        def assertIsNone(self, val, msg=None):
            assert val is None, msg or f"Expected None, got {val!r}"

        class _AssertRaisesContext:
            def __init__(self, exc_type):
                self.exc_type = exc_type

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    raise AssertionError(f"{self.exc_type.__name__} not raised")
                return issubclass(exc_type, self.exc_type)

        def assertRaises(self, exc_type):
            return self._AssertRaisesContext(exc_type)

from analyzer import BankStatementAnalyzer


class TestBankStatementAnalyzer(BaseTestCase):

    def setUp(self):
        self.analyzer = BankStatementAnalyzer()
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_scratch")
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_amount(self):
        """Test currency cleaning for various formats."""
        self.assertEqual(BankStatementAnalyzer._clean_amount(100), 100.0)
        self.assertEqual(BankStatementAnalyzer._clean_amount(100.5), 100.5)
        self.assertEqual(BankStatementAnalyzer._clean_amount("$1,234.56"), 1234.56)
        self.assertEqual(BankStatementAnalyzer._clean_amount("-50.25"), -50.25)
        self.assertEqual(BankStatementAnalyzer._clean_amount("(75.00)"), -75.0)
        self.assertEqual(BankStatementAnalyzer._clean_amount(""), 0.0)
        self.assertEqual(BankStatementAnalyzer._clean_amount(None), 0.0)
        self.assertEqual(BankStatementAnalyzer._clean_amount("invalid"), 0.0)

    def test_parse_date(self):
        """Test date parsing across multiple standard formats."""
        d1 = BankStatementAnalyzer._parse_date("2026-01-15")
        self.assertEqual(d1, datetime(2026, 1, 15))

        d2 = BankStatementAnalyzer._parse_date("01/15/2026")
        self.assertEqual(d2, datetime(2026, 1, 15))

        d3 = BankStatementAnalyzer._parse_date("15/01/2026")
        self.assertEqual(d3, datetime(2026, 1, 15))

        d4 = BankStatementAnalyzer._parse_date("Jan 15, 2026")
        self.assertEqual(d4, datetime(2026, 1, 15))

        invalid = BankStatementAnalyzer._parse_date("not-a-date")
        self.assertIsNone(invalid)

    def test_auto_categorize(self):
        """Test categorization matching based on keywords and fallback rules."""
        # Keyword based
        self.assertEqual(self.analyzer.auto_categorize("Whole Foods Market"), "Groceries")
        self.assertEqual(self.analyzer.auto_categorize("Starbucks Reserve"), "Dining & Catering")
        self.assertEqual(self.analyzer.auto_categorize("NEFT-DR-ROYAL ESTATES RENT"), "Rent & Facilities")
        self.assertEqual(self.analyzer.auto_categorize("ECS DR LOAN EMI 8801234"), "Loan & EMI")
        self.assertEqual(self.analyzer.auto_categorize("ELECTRICITY BILL PAYMENT"), "Utilities")
        self.assertEqual(self.analyzer.auto_categorize("GST PMT CHALLAN"), "Taxes & Compliance")
        self.assertEqual(self.analyzer.auto_categorize("SALARY BATCH PAYOUT"), "Payroll & Salary")
        self.assertEqual(self.analyzer.auto_categorize("NEFT-DR-METRO FUEL POINT"), "Logistics & Transport")
        self.assertEqual(self.analyzer.auto_categorize("NEFT-CR-MEHTA, JOSHI & CO", is_income=True), "Revenue & Sales Inflow")

        # Explicit category override
        self.assertEqual(
            self.analyzer.auto_categorize("Random Merchant", explicit_category="Education"),
            "Education",
        )

    def test_load_csv_debit_credit_format(self):
        """Test loading CSV with separate Debit and Credit columns."""
        sample_csv = (
            "Date,Description,Debit,Credit,Balance\n"
            "2026-04-01,OPENING BALANCE,,,300000.00\n"
            "2026-04-01,Opening Transfer,0.00,1000.00,301000.00\n"
            "2026-04-02,City Packaging Supplies,50.00,0.00,300950.00\n"
        )
        csv_path = os.path.join(self.test_dir, "test_dc.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(sample_csv)

        txns = self.analyzer.load_csv(csv_path)
        self.assertEqual(len(txns), 2)
        self.assertEqual(self.analyzer.starting_balance, 300000.00)

        # Check Credit transaction
        self.assertEqual(txns[0]["type"], "Credit")
        self.assertEqual(txns[0]["amount"], 1000.00)

        # Check Debit transaction
        self.assertEqual(txns[1]["type"], "Debit")
        self.assertEqual(txns[1]["amount"], 50.00)

    def test_load_csv_amount_type_format(self):
        """Test loading CSV with single Amount and Type columns."""
        sample_csv = (
            "Date,Description,Amount,Type\n"
            "2026-02-01,Salary Direct Dep,3000.00,Credit\n"
            "2026-02-02,Chipotle Lunch,15.50,Debit\n"
        )
        csv_path = os.path.join(self.test_dir, "test_amt.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(sample_csv)

        txns = self.analyzer.load_csv(csv_path)
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0]["type"], "Credit")
        self.assertEqual(txns[0]["amount"], 3000.00)
        self.assertEqual(txns[1]["type"], "Debit")
        self.assertEqual(txns[1]["amount"], 15.50)

    def test_file_not_found(self):
        """Test FileNotFoundError is raised when file does not exist."""
        with self.assertRaises(FileNotFoundError):
            self.analyzer.load_csv("non_existent_file.csv")

    def test_invalid_csv_schema(self):
        """Test ValueError is raised when essential columns are missing."""
        invalid_csv = "ColA,ColB\n1,2\n"
        csv_path = os.path.join(self.test_dir, "invalid.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(invalid_csv)

        with self.assertRaises(ValueError):
            self.analyzer.load_csv(csv_path)

    def test_analyze_calculations(self):
        """Test financial analysis calculations including totals, savings, and categories."""
        sample_csv = (
            "Date,Description,Debit,Credit,Balance\n"
            "2026-04-01,OPENING BALANCE,,,300000.00\n"
            "2026-04-05,NEFT-DR-ROYAL ESTATES RENT,45000.00,,255000.00\n"
            "2026-04-10,NEFT-CR-CUSTOMER A,,100000.00,355000.00\n"
            "2026-05-05,NEFT-DR-ROYAL ESTATES RENT,45000.00,,310000.00\n"
            "2026-05-10,NEFT-CR-CUSTOMER B,,100000.00,410000.00\n"
        )
        csv_path = os.path.join(self.test_dir, "analysis_test.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(sample_csv)

        self.analyzer.load_csv(csv_path)
        report = self.analyzer.analyze()

        summary = report["summary"]
        self.assertEqual(summary["total_transactions"], 4)
        self.assertEqual(summary["total_income"], 200000.00)
        self.assertEqual(summary["total_expenses"], 90000.00)
        self.assertEqual(summary["net_cash_flow"], 110000.00)
        self.assertAlmostEqual(summary["savings_rate_pct"], 55.0, places=1)
        self.assertEqual(summary["starting_balance"], 300000.00)
        self.assertEqual(summary["ending_balance"], 410000.00)

        # Monthly trends
        trends = report["monthly_trends"]
        self.assertIn("2026-04", trends)
        self.assertIn("2026-05", trends)
        self.assertEqual(trends["2026-04"]["income"], 100000.00)
        self.assertEqual(trends["2026-04"]["expenses"], 45000.00)

        # Recurring expenses (Rent 45,000.00 occurred twice)
        recurring = {r["description"]: r for r in report["recurring_expenses"]}
        self.assertIn("NEFT-DR-ROYAL ESTATES RENT", recurring)
        self.assertEqual(recurring["NEFT-DR-ROYAL ESTATES RENT"]["frequency"], 2)
        self.assertEqual(recurring["NEFT-DR-ROYAL ESTATES RENT"]["total_spent"], 90000.00)

    def test_export_json(self):
        """Test exporting analysis report to a valid JSON file."""
        sample_csv = (
            "date,description,debit,credit\n"
            "2026-04-01,Customer Receipt,,50000.00\n"
            "2026-04-02,Office Supplies,1200.00,\n"
        )
        csv_path = os.path.join(self.test_dir, "test_export.csv")
        json_path = os.path.join(self.test_dir, "report_test.json")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(sample_csv)

        self.analyzer.load_csv(csv_path)
        self.analyzer.export_json(json_path)

        self.assertTrue(os.path.exists(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total_income"], 50000.00)
        self.assertEqual(data["summary"]["total_expenses"], 1200.00)


def run_tests():
    """Manual runner that executes all test methods."""
    suite = TestBankStatementAnalyzer()
    methods = [m for m in dir(suite) if m.startswith("test_")]
    passed = 0
    failed = 0

    print(f"Running {len(methods)} tests in test_analyzer.py...")
    for m in methods:
        suite.setUp()
        try:
            getattr(suite, m)()
            passed += 1
            print(f"  [PASS] {m}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {m}: {e}")
        finally:
            suite.tearDown()

    print(f"\nResults: {passed} passed, {failed} failed.")
    if failed > 0:
        exit(1)


if __name__ == "__main__":
    if "unittest" in sys.modules:
        unittest.main()
    else:
        run_tests()
