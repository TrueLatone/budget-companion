# Budget Companion — Flask Demo (Revised UI and meal schedule)

An integrated three-screen, minimal Flask demo for initial student budgeting. It preserves the existing **Python budget-generation rules, Gemini/fallback recommendations, and TXT storage**.

## What's changed in this version

1. **Spending views use Daily → Weekly → Monthly**, and **Daily** opens first after confirmation.
2. When viewing a budget for the **current calendar month**, Daily automatically highlights the current day using the browser's local date. For another month, it defaults to day 1. Selecting the Daily tab again also returns to that day's date.
3. **Food is tracked daily** and each Food allowance includes a **Breakfast / Lunch / Dinner** breakdown. The initial 30% / 40% / 30% distribution is an **illustrative, configurable design assumption**, not measured Vietnamese student spending. It is set in `budget_rules.py` as `MEAL_WEIGHTS`. Each day's three meal values add up exactly to the Food allowance, and all Food days add up to the confirmed monthly Food allocation. Meal amounts are *subdivisions*, never extra expenses.
4. **The generated plan screen is read-only.** Users can choose Saving, Balanced or Lifestyle and review the allocations, but cannot edit priorities, expense amounts, P1 minimums, savings, or other financial values there. For changes, return to Budget Setup and regenerate. The Flask `/api/confirm` endpoint also rejects submitted allocation/savings edits, so the restriction is enforced on the server.

## Current scope

- **Screen 1 — Budget Setup**: calendar month, funds actually on hand, required Rent/Electricity/Water P0, optional Internet, optional Food/Transportation P1 minimums, additional P0/P1/P2 expenses and tracking cycles. The user may add/edit expenses **before generation**; Gemini or rule-based fallback may suggest priorities requiring review before generating.
- **Screen 2 — Generate and Choose**: three plan choices using the fixed style percentages below, protected P1 minimums, and recommended individual expense weights. All figures on this screen are read-only. Confirmation saves the selected proposal unchanged.
- **Screen 3 — Daily → Weekly → Monthly**: planned daily spending and Food meals, calendar-week allowances (including partial weeks), and monthly due dates/allocations. It shows planned limits, **not recorded actual spending**.

| Style | P1 Essential | P2 Flexible | Savings |
|---|---:|---:|---:|
| Saving | 70% | 5% | 25% |
| Balanced | 65% | 15% | 20% |
| Lifestyle | 60% | 30% | 10% |

Ratios apply **after P0 reservation**. If targets conflict with positive included expenses or user-specified P1 minimums, the existing Python generator adjusts the style within permitted constraints or rejects infeasible inputs. Totals are always computed/validated by Python, not Gemini.

## Requirements

- Python 3.10+ (3.11+ preferred)
- `uv` or `pip`
- Dependencies installed from `requirements.txt`:
  - `Flask>=3.0,<4.0`
  - `google-genai>=1.0,<2.0`
  - `python-dotenv>=1.0,<2.0`
- A modern browser (HTML/CSS/JavaScript)

**Only external API: Google Gemini Developer API**, requiring `GEMINI_API_KEY` for AI suggestions. No other API key is needed. Without the key or on a timeout, the app uses *labelled rule-based fallback recommendations*. The Gemini model and timeout are configurable in `.env`; check that the named model is available to your API project.

## Run on Windows with uv

Extract the ZIP and open PowerShell inside the project directory:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your Gemini key (optional):

```dotenv
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=YOUR_AVAILABLE_GEMINI_MODEL
GEMINI_TIMEOUT_MS=60000
```

Then:

```powershell
python app.py
```

Open **http://127.0.0.1:5000/**. Do **not** open `templates/index.html` by double-clicking; it needs Flask's API endpoints.

Alternatively, run without activating the environment:

```powershell
uv run --with-requirements requirements.txt python app.py
```

On macOS/Linux use `source .venv/bin/activate` and `cp .env.example .env` instead.

## Demonstration steps

1. **Load sample data** (November 2026, 30 days), or choose another month. For a demonstration of current-day navigation, select the actual current month.
2. Click **Generate 3 plans**. If the custom expense priority is set to **Suggest**, review the recommendation and click Generate again.
3. Select one of the three plans. The detailed expense table shows **fixed, non-editable** monthly allocations.
4. Click **Confirm selected plan**. Flask stores the plan and schedule as JSON lines in `data/budgets.txt`.
5. The **Daily** calendar is shown automatically. Select a day to see Breakfast, Lunch and Dinner inside the daily Food amount. Move to **Weekly** and **Monthly** using the tab bar.

## Architecture

```text
Budget_Companion_Flask_Refined/
├── app.py                  # Flask routes; server-side no-edit confirmation
├── budget_rules.py         # Existing plan rules + Food meal subdivision
├── ai_service.py           # Existing Gemini integration / rule-based fallback
├── storage.py              # TXT JSON-lines store
├── requirements.txt
├── .env.example
├── templates/index.html    # Three-screen interface
├── static/app.js           # Screen navigation and backend API calls
├── static/style.css        # Minimal responsive style
├── tests/                  # Python unit tests incl. daily meal totals
└── data/.gitkeep
```

| Endpoint | Purpose |
|---|---|
| `GET /` | Serve frontend |
| `POST /api/suggest-priorities` | Gemini/fallback custom P1/P2 priority recommendations |
| `POST /api/generate` | Generate three plans and store the draft |
| `POST /api/confirm` | Accept **draft_id + plan_name only**, store unchanged chosen plan and schedule |
| `GET /api/history` | Read summary of recent confirmed plans |

## Testing

```powershell
python -m unittest discover -s tests -v
```

Tests cover existing plan financial rules, AI fallbacks, 28/30/31-day month scheduling, and meal totals. The backend calculations, Gemini client, and TXT format remain lightweight for a local university demo.

**Not yet built:** actual-spending check-in, reallocation following overspending, mid-month revisions, authenticated user accounts, secure multi-user database support. The previous `apply_manual_adjustments` utility remains in `budget_rules.py` for backwards compatibility with earlier tests, **but it is not used by any current Flask endpoint or UI**.
