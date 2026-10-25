"use strict";

/* Three-screen Flask frontend. Python owns budgets, validation, Gemini and schedules. */
const $ = (id) => document.getElementById(id);
const fmt = (number) => `${Math.round(number).toLocaleString("vi-VN")}đ`;
const compact = (number) => number >= 1000000 ? `${(number / 1000000).toFixed(1)}m` : number >= 1000 ? `${Math.round(number / 1000)}k` : String(number);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[character]));
const descriptions = {
  Saving: "More reserved for savings, less for optional spending.",
  Balanced: "A moderate split between needs, optional spending and savings.",
  Lifestyle: "More room for optional purchases and activities."
};
const state = {screen: 1, setup: null, plans: [], chosen: "Balanced", confirmed: null, schedule: null, day: 1, tab: "daily", customId: 0, draftId: null, savedId: null};

function showScreen(screen) {
  if (screen === 2 && !state.plans.length) return;
  if (screen === 3 && !state.confirmed) return;
  state.screen = screen;
  for (let i = 1; i <= 3; i++) $("screen-" + i).hidden = i !== screen;
  document.querySelectorAll(".step").forEach((button, index) => {
    const value = index + 1;
    button.classList.toggle("is-active", value === screen);
    button.classList.toggle("is-complete", value < screen);
    if (value === screen) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  window.scrollTo({top: 0, behavior: "instant"});
}

function parseAmount(value, name, {allowEmpty = false, min = 1} = {}) {
  if (value === "" || value === null || value === undefined) {
    if (allowEmpty) return null;
    throw new Error(`Enter ${name}.`);
  }
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < min || number > 1000000000000) {
    throw new Error(`${name} must be a whole number${min === 0 ? " (zero allowed)" : " greater than zero"}.`);
  }
  return number;
}
function getDue(value, label) {
  if (value === "" || value == null) return null;
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1 || result > 31) throw new Error(`${label} due day must be between 1 and 31.`);
  return result;
}
function monthInfo(month) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) throw new Error("Choose a valid budget month.");
  const [year, monthNumber] = month.split("-").map(Number);
  const days = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const label = new Intl.DateTimeFormat("en-US", {month: "long", year: "numeric", timeZone: "UTC"}).format(new Date(Date.UTC(year, monthNumber - 1, 1)));
  return {year, monthNumber, days, label};
}
function addCustom(name = "", priority = "P2", frequency = "monthly", amount = "", due = "") {
  const id = `custom_${++state.customId}`;
  const row = document.createElement("div");
  row.className = "custom-row";
  row.dataset.id = id;
  row.innerHTML = `
    <label class="mini-field"><span>Expense name</span><input class="custom-name" type="text" maxlength="60" placeholder="e.g. Shopping" aria-label="Custom expense name"></label>
    <label class="mini-field"><span>Priority</span><select class="custom-priority" aria-label="Custom expense priority"><option value="AI">Suggest</option><option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option></select></label>
    <label class="mini-field"><span>Tracking</span><select class="custom-frequency" aria-label="Custom expense frequency"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
    <label class="mini-field"><span class="amount-caption">Amount / minimum</span><input class="custom-amount" type="number" min="1" placeholder="—" aria-label="Custom expense amount or minimum"></label>
    <label class="mini-field"><span>Due day</span><input class="custom-due" type="number" min="1" max="31" placeholder="—" aria-label="Custom expense due day"></label>
    <button class="remove-expense" type="button" aria-label="Remove custom expense" title="Remove expense">×</button>`;
  row.querySelector(".custom-name").value = name;
  row.querySelector(".custom-priority").value = priority;
  row.querySelector(".custom-frequency").value = frequency;
  row.querySelector(".custom-amount").value = amount;
  row.querySelector(".custom-due").value = due;
  row.querySelector(".remove-expense").addEventListener("click", () => {row.remove(); updateSetupSummary();});
  row.querySelectorAll("input,select").forEach((field) => field.addEventListener("input", updateSetupSummary));
  row.querySelector(".custom-priority").addEventListener("change", () => {updateCustomRow(row); updateSetupSummary();});
  row.querySelector(".custom-frequency").addEventListener("change", () => {updateCustomRow(row);updateSetupSummary();});
  updateCustomRow(row);
  $("custom-list").appendChild(row);
  updateSetupSummary();
}
function updateCustomRow(row) {
  const priority = row.querySelector(".custom-priority").value;
  const monthly = row.querySelector(".custom-frequency").value === "monthly";
  const amount = row.querySelector(".custom-amount");
  amount.disabled = priority === "P2" || priority === "AI";
  if (amount.disabled) amount.value = "";
  row.querySelector(".amount-caption").textContent = priority === "P0" ? "Required amount" : priority === "P1" ? "Min. (optional)" : "Not needed";
  row.querySelector(".custom-due").disabled = !monthly;
}
function gatherSetup() {
  const month = $("budget-month").value;
  monthInfo(month);
  const funds = parseAmount($("available-funds").value, "available funds");
  const expenses = [];
  for (const [id, name] of [["rent","Rent"],["electricity","Electricity"],["water","Water"]]) {
    expenses.push({id, name, priority:"P0", frequency:"monthly", amount:parseAmount($(id).value, name), due_day:getDue($(id + "-due").value, name), minimum:null});
  }
  if ($("internet-enabled").checked) expenses.push({id:"internet", name:"Internet", priority:"P0",frequency:"monthly",amount:parseAmount($("internet").value,"Internet"),due_day:getDue($("internet-due").value,"Internet"),minimum:null});
  for (const [id,name,minId] of [["food","Food","food-min"],["transport","Transportation","transport-min"]]) {
    if ($(id + "-enabled").checked) expenses.push({id,name,priority:"P1",frequency:$(id + "-frequency").value,amount:null,minimum:parseAmount($(minId).value,`${name} minimum`,{allowEmpty:true})});
  }
  const names = new Set(expenses.map((item) => item.name.toLowerCase()));
  for (const row of document.querySelectorAll(".custom-row")) {
    const id = row.dataset.id;
    const name = row.querySelector(".custom-name").value.trim();
    if (!name) throw new Error("Please name every additional expense.");
    if (names.has(name.toLowerCase())) throw new Error(`Duplicate expense: ${name}.`);
    names.add(name.toLowerCase());
    let priority = row.querySelector(".custom-priority").value;
    if (priority === "AI") throw new Error(`Please confirm the suggested priority for ${name} before generating.`);
    const frequency = row.querySelector(".custom-frequency").value;
    const number = row.querySelector(".custom-amount").value;
    expenses.push({id,name,priority,frequency,
      amount:priority==="P0" ? parseAmount(number,`${name} amount`) : null,
      minimum:priority==="P1" ? parseAmount(number,`${name} minimum`,{allowEmpty:true}) : null,
      due_day:frequency==="monthly" ? getDue(row.querySelector(".custom-due").value,name) : null});
  }
  const p0 = expenses.filter((e) => e.priority === "P0").reduce((sum,e) => sum + e.amount,0);
  const p1Min = expenses.filter((e) => e.priority === "P1").reduce((sum,e) => sum + (e.minimum || 0),0);
  if (p0 + p1Min > funds) throw new Error(`Budget shortfall: mandatory expenses and P1 minimums exceed available funds by ${fmt(p0 + p1Min - funds)}.`);
  if (expenses.length > 40) throw new Error("Include no more than 40 expenses.");
  return {month,funds,expenses,p0,p1Min,remaining:funds-p0};
}
function updateSetupSummary() {
  // Prevent an old generated plan from being reused after editing setup inputs.
  if (state.screen === 1 && state.plans.length) {state.plans=[];state.confirmed=null;state.schedule=null;state.draftId=null;}
  let p0 = 0, p1 = 0;
  for (const id of ["rent","electricity","water",...($("internet-enabled").checked?["internet"]:[])]) p0 += Number($(id).value) || 0;
  for (const [enabled,min] of [["food-enabled","food-min"],["transport-enabled","transport-min"]]) if ($(enabled).checked) p1 += Number($(min).value) || 0;
  for (const row of document.querySelectorAll(".custom-row")) {
    const val = Number(row.querySelector(".custom-amount").value) || 0;
    const priority = row.querySelector(".custom-priority").value;
    if (priority === "P0") p0 += val;
    if (priority === "P1") p1 += val;
  }
  const funds = Number($("available-funds").value) || 0;
  $("summary-funds").textContent = fmt(funds);
  $("summary-p0").textContent = fmt(p0);
  $("summary-min").textContent = fmt(p1);
  $("summary-remaining").textContent = fmt(funds - p0 - p1);
  $("summary-remaining").style.color = funds < p0 + p1 ? "var(--error)" : "var(--good)";
  $("setup-error").textContent = "";
  $("setup-error").className = "feedback";
}
function loadSample() {
  $("budget-month").value = "2026-11";
  $("available-funds").value = "5000000";
  for (const [id,value,due] of [["rent",1500000,5],["electricity",200000,12],["water",100000,12]]) {$(id).value=value; $(id+"-due").value=due;}
  $("internet-enabled").checked = false;
  $("internet").value = "100000"; $("internet-due").value = "1";
  $("internet").disabled = true; $("internet-due").disabled = true;
  $("food-enabled").checked=true; $("transport-enabled").checked=true;
  $("food-min").value=""; $("transport-min").value="";
  $("food-frequency").value="daily"; $("transport-frequency").value="weekly";
  $("custom-list").innerHTML = "";
  $("priority-review").hidden = true;
  addCustom("Shopping","P2","monthly");
  addCustom("Entertainment","P2","weekly");
  updateSetupSummary();
}
// The backend is the only source of truth for financial calculations.
async function postJson(url, payload) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
  } catch (_) {
    throw new Error("Cannot connect to Flask. Start the app with python app.py and reload this page.");
  }
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error(`The server returned an invalid response (HTTP ${response.status}).`); }
  if (!response.ok) throw new Error(data.error || `Server request failed (HTTP ${response.status}).`);
  return data;
}
function normalizePlan(plan, setupExpenses) {
  const index = new Map(setupExpenses.map(expense => [expense.id, expense]));
  return {
    ...plan,
    savings: plan.totals.Savings,
    allocations: plan.allocations.map(item => ({
      ...item,
      id: item.expense_id,
      minimum: index.get(item.expense_id)?.minimum ?? null
    }))
  };
}
function requestSetupPayload(setup) {
  return {month:setup.month, available_funds:setup.funds, expenses:setup.expenses};
}
async function suggestPendingPriorities() {
  const rows = [...document.querySelectorAll(".custom-row")]
    .filter(row => row.querySelector(".custom-priority").value === "AI");
  if (!rows.length) return false;
  const entries = rows.map(row => ({
    id: row.dataset.id,
    name: row.querySelector(".custom-name").value.trim(),
    priority: "AI"
  }));
  if (entries.some(item => !item.name)) throw new Error("Name every custom expense before requesting priority suggestions.");
  const result = await postJson("/api/suggest-priorities", {expenses: entries});
  const lines = [];
  result.suggestions.forEach(suggestion => {
    const row = rows.find(entry => entry.dataset.id === suggestion.id);
    if (!row) return;
    row.querySelector(".custom-priority").value = suggestion.priority;
    updateCustomRow(row);
    const label = row.querySelector(".custom-name").value.trim();
    lines.push(`<li><strong>${escapeHtml(label)} → ${escapeHtml(suggestion.priority)}</strong> · ${escapeHtml(suggestion.source)}. ${escapeHtml(suggestion.reason)}</li>`);
  });
  const review = $("priority-review");
  review.hidden = false;
  review.innerHTML = `<strong>Review the suggested priorities</strong><ul>${lines.join("")}</ul><p>Change any priority in the form if needed. Click <strong>Generate 3 plans</strong> again to continue.</p>`;
  updateSetupSummary();
  return true;
}
function groupTotals(plan) {
  const totals={P0:0,P1:0,P2:0,Savings:plan.savings};
  plan.allocations.forEach((item)=>totals[item.priority]+=item.amount);
  return totals;
}
function renderPlans() {
  $("plans-grid").innerHTML=state.plans.map((plan)=>{
    const totals=groupTotals(plan), active=state.chosen===plan.name;
    const remaining=state.setup.remaining;
    return `<button class="plan-card ${active?"is-selected":""}" type="button" data-plan="${plan.name}" aria-pressed="${active}" ${state.confirmed?"disabled":""}>
      <div class="plan-header"><span class="radio-dot" aria-hidden="true"></span><div><strong>${plan.name}</strong><p>${descriptions[plan.name]}</p></div></div>
      <div class="plan-alloc-row"><div><small>P1 Essential</small><strong>${fmt(totals.P1)}</strong><span>${plan.ratios.P1}% target</span></div><div><small>P2 Flexible</small><strong>${fmt(totals.P2)}</strong><span>${plan.ratios.P2}% target</span></div><div><small>Savings</small><strong>${fmt(totals.Savings)}</strong><span>${plan.ratios.Savings}% target</span></div></div>
      <div class="distribution-bar" role="img" aria-label="P1 ${plan.ratios.P1} percent, P2 ${plan.ratios.P2} percent, savings ${plan.ratios.Savings} percent"><span class="bar-p1" style="flex:${totals.P1}"></span><span class="bar-p2" style="flex:${totals.P2}"></span><span class="bar-save" style="flex:${totals.Savings}"></span></div>
      ${plan.adjustments.length ? `<p class="plan-adjustment">${plan.adjustments.map(escapeHtml).join(" ")}</p>` : ""}<div class="plan-footer"><span>P0 reserved: ${fmt(totals.P0)}</span>${active?'<span class="selected-tag">Selected</span>':"<span>Choose plan →</span>"}</div>
    </button>`;
  }).join("");
  document.querySelectorAll(".plan-card").forEach((button)=>button.addEventListener("click",()=>{
    if(state.confirmed) return;
    state.chosen=button.dataset.plan;renderPlans();renderReadOnlyPlan();
  }));
}
function currentPlan() {return state.plans.find((plan)=>plan.name===state.chosen);}
function renderReadOnlyPlan() {
  const plan=currentPlan();
  if(!plan) return;
  $("selected-plan-caption").textContent=`${plan.name} plan · read-only, all values in VND`;
  $("editor-rows").innerHTML=plan.allocations.map((item)=>`<tr><td><strong>${escapeHtml(item.name)}</strong></td><td><span class="priority-label"><i class="legend-dot dot-${item.priority.toLowerCase()}"></i>${item.priority}</span></td><td class="min-tag">${item.priority==="P1"&&item.minimum?fmt(item.minimum):"—"}</td><td class="right"><span class="fixed-money">${fmt(item.amount)}</span></td></tr>`).join("") + `<tr><td><strong>Planned savings</strong></td><td>—</td><td>—</td><td class="right"><strong>${fmt(plan.savings)}</strong></td></tr>`;
  const totals=groupTotals(plan);
  $("edit-p0").textContent=fmt(totals.P0);
  $("edit-p1").textContent=fmt(totals.P1);
  $("edit-p2").textContent=fmt(totals.P2);
  $("edit-save").textContent=fmt(totals.Savings);
  const sum=totals.P0+totals.P1+totals.P2+totals.Savings;
  $("edit-total").textContent=fmt(sum);
  $("edit-funds").textContent=fmt(state.setup.funds);
  const valid=sum===state.setup.funds;
  $("edit-validation").className=`feedback ${valid?"valid":"error"}`;
  $("edit-validation").textContent=valid?"All allocations balance. This plan is ready to confirm.":"Plan totals do not match available funds.";
  $("confirm-button").disabled=!valid||Boolean(state.confirmed);
}

