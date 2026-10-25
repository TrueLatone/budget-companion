"""Gemini errors must never block local budgeting recommendations."""
import os
import unittest
from unittest.mock import patch

from ai_service import recommend_weights, suggest_priorities


class GeminiFallbackTests(unittest.TestCase):
    @patch("ai_service._ask_gemini", side_effect=TimeoutError("504 GatewayTimeout"))
    def test_priority_suggestions_fall_back_on_timeout(self, request):
        suggestions = suggest_priorities([
            {"id": "study", "name": "Study materials"},
            {"id": "party", "name": "Party"},
        ])
        self.assertEqual([s["priority"] for s in suggestions], ["P1", "P2"])
        self.assertTrue(all(s["source"] == "Rule-based fallback" for s in suggestions))
        request.assert_called_once()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-test-key"})
    @patch("ai_service._ask_gemini", side_effect=TimeoutError("504 GatewayTimeout"))
    def test_expense_weights_fall_back_on_timeout(self, request):
        output = recommend_weights([
            {"id": "food", "name": "Food", "priority": "P1", "frequency": "daily", "minimum": None},
            {"id": "shopping", "name": "Shopping", "priority": "P2", "frequency": "monthly", "minimum": None},
        ])
        self.assertEqual(output["source"], "Rule-based fallback")
        self.assertEqual(output["weights"], {})
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
