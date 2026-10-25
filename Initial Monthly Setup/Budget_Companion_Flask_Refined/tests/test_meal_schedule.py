"""Regression tests for daily Food meal guidance."""
import unittest
from datetime import date
from budget_rules import MEAL_WEIGHTS, generate_schedule, generate_three_plans, validate_setup


class MealScheduleTests(unittest.TestCase):
    def make_setup(self, month="2026-11"):
        return validate_setup({
            "month": month,
            "available_funds": 5_000_000,
            "expenses": [
                {"id": "rent", "name": "Rent", "priority": "P0", "amount": 1_500_000, "frequency": "monthly"},
                {"id": "electricity", "name": "Electricity", "priority": "P0", "amount": 200_000, "frequency": "monthly"},
                {"id": "water", "name": "Water", "priority": "P0", "amount": 100_000, "frequency": "monthly"},
                {"id": "food", "name": "Food", "priority": "P1", "frequency": "daily", "minimum": None},
                {"id": "transport", "name": "Transportation", "priority": "P1", "frequency": "weekly", "minimum": None},
                {"id": "shopping", "name": "Shopping", "priority": "P2", "frequency": "monthly"},
            ],
        })

    def test_meals_sum_to_each_food_day_and_month(self):
        setup = self.make_setup()
        plan = generate_three_plans(setup)[1]
        schedule = generate_schedule(plan, setup["month"])
        foods = [entry for entry in schedule["daily"] if entry["expense_id"] == "food"]
        self.assertEqual(len(foods), 30)
        self.assertEqual(sum(MEAL_WEIGHTS.values()), 100)
        for entry in foods:
            self.assertEqual(set(entry["meals"]), {"Breakfast", "Lunch", "Dinner"})
            self.assertEqual(sum(entry["meals"].values()), entry["amount"])
            self.assertTrue(all(value >= 0 for value in entry["meals"].values()))
        food_month = next(item["amount"] for item in plan["allocations"] if item["expense_id"] == "food")
        self.assertEqual(sum(entry["amount"] for entry in foods), food_month)
        # Existing schedule has no duplicated meal expenses.
        self.assertEqual(sum(e["amount"] for group in schedule.values() for e in group) + plan["totals"]["Savings"], setup["available_funds"])

    def test_non_food_daily_expense_has_no_meal_split(self):
        setup = self.make_setup(month="2027-02")
        plan = generate_three_plans(setup)[0]
        schedule = generate_schedule(plan, setup["month"])
        self.assertEqual(len([e for e in schedule["daily"] if e["expense_id"] == "food"]), 28)
        self.assertTrue(all("meals" not in entry for entry in schedule["daily"] if entry["expense_id"] != "food"))


if __name__ == "__main__":
    unittest.main()
