const monthPicker = document.getElementById("month");
const dayPicker = document.getElementById("tracking_start_day");
let dayWasEdited = false;
dayPicker.addEventListener("input", () => { dayWasEdited = true; });
function showDayRange(adjust) {
  if (!monthPicker.value) return;
  if (!/^(0[1-9]|1[0-2])\/\d{4}$/.test(monthPicker.value)) return;
  const [month, year] = monthPicker.value.split("/").map(Number);
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const today = dayPicker.dataset.today;
  const first = year === Number(today.slice(0,4)) && month === Number(today.slice(5,7)) ? Number(today.slice(8)) : 1;
  dayPicker.min = first;
  dayPicker.max = last;
  if (adjust && !dayWasEdited) dayPicker.value = first;
  if (adjust && Number(dayPicker.value) < first) dayPicker.value = first;
  if (adjust && Number(dayPicker.value) > last) dayPicker.value = last;
}
monthPicker.addEventListener("change", () => showDayRange(true));
showDayRange(false);

const picker = document.getElementById("month-calendar");
const current = dayPicker.dataset.today.slice(0,7);
let year;
function drawPicker() {
  document.getElementById("picker-year").textContent = year;
  document.getElementById("year-prev").disabled = year <= Number(current.slice(0,4));
  document.getElementById("year-next").disabled = year >= 9999;
  const grid = document.getElementById("month-options");
  grid.replaceChildren();
  for (let n=1; n<=12; n++) {
    const num=String(n).padStart(2,"0"), label=num+"/"+year;
    const button=document.createElement("button");
    button.type="button"; button.textContent=num; button.setAttribute("aria-label",label);
    button.setAttribute("aria-pressed",String(label===monthPicker.value));
    button.disabled=year+"-"+num<current;
    button.onclick=()=>{monthPicker.value=label;showDayRange(true);closePicker(true)};
    grid.append(button);
  }
}
const trigger = document.getElementById("open-picker");
function closePicker(restoreFocus) {
  picker.close();
  trigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) trigger.focus();
}
trigger.addEventListener("click", () => {
  if (picker.open) {
    closePicker(true);
    return;
  }
  const currentYear = Number(current.slice(0, 4));
  const inputYear = /^\d{2}\/\d{4}$/.test(monthPicker.value) ? Number(monthPicker.value.slice(3)) : currentYear;
  year = Math.max(inputYear, currentYear);
  drawPicker();
  picker.show();
  trigger.setAttribute("aria-expanded", "true");
  (picker.querySelector('[aria-pressed="true"]:enabled') || picker.querySelector("#month-options button:enabled")).focus();
});
document.getElementById("year-prev").onclick = () => { year--; drawPicker(); };
document.getElementById("year-next").onclick = () => { year++; drawPicker(); };
document.getElementById("picker-close").onclick = () => closePicker(true);
document.addEventListener("keydown", event => {
  if (picker.open && event.key === "Escape") {
    event.preventDefault();
    closePicker(true);
  }
});
function dismissOutside(event) {
  if (picker.open && !picker.contains(event.target) && !trigger.contains(event.target)) closePicker(false);
}
document.addEventListener("pointerdown", dismissOutside);
document.addEventListener("focusin", dismissOutside);
