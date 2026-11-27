"use strict";

if (window.location.hash === "#add-expense") {
  const addExpense = document.getElementById("add-expense");
  if (addExpense) {
    addExpense.open = true;
    addExpense.querySelector("input[name='expense_name']").focus();
  }
}

for (const frequency of document.querySelectorAll('select[name$="allocation_frequency"]')) {
  const day = frequency.form.elements[frequency.name.replace("allocation_frequency", "due_day")];
  if (!day) continue;
  function updateDay() {
    day.disabled = frequency.value !== "MONTHLY";
    if (day.disabled) day.value = "";
  }
  frequency.addEventListener("change", updateDay);
  updateDay();
}

const priorityField=document.querySelector("#add-expense [name=priority]");
if(priorityField){
 const wrapper=document.querySelector("#add-expense [data-field=minimum_amount]");
 const sync=()=>{wrapper.hidden=priorityField.value!=="P1";wrapper.querySelector("input").disabled=wrapper.hidden;};
 priorityField.addEventListener("change", sync);sync();
}

for (const row of document.querySelectorAll(".bp-setup-row")) {
  const include = row.querySelector('[name="suggestion"]');
  const frequency = row.querySelector("select");
  const due = row.querySelector('[name$="_due_day"]');
  function updateRow() {
    for (const field of row.querySelectorAll("input, select")) {
      if (field !== include) field.disabled = !include.checked;
    }
    due.disabled = !include.checked || frequency.value !== "MONTHLY";
    const extraDay = due.closest(".bp-extra-day");
    if (extraDay) extraDay.hidden = frequency.value !== "MONTHLY";
  }
  include.addEventListener("change", updateRow);
  frequency.addEventListener("change", updateRow);
  updateRow();
}
