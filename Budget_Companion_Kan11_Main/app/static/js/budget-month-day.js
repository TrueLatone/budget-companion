"use strict";
(() => {
  const monthSelect = document.getElementById("budget-month-picker");
  const dayInput = document.getElementById("tracking-start-day");
  const guidance = document.getElementById("start-day-guidance");
  const script = document.querySelector('script[src*="budget-month-day.js"]');
  if (!monthSelect || !dayInput || !script) return;
  const today = script.dataset.today;
  const currentMonth = today.slice(0, 7);
  const currentDay = Number(today.slice(8, 10));
  const group = dayInput.closest(".bc-form-group");
  const oldErrors = [...group.querySelectorAll(".bc-form-error")];
  const liveError = document.createElement("div");
  liveError.className = "bc-form-error";
  liveError.setAttribute("role", "alert");
  liveError.hidden = true;
  group.appendChild(liveError);
  const validate = () => {
    const day = Number(dayInput.value);
    const min = Number(dayInput.min);
    const max = Number(dayInput.max);
    const valid = dayInput.value.trim() !== "" && Number.isInteger(day) && day >= min && day <= max;
    // Keep the server's message until the entered day has actually been corrected.
    if (valid) oldErrors.forEach(error => { error.hidden = true; });
    if (!valid) {
      liveError.textContent = `Chọn ngày từ ${min} đến ${max}.`;
      liveError.hidden = false;
    } else liveError.hidden = true;
    dayInput.classList.toggle("is-invalid", !valid);
    return valid;
  };
  const sync = (reset) => {
    const selected = monthSelect.value;
    const [year, month] = selected.split("-").map(Number);
    const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const earliest = selected === currentMonth ? currentDay : 1;
    dayInput.min = String(earliest);
    dayInput.max = String(days);
    if (reset || !dayInput.value) dayInput.value = String(earliest);
    guidance.textContent = selected === currentMonth
      ? `Bạn có thể bắt đầu từ ngày ${earliest} đến ngày ${days}.`
      : `Chọn ngày bắt đầu từ 1 đến ${days}.`;
    validate();
  };
  monthSelect.addEventListener("change", () => sync(true));
  dayInput.addEventListener("input", validate);
  // Validation is enforced by the backend as well, including forged POST values.
  sync(false);
})();
