"use strict";

if (window.location.hash === "#add-expense") {
  const addExpense = document.getElementById("add-expense");
  if (addExpense) {
    addExpense.open = true;
    addExpense.querySelector("input[name='expense_name']").focus();
  }
}

// Only fill the current unsaved form on an explicit click. No financial storage
// or arithmetic lives in the browser, including for amounts beyond JS precision.
const exampleButton = document.getElementById("load-budget-example");
if (exampleButton) {
  exampleButton.hidden = false;
  exampleButton.addEventListener("click", () => {
    const form = document.getElementById("suggested-expenses");
    for (const field of form.querySelectorAll("[data-example]:not(:disabled)")) {
      const key = field.name.split("_")[0];
      if (!form.querySelector(`input[name="suggestion"][value="${key}"]`).checked) continue;
      if (field.name.endsWith("_due_day") &&
          form.elements[`${key}_allocation_frequency`].value !== "MONTHLY") continue;
      field.value = field.dataset.example;
    }
    document.getElementById("budget-example-notice").textContent =
      "Example amounts loaded for selected expenses only. Review them before Apply selected expenses. Nothing has been saved; available funds and existing expenses are unchanged.";
  });
}
