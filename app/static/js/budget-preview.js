const form = document.getElementById("bp-customize");
const vi = document.documentElement.lang === "vi";
const available = BigInt(form.dataset.funds);
const fixed = [...form.querySelectorAll("[data-fixed]")].reduce((sum, row) => sum + BigInt(row.dataset.fixed), 0n);
const edits = [...form.querySelectorAll("[data-minimum]")];
const format = new Intl.NumberFormat(vi ? "vi-VN" : "en-US");
function preview() {
  let spending = fixed;
  let valid = true;
  for (const input of edits) {
    const digits = input.value.trim().replace(/^0+(?=\d)/, "");
    const amount = /^[0-9]{1,19}$/.test(digits) ? BigInt(digits) : null;
    const ok = amount !== null && amount % BigInt(form.dataset.unit || 1) === 0n && amount >= BigInt(input.dataset.minimum) && amount <= 9223372036854775807n;
    input.setCustomValidity(ok ? "" : (vi ? "Nhập số tiền nguyên từ " + format.format(BigInt(input.dataset.minimum)) + " VND." : "Enter a whole amount of at least " + format.format(BigInt(input.dataset.minimum)) + " VND."));
    if(amount !== null && amount % BigInt(form.dataset.unit || 1) !== 0n)
      input.setCustomValidity(vi ? "Nhập số tiền theo bội số 1.000 ₫." : "Enter multiples of 1,000 VND.");
    input.setAttribute("aria-invalid", String(!ok));
    if (ok) spending += amount;
    valid &&= ok;
  }
  const over = spending > available;
  document.getElementById("bp-savings").textContent = valid && !over ? format.format(available - spending) + " VND" : "—";
  const warning = document.getElementById("bp-warning");
  warning.textContent = !valid ? (vi ? "Kiểm tra khoản chi được đánh dấu." : "Check the highlighted amount.") :
    over ? (vi ? "Vượt ngân sách " : "Over budget by ") + format.format(spending - available) + " VND" : "";
  return valid && !over;
}
form.addEventListener("input", preview);
form.addEventListener("submit", event => { if (!preview()) event.preventDefault(); });
preview();
