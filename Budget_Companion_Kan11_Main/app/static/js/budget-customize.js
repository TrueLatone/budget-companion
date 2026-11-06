"use strict";
// Client-side preview only; server recomputes savings and validates P0/P1/P2.
(() => {
  const form = document.getElementById("bp-customize-form");
  if (!form) return;
  const edits = [...form.querySelectorAll("[data-budget-editable]")];
  const fixed = [...form.querySelectorAll("[data-budget-fixed]")];
  const savingsDisplay = form.querySelector("[data-budget-savings-display]");
  const totalElement = document.querySelector("[data-budget-total]");
  const differenceElement = document.querySelector("[data-budget-difference]");
  const feedback = document.querySelector("[data-budget-feedback]");
  const funds = BigInt(form.dataset.funds);
  const max = 9223372036854775807n;
  const format = (v) => `${new Intl.NumberFormat("vi-VN").format(v)} ₫`;
  const parse = (field) => {
    const digits = field.value.trim();
    if (!/^[0-9]+$/.test(digits)) return null;
    // Bound numeric parsing, even for a pasted input with thousands of digits.
    const normalized = digits.replace(/^0+/, "") || "0";
    return normalized.length <= 19 ? BigInt(normalized) : null;
  };

  function update() {
    let invalid = false;
    const values = [];
    for (const field of edits) {
      const number = parse(field);
      const minimum = BigInt(field.dataset.minimum || "1");
      let issue = "";
      if (number === null || number > max) issue = "Nhập số tiền VND hợp lệ.";
      else if (number < minimum) issue = `Mức tối thiểu: ${format(minimum)}.`;
      const error = field.closest(".bv-edit-line").querySelector("[data-budget-error]");
      error.textContent = issue;
      error.hidden = !issue;
      field.setAttribute("aria-invalid", issue ? "true" : "false");
      invalid ||= Boolean(issue);
      values.push(number);
    }
    for (const field of fixed) values.push(parse(field));
    if (invalid || values.some(value => value === null || value > max)) {
      feedback.dataset.state = "error";
      feedback.textContent = "Hãy sửa số tiền được đánh dấu trước khi lưu.";
      savingsDisplay.textContent = totalElement.textContent = differenceElement.textContent = "—";
      return false;
    }
    const spent = values.reduce((sum, value) => sum + value, 0n);
    const savings = funds - spent;
    totalElement.textContent = format(spent);
    savingsDisplay.textContent = format(savings);
    differenceElement.textContent = format(savings < 0n ? savings : 0n);
    const valid = spent <= max && savings >= 0n;
    feedback.dataset.state = valid ? "ok" : "error";
    feedback.textContent = valid ? "Ngân sách đã cân đối." : `Vượt nguồn tiền ${format(-savings)}. Hãy giảm một khoản chi.`;
    return valid;
  }
  form.addEventListener("input", update);
  form.addEventListener("submit", (event) => {
    if (!update()) {
      event.preventDefault();
      const invalid = form.querySelector('[aria-invalid="true"]');
      if (invalid) invalid.focus();
      else { feedback.setAttribute("tabindex", "-1"); feedback.focus(); }
    }
  });
  update();
})();
