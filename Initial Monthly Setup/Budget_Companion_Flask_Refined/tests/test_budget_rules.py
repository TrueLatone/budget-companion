"""Run with: python -m unittest discover -s tests -v"""
import unittest
from collections import defaultdict

from budget_rules import (BudgetError, apply_manual_adjustments, generate_schedule,
                          generate_three_plans, validate_setup)


def example(month="2026-10", funds=5_000_000, transport_min=None, p2=True):
    expenses = [
        {"id": "rent", "name": "Rent", "priority": "P0", "amount": 1_500_000,
         "frequency": "monthly", "due_day": 5},
        {"id": "electricity", "name": "Electricity", "priority": "P0", "amount": 200_000,
         "frequency": "monthly", "due_day": 10},
        {"id": "water", "name": "Water", "priority": "P0", "amount": 100_000,
         "frequency": "monthly", "due_day": 31},
        {"id": "food", "name": "Food", "priority": "P1", "minimum": None,
         "frequency": "daily"},
        {"id": "transport", "name": "Transportation", "priority": "P1",
         "minimum": transport_min, "frequency": "weekly"},
    ]
    if p2:
        expenses += [
            {"id": "shopping", "name": "Shopping", "priority": "P2", "frequency": "monthly"},
            {"id": "entertainment", "name": "Entertainment", "priority": "P2",
             "frequency": "weekly"},
        ]
    return {"month": month, "available_funds": funds, "expenses": expenses}