// Convert Python's generated schedule into the calendar view model.
// All allocation amounts below come from the /api/confirm response.
function scheduleFromBackend(server, month) {
  const info = monthInfo(month);
  const weekday = (new Date(Date.UTC(info.year, info.monthNumber - 1, 1)).getUTCDay() + 6) % 7;
  const weeks = [];
  for (let start = 1; start <= info.days;) {
    const dayOfWeek = (weekday + start - 1) % 7;
    const end = Math.min(info.days, start + 6 - dayOfWeek);
    weeks.push({index: weeks.length + 1, start, end, days: end - start + 1, entries: []});
    start = end + 1;
  }
  const dates = Array.from({length:info.days}, (_, i) => ({day:i + 1, daily:[], monthly:[], week:0}));
  const monthly = [];
  const row = item => ({id:item.expense_id, name:item.expense, priority:item.priority, amount:item.amount, ...(item.meals ? {meals:item.meals} : {})});
  for (const item of server.daily) {
    const day = Number(item.date.slice(-2));
    if (dates[day-1]) dates[day-1].daily.push(row(item));
  }
  for (const item of server.weekly) {
    const start = Number(item.start.slice(-2));
    const end = Number(item.end.slice(-2));
    const week = weeks.find(w => w.start === start && w.end === end);
    if (week) week.entries.push(row(item));
  }
  for (const item of server.monthly) {
    const due = item.due_date ? Number(item.due_date.slice(-2)) : null;
    const value = {...row(item), due};
    monthly.push(value);
    if (due && dates[due-1]) dates[due-1].monthly.push(value);
  }
  dates.forEach(date => { date.week = weeks.find(week => date.day >= week.start && date.day <= week.end).index; });
  return {...info, month, weekday, dates, weeks, monthly};
}
function dateLabel(day,info,options={}) {
  return new Intl.DateTimeFormat("en-US",{timeZone:"UTC",...options}).format(new Date(Date.UTC(info.year,info.monthNumber-1,day)));
}
function renderMonthly() {
  const month=state.schedule;
  const rows=state.confirmed.allocations.map((e)=>{
    const due=e.frequency==="monthly" && e.due_day!=null?`${dateLabel(Math.min(e.due_day,month.days),month,{month:"short",day:"numeric"})}`:"—";
    return `<tr><td><strong>${escapeHtml(e.name)}</strong></td><td><span class="priority-label"><i class="legend-dot dot-${e.priority.toLowerCase()}"></i>${e.priority}</span></td><td>${e.frequency[0].toUpperCase()+e.frequency.slice(1)}</td><td class="muted-cell">${due}</td><td class="right"><strong>${fmt(e.amount)}</strong></td></tr>`;
  });
  rows.push(`<tr><td><strong>Planned savings</strong></td><td>—</td><td>Monthly reserve</td><td>—</td><td class="right"><strong>${fmt(state.confirmed.savings)}</strong></td></tr>`);
  rows.push(`<tr style="background:#f5f8f9"><td colspan="4"><strong>Total planned funds</strong></td><td class="right"><strong>${fmt(state.setup.funds)}</strong></td></tr>`);
  $("monthly-rows").innerHTML=rows.join("");
}
function renderWeekly() {
  const s=state.schedule;
  $("week-count").textContent=`${s.weeks.length} periods`;
  $("weekly-list").innerHTML=s.weeks.map((week)=>{
    const dates=s.dates.slice(week.start-1,week.end);
    const daily=dates.flatMap((d)=>d.daily);
    const dailyTotal=daily.reduce((n,item)=>n+item.amount,0);
    const weeklyTotal=week.entries.reduce((n,item)=>n+item.amount,0);
    const bills=dates.flatMap((d)=>d.monthly);
    const billsTotal=bills.reduce((n,item)=>n+item.amount,0);
    const total=dailyTotal+weeklyTotal+billsTotal;
    const details=[...week.entries.map((e)=>`${e.name}: ${fmt(e.amount)} (weekly)`),...bills.map((e)=>`${e.name}: ${fmt(e.amount)} (due)`)].slice(0,4);
    return `<article class="week-card"><div class="week-card-head"><div><h3>${dateLabel(week.start,s,{month:"short",day:"numeric"})} – ${dateLabel(week.end,s,{month:"short",day:"numeric"})}</h3><p>${week.days} day${week.days===1?"":"s"} inside ${s.label}</p></div><span class="week-number">Week ${week.index}</span></div><div class="week-table"><span>Daily allowances (combined)</span><strong>${fmt(dailyTotal)}</strong><span>Weekly expense allowances</span><strong>${fmt(weeklyTotal)}</strong><span>Monthly payments due</span><strong>${fmt(billsTotal)}</strong></div><div class="week-card-total"><span>Planned for this period</span><span>${fmt(total)}</span></div>${details.length?`<p class="small-muted" style="margin-top:10px">${details.map(escapeHtml).join(" · ")}</p>`:""}</article>`;
  }).join("");
}
function renderDaily() {
  const s=state.schedule;
  $("calendar-title").textContent=`${s.days}-day calendar`;
  $("calendar-grid").innerHTML=Array.from({length:s.weekday},()=>`<span class="calendar-blank" aria-hidden="true"></span>`).join("")+s.dates.map((item)=>{
    const dayTotal=item.daily.reduce((n,e)=>n+e.amount,0);
    const isCurrent=item.day===state.day;
    return `<button class="calendar-cell ${isCurrent?"is-selected":""}" type="button" data-day="${item.day}" aria-pressed="${isCurrent}" aria-label="${dateLabel(item.day,s,{month:"long",day:"numeric"})}, daily allowance ${fmt(dayTotal)}"><span class="calendar-date">${item.day}</span><span class="calendar-amount">${compact(dayTotal)} daily</span>${item.monthly.length?`<span class="calendar-due">${item.monthly.length} due item${item.monthly.length>1?"s":""}</span>`:""}</button>`;
  }).join("");
  document.querySelectorAll(".calendar-cell").forEach((el)=>el.addEventListener("click",()=>selectDay(Number(el.dataset.day))));
  $("daily-rows").innerHTML=s.dates.map((item)=>{
    const due=item.monthly.length?item.monthly.map((e)=>e.name).join(", "):"—";
    const amount=item.daily.reduce((n,e)=>n+e.amount,0);
    return `<tr><td><button class="text-link" data-day="${item.day}" type="button">${dateLabel(item.day,s,{weekday:"short",month:"short",day:"numeric"})}</button></td><td>${fmt(amount)}</td><td>Week ${item.week}</td><td class="right">${escapeHtml(due)}</td></tr>`;
  }).join("");
  document.querySelectorAll(".text-link[data-day]").forEach((el)=>el.addEventListener("click",()=>{selectDay(Number(el.dataset.day));$("calendar-title").scrollIntoView({behavior:"smooth"});}));
  renderDayDetail();
}
function selectDay(day) {
  if(day<1||day>state.schedule.days)return;
  state.day=day;
  document.querySelectorAll(".calendar-cell").forEach((el)=>{
    const active=Number(el.dataset.day)===day;
    el.classList.toggle("is-selected",active);
    el.setAttribute("aria-pressed",String(active));
  });
  renderDayDetail();
}
function renderDayDetail() {
  const s=state.schedule,date=s.dates[state.day-1],week=s.weeks[date.week-1];
  $("day-title").textContent=dateLabel(state.day,s,{weekday:"long",month:"long",day:"numeric"});
  $("prev-day").disabled=state.day===1;
  $("next-day").disabled=state.day===s.days;
  const lines=(entries)=>entries.length?`<div class="detail-list">${entries.map((e)=>{
    const mealLines=e.meals?`<div class="meal-breakdown"><div class="small-muted">Meal guidance · Breakfast 30%, Lunch 40%, Dinner 30%</div>${["Breakfast","Lunch","Dinner"].map(name=>`<div class="meal-line"><span>${name}</span><strong>${fmt(e.meals[name]??0)}</strong></div>`).join("")}</div>`:"";
    return `<div><div class="detail-line"><span>${escapeHtml(e.name)}</span><strong>${fmt(e.amount)}</strong></div>${mealLines}</div>`;
  }).join("")}</div>`:`<p class="empty-note">No items for this period.</p>`;
  $("day-detail").innerHTML=`<div class="day-block"><h4>Daily spending limits</h4>${lines(date.daily)}</div><hr class="day-divider"><div class="day-block"><h4>Weekly allowances · Week ${week.index}</h4>${lines(week.entries)}<p class="small-muted">Weekly amounts apply to the whole period, not separately to each day.</p></div><hr class="day-divider"><div class="day-block"><h4>Monthly expenses due today</h4>${lines(date.monthly)}</div>`;
}
function preferredDay() {
  if(!state.schedule) return 1;
  const today=new Date();
  const s=state.schedule;
  return s.year===today.getFullYear()&&s.monthNumber===today.getMonth()+1
    ? Math.min(today.getDate(),s.days) : 1;
}
function setTab(name) {
  state.tab=name;
  for (const tab of ["daily","weekly","monthly"]) {
    $("tab-"+tab).hidden=tab!==name;
    const button=document.querySelector(`.tab[data-tab="${tab}"]`);
    button.classList.toggle("is-active",tab===name);
    button.setAttribute("aria-selected",tab===name?"true":"false");
  }
  // Open the actual current date when this is the current month.
  // For past/future budget months use the first day.
  if(name==="daily"&&state.schedule) selectDay(preferredDay());
}
function renderSchedule() {
  const s=state.schedule,totals=groupTotals(state.confirmed);
  $("schedule-subtitle").textContent=`${s.label} · based on your confirmed ${state.confirmed.name} plan.`;
  $("schedule-month-label").textContent=s.label;
  $("stat-plan").textContent=state.confirmed.name;
  $("stat-expenses").textContent=fmt(totals.P0+totals.P1+totals.P2);
  $("stat-savings").textContent=fmt(totals.Savings);
  $("stat-days").textContent=`${s.days} days`;
  renderMonthly(); renderWeekly(); renderDaily(); setTab("daily");
}

