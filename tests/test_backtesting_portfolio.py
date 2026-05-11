import unittest

from backtesting.portfolio import size_position


class BacktestingPortfolioTests(unittest.TestCase):
    def test_size_position_uses_allocation_and_keeps_cash_non_negative(self):
        sized = size_position(cash=100000, price=250, allocation_pct=0.25)

        self.assertEqual(sized.quantity, 100)
        self.assertEqual(sized.notional, 25000)
        self.assertEqual(sized.remaining_cash, 75000)

    def test_size_position_rejects_invalid_price(self):
        with self.assertRaisesRegex(ValueError, "price"):
            size_position(cash=100000, price=0, allocation_pct=0.25)


if __name__ == "__main__":
    unittest.main()
