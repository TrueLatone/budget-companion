from pathlib import Path
import argparse
import re
import pandas as pd
import numpy as np

REQUIRED_COLUMNS = [
    "user_id", "row_kind", "task_id", "assigned_date", "planned_amount",
    "task_status", "record_id", "record_type", "title", "category",
    "amount", "expense_date"
]


def normalize_category(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    aliases = {
        "books_and_supplies": "books_supplies",
        "books_supplies": "books_supplies",
        "health_and_wellness": "health_wellness",
        "health_wellness": "health_wellness",
        "housing_rent": "housing",
    }
    return aliases.get(value, value)


def load_data(input_file):
    df = pd.read_csv(input_file, dtype=str).fillna("")
    df.columns = df.columns.str.strip()
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for col in REQUIRED_COLUMNS:
        df[col] = df[col].astype(str).str.strip()

    for col in ["amount", "planned_amount"]:
        df[col] = pd.to_numeric(
            df[col].str.replace(r"[$,\s]", "", regex=True),
            errors="coerce"
        )

    for col in ["assigned_date", "expense_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["task_status"] = df["task_status"].str.upper()
    df["category_norm"] = df["category"].apply(normalize_category)
    return df


def run_f18(df, output_dir):
    historical_statuses = ["WITHIN_BUDGET", "OVER_BUDGET", "UNRECORDED", "NO_EXPENSE"]
    historical = df[df["task_status"].isin(historical_statuses)].copy()
    unexpected = df[df["row_kind"].eq("UNEXPECTED_TRANSACTION")].copy()
    records = pd.concat([historical, unexpected], ignore_index=True)

    records["is_unrecorded"] = records["task_status"].eq("UNRECORDED")
    records["is_no_expense"] = records["task_status"].eq("NO_EXPENSE")
    records["is_transaction"] = records["row_kind"].isin(
        ["TASK_TRANSACTION", "UNEXPECTED_TRANSACTION"]
    )

    def get_missing_fields(row):
        required = [
            ("record_id", bool(str(row["record_id"]).strip())),
            ("amount", pd.notna(row["amount"]) and float(row["amount"]) > 0),
            ("category", bool(str(row["category"]).strip())),
            ("expense_date", pd.notna(row["expense_date"])),
        ]
        return ", ".join(name for name, present in required if not present)

    records["missing_fields"] = records.apply(get_missing_fields, axis=1)
    records["is_complete"] = (
        records["is_transaction"]
        & records["record_id"].ne("")
        & records["amount"].notna()
        & records["amount"].gt(0)
        & records["category"].ne("")
        & records["expense_date"].notna()
    )
    records["is_incomplete"] = (
        records["is_unrecorded"]
        | (records["is_transaction"] & ~records["is_complete"])
    )

    summaries = []
    for user_id, user_data in records.groupby("user_id"):
        transactions = user_data[user_data["is_transaction"]]
        complete = transactions[transactions["is_complete"]]
        incomplete = user_data[user_data["is_incomplete"]]
        complete_count = len(complete)
        incomplete_count = len(incomplete)
        denom = complete_count + incomplete_count
        completeness_rate = complete_count / denom * 100 if denom else 0.0

        distinct_categories = complete["category_norm"].nunique()
        dates = complete["expense_date"].dropna()
        coverage_days = (
            (dates.max() - dates.min()).days + 1 if not dates.empty else 0
        )
        sufficient = bool(
            complete_count >= 10
            and distinct_categories >= 3
            and coverage_days >= 30
            and completeness_rate >= 80
        )

        summaries.append({
            "user_id": user_id,
            "total_transaction_records": len(transactions),
            "complete_records": complete_count,
            "unrecorded_tasks": int(user_data["is_unrecorded"].sum()),
            "confirmed_no_expense_tasks": int(user_data["is_no_expense"].sum()),
            "incomplete_records": incomplete_count,
            "completeness_rate_pct": round(completeness_rate, 2),
            "distinct_categories": int(distinct_categories),
            "coverage_days": int(coverage_days),
            "data_sufficient": sufficient,
            "guidance_type": "PERSONALIZED_GUIDANCE" if sufficient else "GENERAL_BASELINE_GUIDANCE",
        })

    summary_df = pd.DataFrame(summaries)
    issue_cols = [
        "user_id", "row_kind", "task_id", "assigned_date", "planned_amount",
        "task_status", "record_id", "record_type", "title", "category", "amount",
        "expense_date", "is_unrecorded", "is_no_expense", "is_transaction",
        "missing_fields", "is_complete", "is_incomplete"
    ]
    issues_df = records[records["is_incomplete"]].copy()
    issues_df = issues_df[issue_cols]

    summary_path = output_dir / "f18_completeness_summary.csv"
    issues_path = output_dir / "f18_data_issues.csv"
    summary_df.to_csv(summary_path, index=False)
    issues_df.to_csv(issues_path, index=False)

    print("=== F18 DATA COMPLETENESS SUMMARY ===")
    print(summary_df.to_string(index=False))
    print("\n=== F18 DATA ISSUES ===")
    print(issues_df.to_string(index=False))
    return summary_df, issues_df


def run_f19(df, target_month, output_dir, rating=None, comment=""):
    user_ids = sorted(df.loc[df["user_id"].ne(""), "user_id"].unique())
    monthly_rows = []
    category_rows = []
    status_rows = []
    unexpected_rows = []

    for user_id in user_ids:
        user_df = df[df["user_id"].eq(user_id)].copy()

        task_rows = user_df[
            user_df["row_kind"].isin(["TASK_TRANSACTION", "TASK_NO_RECORD"])
            & user_df["task_id"].ne("")
        ].copy()
        tasks_month = task_rows[
            task_rows["assigned_date"].dt.strftime("%Y-%m").eq(target_month)
        ].copy()
        tasks_month = tasks_month.sort_values("assigned_date")
        tasks = tasks_month.drop_duplicates(["user_id", "task_id"], keep="first").copy()

        counts = (
            tasks["task_status"].replace("", "UNKNOWN").value_counts()
            .rename_axis("task_status").reset_index(name="task_count")
        )
        counts.insert(0, "month", target_month)
        counts.insert(0, "user_id", user_id)
        status_rows.append(counts)

        confirmed_statuses = ["WITHIN_BUDGET", "OVER_BUDGET"]
        normal_actuals = user_df[
            user_df["row_kind"].eq("TASK_TRANSACTION")
            & user_df["task_status"].isin(confirmed_statuses)
            & user_df["record_id"].ne("")
            & user_df["amount"].gt(0)
            & user_df["expense_date"].dt.strftime("%Y-%m").eq(target_month)
        ].copy()
        unexpected_month = user_df[
            user_df["row_kind"].eq("UNEXPECTED_TRANSACTION")
            & user_df["expense_date"].dt.strftime("%Y-%m").eq(target_month)
        ].copy()
        unexpected_actuals = unexpected_month[
            unexpected_month["record_id"].ne("") & unexpected_month["amount"].gt(0)
        ].copy()

        actuals = pd.concat([normal_actuals, unexpected_actuals], ignore_index=True)
        actuals = actuals.drop_duplicates(subset=["user_id", "record_id"], keep="first").copy()
        actuals["category_for_review"] = actuals["category_norm"]
        actuals.loc[
            actuals["category_for_review"].eq("")
            & actuals["row_kind"].eq("UNEXPECTED_TRANSACTION"),
            "category_for_review"
        ] = "uncategorized_unexpected"
        actuals.loc[
            actuals["category_for_review"].eq(""), "category_for_review"
        ] = "uncategorized_transaction"

        total_actual = float(actuals["amount"].sum())
        unexpected_total = float(unexpected_actuals["amount"].sum())
        planned_available = bool(
            not tasks.empty and tasks["planned_amount"].notna().all()
        )
        total_planned = float(tasks["planned_amount"].sum()) if planned_available else np.nan

        confirmed_task_statuses = ["WITHIN_BUDGET", "OVER_BUDGET", "NO_EXPENSE"]
        task_statuses_complete = bool(
            not tasks.empty and tasks["task_status"].isin(confirmed_task_statuses).all()
        )
        missing_category_count = int(actuals["category_norm"].eq("").sum())
        monthly_data_complete = bool(task_statuses_complete and missing_category_count == 0)

        categories = set(tasks.loc[tasks["category_norm"].ne(""), "category_norm"])
        categories.update(actuals["category_for_review"].unique())
        user_category_rows = []

        for category in sorted(categories):
            category_tasks = tasks[tasks["category_norm"].eq(category)]
            category_actuals = actuals[actuals["category_for_review"].eq(category)]
            statuses = set(category_tasks["task_status"])
            has_incomplete_task = bool(
                statuses.intersection({"UNRECORDED", "PENDING", "UNKNOWN", ""})
            )
            all_no_expense = bool(
                not category_tasks.empty
                and category_tasks["task_status"].eq("NO_EXPENSE").all()
            )
            has_actual = not category_actuals.empty
            actual_observed = (
                float(category_actuals["amount"].sum()) if has_actual
                else (0.0 if all_no_expense else np.nan)
            )
            category_plan_available = bool(
                not category_tasks.empty and category_tasks["planned_amount"].notna().all()
            )
            planned_amount = (
                float(category_tasks["planned_amount"].sum())
                if category_plan_available else np.nan
            )
            variance = np.nan

            if has_incomplete_task:
                status = "INCOMPLETE_DATA"
            elif category_plan_available and (has_actual or all_no_expense):
                variance = actual_observed - planned_amount
                if variance > 0:
                    status = "OVER_BUDGET"
                elif variance < 0:
                    status = "UNDER_BUDGET"
                else:
                    status = "ON_BUDGET"
            elif "OVER_BUDGET" in statuses:
                status = "OVER_BUDGET_FROM_TASK_STATUS"
            elif "WITHIN_BUDGET" in statuses:
                status = "WITHIN_BUDGET_FROM_TASK_STATUS"
            elif all_no_expense:
                status = "NO_EXPENSE_CONFIRMED"
            elif category_tasks.empty and has_actual:
                status = "UNPLANNED_OR_UNEXPECTED_SPENDING"
            else:
                status = "NO_CONFIRMED_DATA"

            record = {
                "user_id": user_id,
                "month": target_month,
                "category": category,
                "planned_amount": planned_amount,
                "confirmed_actual_amount_observed": actual_observed,
                "variance_actual_minus_planned": variance,
                "task_count": len(category_tasks),
                "incomplete_task_count": int(category_tasks["task_status"].isin(
                    ["UNRECORDED", "PENDING", "UNKNOWN", ""]
                ).sum()),
                "status": status,
            }
            category_rows.append(record)
            user_category_rows.append(record)

        categories_over_budget = sum(
            row["status"] in ["OVER_BUDGET", "OVER_BUDGET_FROM_TASK_STATUS"]
            for row in user_category_rows
        )
        categories_unplanned = int(
            actuals.loc[actuals["row_kind"].eq("UNEXPECTED_TRANSACTION"), "category_for_review"].nunique()
        )

        monthly_rows.append({
            "user_id": user_id,
            "month": target_month,
            "total_planned": total_planned,
            "total_confirmed_spending_observed": round(total_actual, 2),
            "remaining_vs_plan": (
                round(total_planned - total_actual, 2)
                if planned_available and monthly_data_complete else np.nan
            ),
            "categories_over_budget": int(categories_over_budget),
            "categories_unplanned": categories_unplanned,
            "unrecorded_tasks": int(tasks["task_status"].eq("UNRECORDED").sum()),
            "pending_tasks": int(tasks["task_status"].eq("PENDING").sum()),
            "confirmed_no_expense_tasks": int(tasks["task_status"].eq("NO_EXPENSE").sum()),
            "within_budget_tasks": int(tasks["task_status"].eq("WITHIN_BUDGET").sum()),
            "over_budget_tasks": int(tasks["task_status"].eq("OVER_BUDGET").sum()),
            "unexpected_spending_total": round(unexpected_total, 2),
            "missing_category_transactions": missing_category_count,
            "planned_amount_available": planned_available,
            "monthly_task_data_complete": monthly_data_complete,
            "satisfaction_rating": rating if rating is not None else "",
            "review_comment": comment,
            "review_status": (
                "PARTIAL_REVIEW_PLAN_DATA_MISSING" if not planned_available
                else "PARTIAL_REVIEW_DATA_INCOMPLETE" if not monthly_data_complete
                else "REVIEW_READY"
            ),
        })

        if not unexpected_month.empty:
            unexpected_month = unexpected_month.copy()
            unexpected_month["month"] = target_month
            unexpected_rows.append(unexpected_month)

    summary_df = pd.DataFrame(monthly_rows)
    category_df = pd.DataFrame(category_rows)
    status_df = pd.concat(status_rows, ignore_index=True) if status_rows else pd.DataFrame()
    unexpected_df = (
        pd.concat(unexpected_rows, ignore_index=True)
        if unexpected_rows else pd.DataFrame(columns=list(df.columns) + ["month"])
    )

    summary_df.to_csv(output_dir / "f19_monthly_review_summary.csv", index=False)
    category_df.to_csv(output_dir / "f19_category_review.csv", index=False)
    status_df.to_csv(output_dir / "f19_task_status_counts.csv", index=False)
    unexpected_df.to_csv(output_dir / "f19_unexpected_transactions.csv", index=False)

    print(f"\n=== F19 MONTHLY REVIEW: {target_month} ===")
    print(summary_df.to_string(index=False))
    print("\n=== F19 CATEGORY REVIEW ===")
    print(category_df.to_string(index=False))
    print("\n=== F19 TASK STATUS COUNTS ===")
    print(status_df.to_string(index=False))
    return summary_df, category_df, status_df, unexpected_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="f18_f19_.csv")
    parser.add_argument("--month", default="2026-09")
    parser.add_argument("--rating", type=int, choices=[1, 2, 3, 4, 5], default=None)
    parser.add_argument("--comment", default="")
    parser.add_argument("--skip-feedback-prompt", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_path}. Put the CSV next to this script or pass --input."
        )
    input_path = input_path.resolve()
    output_dir = input_path.parent
    df = load_data(input_path)

    run_f18(df, output_dir)

    rating = args.rating
    comment = args.comment[:2000]
    if not args.skip_feedback_prompt and rating is None and not comment:
        try:
            rating_text = input("\nSatisfaction rating from 1 to 5 (press Enter to skip): ").strip()
            if rating_text:
                rating_value = int(rating_text)
                if not 1 <= rating_value <= 5:
                    raise ValueError("Rating must be from 1 to 5.")
                rating = rating_value
            comment = input("Optional review comment (press Enter to skip): ").strip()[:2000]
        except EOFError:
            pass

    run_f19(df, args.month, output_dir, rating=rating, comment=comment)
    print("\nExported F18 files: f18_completeness_summary.csv, f18_data_issues.csv")
    print("Exported F19 files: f19_monthly_review_summary.csv, f19_category_review.csv, f19_task_status_counts.csv, f19_unexpected_transactions.csv")


if __name__ == "__main__":
    main()
