import unittest

import pandas as pd

from fetch_corporate_events import generate_event_alerts


class CorporateEventsTests(unittest.TestCase):
    def test_generate_event_alerts_handles_numeric_score_delta_with_string_inference(self):
        candidates = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "INVESTMENT_SCORE": 70.0,
                }
            ]
        )
        events = pd.DataFrame(
            [
                {
                    "SYMBOL": "AAA",
                    "EVENT_TYPE": "EX_DIVIDEND",
                    "EVENT_DATE": pd.Timestamp.now().normalize().strftime("%Y-%m-%d"),
                    "DETAIL": "Dividend — ₹1",
                }
            ]
        )

        enriched = generate_event_alerts(candidates, events)

        self.assertEqual(enriched.loc[0, "NEXT_EVENT"], "EX_DIVIDEND")
        self.assertEqual(enriched.loc[0, "EVENT_SCORE_DELTA"], 1)
        self.assertEqual(float(enriched.loc[0, "INVESTMENT_SCORE"]), 71.0)


if __name__ == "__main__":
    unittest.main()
