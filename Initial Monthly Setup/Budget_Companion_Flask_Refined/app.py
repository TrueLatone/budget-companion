"""Run with: python app.py (Flask development server, local demo only)."""

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from ai_service import recommend_weights, suggest_priorities
from budget_rules import (
    BudgetError, generate_schedule,
    generate_three_plans, validate_setup,
)
from storage import find_event, recent_confirmed, save_event

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100_000


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/suggest-priorities")
def suggest():
    payload = request.get_json(silent=True) or {}
    expenses = payload.get("expenses", [])
    if not isinstance(expenses, list) or len(expenses) > 40:
        return jsonify(error="Invalid expense list."), 400
    pending = []
    for item in expenses:
        if not isinstance(item, dict):
            return jsonify(error="Invalid expense."), 400
        expense_id = str(item.get("id", ""))
        name = str(item.get("name", "")).strip()
        if len(expense_id) > 48 or len(name) > 60 or not name:
            return jsonify(error="Invalid expense name or ID."), 400
        if item.get("priority") in (None, "", "AI"):
            pending.append({"id": expense_id, "name": name})
    return jsonify(suggestions=suggest_priorities(pending))


@app.post("/api/generate")
def generate():
    try:
        setup = validate_setup(request.get_json(silent=True))
        ai = recommend_weights(setup["expenses"])
        plans = generate_three_plans(setup, ai["weights"], ai["explanations"])
        draft_id = save_event("generated", {"setup": setup, "plans": plans, "ai": ai["source"]})
        return jsonify(draft_id=draft_id, setup=setup, plans=plans,
                       ai_source=ai["source"], ai_notice=ai["notice"])
    except BudgetError as error:
        return jsonify(error=str(error)), 400


@app.post("/api/confirm")
def confirm():
    payload = request.get_json(silent=True) or {}
    draft_id = str(payload.get("draft_id", ""))
    plan_name = str(payload.get("plan_name", ""))
    draft = find_event(draft_id, "generated")
    if not draft:
        return jsonify(error="Generated draft not found. Generate plans again."), 404
    plan = next((p for p in draft["data"]["plans"] if p["name"] == plan_name), None)
    if not plan:
        return jsonify(error="Select a valid generated plan."), 400
    # Plans and expense priorities are read-only after generation. Even a
    # forged request cannot submit modified allocations or savings.
    if "allocations" in payload or "savings" in payload or "expenses" in payload:
        return jsonify(error="Generated plans are read-only. Return to setup and regenerate to make changes."), 400
    setup = draft["data"]["setup"]
    confirmed_plan = plan
    schedule = generate_schedule(confirmed_plan, setup["month"])
    saved_id = save_event("confirmed", {
        "month": setup["month"],
        "available_funds": setup["available_funds"],
        "original_draft_id": draft_id,
        "original_plan": plan,  # original generated proposal
        "plan": confirmed_plan,  # selected plan without manual changes
        "schedule": schedule,
    })
    return jsonify(saved_id=saved_id, plan=confirmed_plan, month=setup["month"], schedule=schedule)


@app.get("/api/history")
def history():
    return jsonify(recent_confirmed())


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Too many fields submitted."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