class BudgetRuleTests(unittest.TestCase):
    def test_three_plans_and_correct_percentage_totals(self):
        setup = validate_setup(example())
        plans = generate_three_plans(setup)
        self.assertEqual([x["name"] for x in plans], ["Saving", "Balanced", "Lifestyle"])
        self.assertEqual(plans[0]["totals"],
                         {"P0": 1_800_000, "P1": 2_240_000, "P2": 160_000, "Savings": 800_000})
        self.assertEqual(plans[1]["totals"],
                         {"P0": 1_800_000, "P1": 2_080_000, "P2": 480_000, "Savings": 640_000})
        self.assertEqual(plans[2]["totals"],
                         {"P0": 1_800_000, "P1": 1_920_000, "P2": 960_000, "Savings": 320_000})
        for plan in plans:
            self.assertEqual(sum(a["amount"] for a in plan["allocations"])
                             + plan["totals"]["Savings"], 5_000_000)
            self.assertTrue(all(a["amount"] > 0 for a in plan["allocations"]))

    def test_optional_p1_minimum_is_null(self):
        setup = validate_setup(example(transport_min=None))
        transport = next(e for e in setup["expenses"] if e["id"] == "transport")
        self.assertIsNone(transport["minimum"])
        self.assertEqual(setup["p1_minimum_total"], 0)

    def test_p1_minimum_adjusts_strategy_safely(self):
        setup = validate_setup(example(transport_min=2_300_000))
        plans = generate_three_plans(setup)
        for plan in plans:
            transportation = next(e for e in plan["allocations"] if e["expense_id"] == "transport")
            self.assertGreaterEqual(transportation["amount"], 2_300_000)
            self.assertTrue(plan["adjustments"])
            self.assertGreaterEqual(plan["totals"]["P2"], 2)
            self.assertEqual(sum(a["amount"] for a in plan["allocations"])
                             + plan["totals"]["Savings"], setup["available_funds"])

    def test_detect_shortfall(self):
        with self.assertRaisesRegex(BudgetError, "shortfall"):
            validate_setup(example(funds=2_000_000, transport_min=400_000))

    def test_positive_p0_and_missing_required(self):
        data = example()
        data["expenses"][0]["amount"] = 0
        with self.assertRaises(BudgetError):
            validate_setup(data)
        data = example()
        data["expenses"] = [x for x in data["expenses"] if x["id"] != "water"]
        with self.assertRaisesRegex(BudgetError, "Water"):
            validate_setup(data)

    def test_no_p2_makes_no_fake_expenses(self):
        setup = validate_setup(example(p2=False))
        plans = generate_three_plans(setup)
        for plan in plans:
            self.assertEqual(plan["totals"]["P2"], 0)
            self.assertFalse(any(a["priority"] == "P2" for a in plan["allocations"]))
            self.assertEqual(sum(plan["totals"].values()), setup["available_funds"])

    def test_schedule_sums_match_plan_across_frequencies(self):
        setup = validate_setup(example())
        plan = generate_three_plans(setup)[1]
        schedule = generate_schedule(plan, "2026-10")
        allocated = {a["expense_id"]: a["amount"] for a in plan["allocations"]}
        scheduled = defaultdict(int)
        for frequency, entries in schedule.items():
            for entry in entries:
                scheduled[entry["expense_id"]] += entry["amount"]
                self.assertGreaterEqual(entry["amount"], 0)
        self.assertEqual(dict(scheduled), allocated)
        self.assertEqual(len([x for x in schedule["daily"] if x["expense_id"] == "food"]), 31)
        # October 2026 includes 5 Monday-Sunday calendar portions.
        self.assertEqual(len([x for x in schedule["weekly"] if x["expense_id"] == "transport"]), 5)
        self.assertEqual(next(x for x in schedule["monthly"] if x["expense_id"] == "water")["due_date"], "2026-10-31")

    def test_february_due_day_is_clipped_and_weeks_are_partial(self):
        setup = validate_setup(example(month="2027-02"))
        plan = generate_three_plans(setup)[1]
        schedule = generate_schedule(plan, "2027-02")
        self.assertEqual(next(x for x in schedule["monthly"] if x["expense_id"] == "water")["due_date"], "2027-02-28")
        transport = [x for x in schedule["weekly"] if x["expense_id"] == "transport"]
        self.assertEqual(transport[0]["start"], "2027-02-01")
        self.assertEqual(transport[-1]["end"], "2027-02-28")
        self.assertEqual(sum(x["amount"] for x in transport),
                         next(x["amount"] for x in plan["allocations"] if x["expense_id"] == "transport"))

    def test_ai_weight_invalid_falls_back(self):
        setup = validate_setup(example())
        plans = generate_three_plans(setup, weights_by_plan={
            "Saving": {"P1": {"food": -0.5}, "P2": {"shopping": 1.0}}
        })
        self.assertEqual(sum(plans[0]["totals"].values()), setup["available_funds"])


    def test_manual_edits_create_new_snapshot_without_changing_proposal(self):
        setup = validate_setup(example(transport_min=300_000))
        proposal = generate_three_plans(setup)[1]
        original_food = next(a for a in proposal["allocations"] if a["expense_id"] == "food")["amount"]
        new_allocations = [
            {"expense_id": a["expense_id"], "amount": a["amount"] + (20_000 if a["expense_id"] == "food" else 0)}
            for a in proposal["allocations"] if a["priority"] != "P0"
        ]
        edited = apply_manual_adjustments(setup, proposal, new_allocations, proposal["totals"]["Savings"] - 20_000)
        self.assertTrue(edited["manually_adjusted"])
        self.assertEqual(next(a for a in edited["allocations"] if a["expense_id"] == "food")["amount"], original_food + 20_000)
        self.assertEqual(next(a for a in proposal["allocations"] if a["expense_id"] == "food")["amount"], original_food)
        self.assertEqual(sum(edited["totals"].values()), setup["available_funds"])
        schedule = generate_schedule(edited, setup["month"])
        self.assertEqual(sum(a["amount"] for group in schedule.values() for a in group) + edited["totals"]["Savings"], setup["available_funds"])

    def test_unchanged_editor_matches_proposed_plan(self):
        setup = validate_setup(example())
        proposal = generate_three_plans(setup)[0]
        edits = [{"expense_id": a["expense_id"], "amount": a["amount"]}
                 for a in proposal["allocations"] if a["priority"] != "P0"]
        edited = apply_manual_adjustments(setup, proposal, edits, proposal["totals"]["Savings"])
        self.assertFalse(edited["manually_adjusted"])
        self.assertEqual(edited["totals"], proposal["totals"])

    def test_manual_edit_must_keep_total_equal(self):
        setup = validate_setup(example())
        proposal = generate_three_plans(setup)[1]
        edits = [{"expense_id": a["expense_id"], "amount": a["amount"]}
                 for a in proposal["allocations"] if a["priority"] != "P0"]
        with self.assertRaisesRegex(BudgetError, "Unallocated funds"):
            apply_manual_adjustments(setup, proposal, edits, proposal["totals"]["Savings"] - 100)
        with self.assertRaisesRegex(BudgetError, "Over budget"):
            apply_manual_adjustments(setup, proposal, edits, proposal["totals"]["Savings"] + 100)

    def test_manual_edit_protects_minimum_and_positive_amounts(self):
        setup = validate_setup(example(transport_min=350_000))
        proposal = generate_three_plans(setup)[1]
        edits = [{"expense_id": a["expense_id"], "amount": a["amount"]}
                 for a in proposal["allocations"] if a["priority"] != "P0"]
        wrong_minimum = [dict(item) for item in edits]
        next(a for a in wrong_minimum if a["expense_id"] == "transport")["amount"] = 349_999
        with self.assertRaisesRegex(BudgetError, "P1 minimum"):
            apply_manual_adjustments(setup, proposal, wrong_minimum, proposal["totals"]["Savings"])
        zero_expense = [dict(item) for item in edits]
        next(a for a in zero_expense if a["expense_id"] == "shopping")["amount"] = 0
        with self.assertRaisesRegex(BudgetError, "positive"):
            apply_manual_adjustments(setup, proposal, zero_expense, proposal["totals"]["Savings"])

    def test_manual_edit_cannot_modify_p0_or_add_fake_expense(self):
        setup = validate_setup(example())
        proposal = generate_three_plans(setup)[2]
        edits = [{"expense_id": a["expense_id"], "amount": a["amount"]}
                 for a in proposal["allocations"] if a["priority"] != "P0"]
        with self.assertRaisesRegex(BudgetError, "Only existing P1/P2"):
            apply_manual_adjustments(setup, proposal, edits + [{"expense_id": "rent", "amount": 1}], proposal["totals"]["Savings"])
        with self.assertRaisesRegex(BudgetError, "Only existing P1/P2"):
            apply_manual_adjustments(setup, proposal, edits + [{"expense_id": "fake", "amount": 1}], proposal["totals"]["Savings"])
        with self.assertRaisesRegex(BudgetError, "every included"):
            apply_manual_adjustments(setup, proposal, edits[:-1], proposal["totals"]["Savings"])


if __name__ == "__main__":
    unittest.main()