function initialize() {
  loadSample();
  document.querySelectorAll(".step").forEach((el)=>el.addEventListener("click",()=>showScreen(Number(el.dataset.go))));
  $("load-example").addEventListener("click",loadSample);
  $("add-expense").addEventListener("click",()=>addCustom("","AI","monthly"));
  $("internet-enabled").addEventListener("change",()=>{
    $("internet").disabled=!$("internet-enabled").checked;
    $("internet-due").disabled=!$("internet-enabled").checked;
    updateSetupSummary();
  });
  for(const [check,ids] of [["food-enabled",["food-min","food-frequency"]],["transport-enabled",["transport-min","transport-frequency"]]]) {
    $(check).addEventListener("change",()=>{ids.forEach((id)=>$(id).disabled=!$(check).checked);updateSetupSummary();});
  }
  document.querySelectorAll("#screen-1 input,#screen-1 select").forEach((el)=>el.addEventListener("input",updateSetupSummary));
  $("generate-button").addEventListener("click", async () => {
    const button = $("generate-button");
    button.disabled = true;
    try {
      if (await suggestPendingPriorities()) return; // User reviews suggestions explicitly.
      const setup = gatherSetup();
      const response = await postJson("/api/generate", requestSetupPayload(setup));
      state.setup = setup;
      state.draftId = response.draft_id;
      state.plans = response.plans.map(plan => normalizePlan(plan, response.setup.expenses));
      state.chosen = "Balanced";
      state.confirmed = null;
      state.schedule = null;
      state.savedId = null;
      $("ai-status").textContent = `${response.ai_source}: ${response.ai_notice}`;
      renderPlans();
      renderReadOnlyPlan();
      showScreen(2);
    } catch (error) {
      $("setup-error").textContent = error.message;
      $("setup-error").className = "feedback error";
    } finally { button.disabled = false; }
  });
  $("back-setup").addEventListener("click",()=>showScreen(1));
  $("confirm-button").addEventListener("click", async () => {
    if (state.confirmed) return;
    const button = $("confirm-button");
    button.disabled = true;
    try {
      // No financial figures are sent from the frontend. Flask reloads
      // the generated draft and confirms the selected plan unchanged.
      const response = await postJson("/api/confirm", {
        draft_id: state.draftId,
        plan_name: state.chosen
      });
      state.confirmed = normalizePlan(response.plan, state.setup.expenses);
      state.schedule = scheduleFromBackend(response.schedule, response.month);
      state.savedId = response.saved_id;
      state.day = preferredDay();
      $("save-status").textContent = `Confirmed plan saved in data/budgets.txt · ID: ${state.savedId}`;
      renderSchedule();
      showScreen(3);
    } catch (error) {
      $("edit-validation").className = "feedback error";
      $("edit-validation").textContent = error.message;
    } finally {button.disabled = Boolean(state.confirmed);}
  });
  $("back-plans").addEventListener("click",()=>{renderPlans();renderReadOnlyPlan();showScreen(2);});
  $("start-over").addEventListener("click",()=>{state.confirmed=null;state.plans=[];state.schedule=null;state.draftId=null;state.savedId=null;$("priority-review").hidden=true;showScreen(1);});
  $("prev-day").addEventListener("click",()=>selectDay(state.day-1));
  $("next-day").addEventListener("click",()=>selectDay(state.day+1));
  document.querySelectorAll(".tab").forEach((el)=>el.addEventListener("click",()=>setTab(el.dataset.tab)));
}

document.addEventListener("DOMContentLoaded",initialize);
