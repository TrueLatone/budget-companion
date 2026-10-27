// Browser-local Dashboard preview. Nothing here creates server financial records.
(() => {
  "use strict";

  const PLAN_KEY = "budget-companion:workspace:v1";
  const PREVIEW_KEY = "budget-companion:dashboard-preview:v1";
  const MAX_AMOUNT = 1_000_000_000_000;
  const MAX_MONTHS = 600;
  const MAX_RECORDS = 1000;
  const GROUPS = ["p0", "p1", "p2"];
  const MONTH_PATTERN = /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/;
  const CUSTOM_PATTERN = /^custom_[a-z0-9_-]{1,70}$/i;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const BREAKDOWN = [
    { id: "rent", color: "#6358d5" },
    { id: "utilities", color: "#b9b1ed" },
    { id: "food", color: "#e8a18e" },
    { id: "other", color: "#95c9b8" }
  ];
  const TITLE_KEYS = new Set([
    "dash_record_rent", "dash_record_utilities", "dash_record_food",
    "dash_record_groceries", "dash_record_lunch", "dash_record_bus",
    "dash_record_transport", "dash_record_study", "dash_record_social", "dash_record_shopping"
  ]);

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isAmount(value) {
    return Number.isSafeInteger(value) && value > 0 && value <= MAX_AMOUNT;
  }

  function validName(value, maximum = 80) {
    return typeof value === "string" && value.trim().length > 0 && value.trim().length <= maximum &&
      !/[\u0000-\u001f\u007f]/.test(value);
  }

  function validDate(value, month) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
        !value.startsWith(`${month}-`) || value > `${month}-12`) return false;
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }

  // Allocate tenths with largest remainders, so the displayed shares total 100.0%.
  function percentageTenths(amounts) {
    const total = amounts.reduce((sum, amount) => sum + amount, 0);
    if (!total) return amounts.map(() => 0);
    const raw = amounts.map((amount) => amount / total * 1000);
    const rounded = raw.map(Math.floor);
    const order = raw.map((amount, index) => ({ index, remainder: amount - rounded[index] }))
      .sort((a, b) => b.remainder - a.remainder || a.index - b.index);
    const missing = 1000 - rounded.reduce((sum, amount) => sum + amount, 0);
    for (let index = 0; index < missing; index += 1) rounded[order[index].index] += 1;
    return rounded;
  }

  function initialize() {
    const dataNode = document.getElementById("workspace-data");
    const copyNode = document.getElementById("workspace-copy");
    let data;
    let copy;
    try {
      data = JSON.parse(dataNode?.textContent || "null");
      copy = JSON.parse(copyNode?.textContent || "null");
    } catch (_) {
      return;
    }
    if (!isObject(data) || data.page !== "dashboard" || !isObject(data.dashboard) ||
        !isObject(copy) || !MONTH_PATTERN.test(data.month)) return;
    const dashboard = data.dashboard;
    const month = data.month;
    const snapshotDate = `${month}-12`;
    const locale = data.locale === "vi" ? "vi-VN" : "en-US";
    const numbers = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
    const percentages = new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    const shortDates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
    const translate = (key, values = {}) => {
      let text = typeof copy[key] === "string" ? copy[key] : key;
      for (const [name, value] of Object.entries(values)) text = text.replaceAll(`{${name}}`, String(value));
      return text;
    };
    const money = (value) => `${numbers.format(value)} ₫`;
    const formatDate = (value, short = false) => (short ? shortDates : dates).format(new Date(`${value}T00:00:00Z`));
    const byId = (id) => document.getElementById(id);
    const warning = byId("db-warning");
    const feedback = byId("db-feedback");
    const expenseDialog = byId("db-expense-dialog");
    const expenseForm = byId("db-expense-form");
    const nameInput = byId("db-expense-name");
    const categoryInput = byId("db-expense-category");
    const amountInput = byId("db-expense-amount");
    const dateInput = byId("db-expense-date");
    const saveButton = byId("db-expense-save");
    const formError = byId("db-expense-error");
    if (!expenseDialog || !expenseForm || !nameInput || !categoryInput || !amountInput ||
        !dateInput || !saveButton || !formError || !Array.isArray(data.defaultPlan?.categories)) return;

    const defaultCategories = new Map(data.defaultPlan.categories.map((category) => [category.id, category]));
    function validatePlan(candidate) {
      if (!isObject(candidate) || !isAmount(candidate.available) || !Array.isArray(candidate.categories) ||
          candidate.categories.length < defaultCategories.size || candidate.categories.length > 30) return null;
      let total = 0;
      const ids = new Set();
      const categories = [];
      for (const row of candidate.categories) {
        if (!isObject(row) || typeof row.id !== "string" || ids.has(row.id) ||
            !GROUPS.includes(row.group) || !isAmount(row.amount)) return null;
        const original = defaultCategories.get(row.id);
        if (original) {
          if (row.labelKey !== original.labelKey || row.group !== original.group) return null;
          categories.push({ id: row.id, labelKey: original.labelKey, group: row.group, amount: row.amount });
        } else {
          if (!CUSTOM_PATTERN.test(row.id) || !validName(row.name, 60)) return null;
          categories.push({ id: row.id, name: row.name.trim(), group: row.group, amount: row.amount });
        }
        ids.add(row.id);
        total += row.amount;
        if (!Number.isSafeInteger(total)) return null;
      }
      if ([...defaultCategories.keys()].some((id) => !ids.has(id)) || total > candidate.available) return null;
      return { available: candidate.available, categories };
    }

    const defaultPlan = validatePlan(data.defaultPlan);
    if (!defaultPlan) return;
    let plan = defaultPlan;
    let storedPlan = false;
    let planWarning = "";
    let previewWarning = "";
    let blocked = false;
    let hasLocalPreview = false;
    let baselineFingerprint = null;
    let state;
    let opener = null;

    function showWarning() {
      if (!warning) return;
      warning.textContent = translate(previewWarning || planWarning);
      warning.hidden = !previewWarning && !planWarning;
    }

    function announce(key) {
      if (!feedback) return;
      feedback.textContent = translate(key);
      feedback.hidden = false;
    }

    function readPlan() {
      plan = defaultPlan;
      storedPlan = false;
      planWarning = "";
      let raw;
      try {
        raw = window.localStorage.getItem(PLAN_KEY);
      } catch (_) {
        planWarning = "dash_error_storage";
        return;
      }
      if (raw === null) return;
      try {
        const parsed = JSON.parse(raw);
        if (!isObject(parsed) || parsed.version !== 1 || !isObject(parsed.plans) ||
            Object.keys(parsed.plans).length > MAX_MONTHS) throw new Error("Invalid plans");
        const plans = {};
        for (const [key, candidate] of Object.entries(parsed.plans)) {
          const valid = MONTH_PATTERN.test(key) ? validatePlan(candidate) : null;
          if (!valid) throw new Error("Invalid plan");
          plans[key] = valid;
        }
        if (Object.hasOwn(plans, month)) {
          plan = plans[month];
          storedPlan = true;
        }
      } catch (_) {
        planWarning = "dash_error_plan";
      }
    }

    function validateMonth(candidate, selectedMonth) {
      if (!isObject(candidate) || !Array.isArray(candidate.records) || candidate.records.length > MAX_RECORDS ||
          !Array.isArray(candidate.noExpenseDates) || candidate.noExpenseDates.length > 12) return null;
      const records = [];
      const ids = new Set();
      let total = 0;
      for (const record of candidate.records) {
        if (!isObject(record) || typeof record.id !== "string" || !/^[a-z0-9_-]{1,90}$/i.test(record.id) ||
            ids.has(record.id) || !isAmount(record.amount) || !validDate(record.date, selectedMonth) ||
            !GROUPS.includes(record.group) || typeof record.categoryId !== "string") return null;
        const hasTitle = Object.hasOwn(record, "title");
        const hasTitleKey = Object.hasOwn(record, "titleKey");
        if (hasTitle === hasTitleKey || (hasTitle && !validName(record.title)) ||
            (hasTitleKey && !TITLE_KEYS.has(record.titleKey))) return null;
        const original = defaultCategories.get(record.categoryId);
        if (original) {
          if (record.group !== original.group) return null;
        } else if (!CUSTOM_PATTERN.test(record.categoryId) || !validName(record.categoryName, 60)) return null;
        const valid = {
          id: record.id,
          ...(hasTitle ? { title: record.title.trim() } : { titleKey: record.titleKey }),
          categoryId: record.categoryId,
          group: record.group,
          date: record.date,
          amount: record.amount
        };
        if (!original) valid.categoryName = record.categoryName.trim();
        total += record.amount;
        if (!Number.isSafeInteger(total)) return null;
        records.push(valid);
        ids.add(record.id);
      }
      const occupiedDates = new Set(records.map((record) => record.date));
      const noExpenseDates = [];
      for (const date of candidate.noExpenseDates) {
        if (!validDate(date, selectedMonth) || occupiedDates.has(date) || noExpenseDates.includes(date)) return null;
        noExpenseDates.push(date);
      }
      return { records, noExpenseDates };
    }

    function readPreview() {
      let raw;
      try {
        raw = window.localStorage.getItem(PREVIEW_KEY);
      } catch (_) {
        return { error: "dash_error_storage" };
      }
      if (raw === null) return { state: { version: 1, months: {} } };
      try {
        const parsed = JSON.parse(raw);
        if (!isObject(parsed) || parsed.version !== 1 || !isObject(parsed.months) ||
            Object.keys(parsed.months).length > MAX_MONTHS) throw new Error("Invalid preview");
        const months = {};
        for (const [key, value] of Object.entries(parsed.months)) {
          const valid = MONTH_PATTERN.test(key) ? validateMonth(value, key) : null;
          if (!valid) throw new Error("Invalid month");
          months[key] = valid;
        }
        return { state: { version: 1, months } };
      } catch (_) {
        return { error: "dash_error_corrupt" };
      }
    }

    const fingerprint = (candidate) => candidate ? JSON.stringify(candidate) : null;
    readPlan();
    const initial = readPreview();
    const defaultRecords = month === dashboard.sampleMonth && Array.isArray(dashboard.defaultRecords) ? dashboard.defaultRecords : [];
    const defaultState = validateMonth({ records: defaultRecords, noExpenseDates: dashboard.defaultNoExpenseDates || [] }, month);
    if (!defaultState) return;
    state = defaultState;
    if (initial.error) {
      previewWarning = initial.error;
      blocked = true;
    } else if (Object.hasOwn(initial.state.months, month)) {
      state = initial.state.months[month];
      baselineFingerprint = fingerprint(state);
      hasLocalPreview = true;
    }

    function categoryName(category) {
      return category.labelKey ? translate(category.labelKey) : category.name;
    }

    function recordCategoryName(record) {
      const original = defaultCategories.get(record.categoryId);
      return original ? translate(original.labelKey) : record.categoryName;
    }

    function parseAmount(value) {
      const text = String(value).trim();
      const grouping = data.locale === "vi" ? /^\d{1,3}(?:\.\d{3})+$/ : /^\d{1,3}(?:,\d{3})+$/;
      if (!/^\d+$/.test(text) && !grouping.test(text)) return null;
      const parsed = Number(text.replace(data.locale === "vi" ? /\./g : /,/g, ""));
      return isAmount(parsed) ? parsed : null;
    }

    function text(selector, value) {
      document.querySelectorAll(selector).forEach((node) => { node.textContent = value; });
    }

    function svgElement(name, attributes) {
      const node = document.createElementNS(SVG_NS, name);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
      return node;
    }

    function renderChart(amounts, spent) {
      const segments = byId("db-chart-segments");
      const labels = byId("db-chart-labels");
      if (!segments || !labels) return;
      const segmentFragment = document.createDocumentFragment();
      const labelFragment = document.createDocumentFragment();
      const tenths = percentageTenths(amounts);
      const callouts = [];
      const circumference = 2 * Math.PI * 76;
      let start = -Math.PI / 2;
      BREAKDOWN.forEach((category, index) => {
        const amount = amounts[index];
        const row = document.querySelector(`[data-db-category="${category.id}"]`);
        if (row) {
          row.style.setProperty("--db-color", category.color);
          const value = row.querySelector("[data-db-breakdown]");
          const share = row.querySelector("[data-db-percent]");
          if (value) value.textContent = money(amount);
          if (share) share.textContent = percentages.format(tenths[index] / 1000);
        }
        if (!amount || !spent) return;
        const ratio = amount / spent;
        const circle = svgElement("circle", {
          cx: 170, cy: 135, r: 76, fill: "none", stroke: category.color, "stroke-width": 32,
          "stroke-dasharray": `${Math.max(0, ratio * circumference - (ratio < 1 ? 2 : 0))} ${circumference}`,
          transform: `rotate(${start * 180 / Math.PI} 170 135)`
        });
        segmentFragment.append(circle);
        const angle = start + ratio * Math.PI;
        const side = Math.cos(angle) >= 0 ? 1 : -1;
        callouts.push({
          angle, side, color: category.color, label: percentages.format(tenths[index] / 1000),
          y: Math.max(28, Math.min(242, 135 + Math.sin(angle) * 109))
        });
        start += ratio * 2 * Math.PI;
      });
      for (const side of [-1, 1]) {
        const points = callouts.filter((point) => point.side === side).sort((a, b) => a.y - b.y);
        for (let index = 1; index < points.length; index += 1) points[index].y = Math.max(points[index].y, points[index - 1].y + 26);
        if (points.length && points[points.length - 1].y > 242) {
          points[points.length - 1].y = 242;
          for (let index = points.length - 2; index >= 0; index -= 1) points[index].y = Math.min(points[index].y, points[index + 1].y - 26);
        }
        for (const point of points) {
          const fromX = 170 + Math.cos(point.angle) * 94;
          const fromY = 135 + Math.sin(point.angle) * 94;
          const elbowX = side === 1 ? 281 : 59;
          const endX = side === 1 ? 314 : 26;
          const line = svgElement("polyline", {
            points: `${fromX.toFixed(2)},${fromY.toFixed(2)} ${elbowX},${point.y.toFixed(2)} ${endX},${point.y.toFixed(2)}`,
            stroke: point.color, fill: "none", "stroke-width": 1.5, class: "db-chart-connector"
          });
          const label = svgElement("text", {
            x: side === 1 ? 330 : 10, y: point.y - 7,
            "text-anchor": side === 1 ? "end" : "start", fill: point.color, class: "db-chart-percent"
          });
          label.textContent = point.label;
          labelFragment.append(line, label);
        }
      }
      segments.replaceChildren(segmentFragment);
      labels.replaceChildren(labelFragment);
      const total = byId("db-chart-total");
      if (total) {
        total.textContent = money(spent);
        total.style.fontSize = `${spent >= 1_000_000_000_000 ? 10 : spent >= 1_000_000_000 ? 12 : spent >= 10_000_000 ? 14 : 17}px`;
      }
      const empty = byId("db-chart-empty");
      if (empty) empty.hidden = spent !== 0;
      const description = byId("db-chart-description");
      if (description) description.textContent = `${translate("dash_chart_description")} ${BREAKDOWN.map((item, index) =>
        `${item.id === "other" ? translate("dash_other") : translate(defaultCategories.get(item.id).labelKey)}: ${money(amounts[index])} (${percentages.format(tenths[index] / 1000)})`).join("; ")}.`;
    }

    function recordIcon(record) {
      const wrapper = document.createElement("span");
      wrapper.className = "db-expense-icon";
      wrapper.dataset.group = record.group;
      wrapper.setAttribute("aria-hidden", "true");
      const svg = svgElement("svg", {
        viewBox: "0 0 24 24", class: "ws-icon", fill: "none", stroke: "currentColor",
        "stroke-width": 1.7, "stroke-linecap": "round", "stroke-linejoin": "round"
      });
      const paths = {
        rent: "m3 10 9-7 9 7v10H4V10m5 11v-7h6v7",
        utilities: "m13 2-9 12h7l-1 8 10-13h-7l1-7",
        food: "M4 12h16a8 8 0 0 1-16 0ZM8 4v4m4-4v4m4-4v4M7 21h10",
        transport: "M5 17h14V6a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v11Zm0-8h14M7 17v3m10-3v3M8 13h.01M16 13h.01",
        study: "M3 5h7a2 2 0 0 1 2 2v14a3 3 0 0 0-3-2H3V5Zm18 0h-7a2 2 0 0 0-2 2v14a3 3 0 0 1 3-2h6V5Z",
        social: "M5 8h14l-1 13H6L5 8Zm3-5v5m8-5v5M9 13h6",
        shopping: "M5 8h14l1 13H4L5 8Zm3 0V6a4 4 0 0 1 8 0v2"
      };
      svg.append(svgElement("path", { d: paths[record.categoryId] || paths.shopping }));
      wrapper.append(svg);
      return wrapper;
    }

    function orderedRecords() {
      return state.records.map((record, index) => ({ record, index }))
        .sort((a, b) => b.record.date.localeCompare(a.record.date) || b.index - a.index)
        .map(({ record }) => record);
    }

    function renderRecords(container, records) {
      if (!container) return;
      const fragment = document.createDocumentFragment();
      for (const record of records) {
        const row = document.createElement("div");
        row.className = "db-expense-row";
        const content = document.createElement("span");
        content.className = "db-expense-copy";
        const title = document.createElement("strong");
        title.textContent = record.titleKey ? translate(record.titleKey) : record.title;
        const category = document.createElement("small");
        category.textContent = `${recordCategoryName(record)} · ${formatDate(record.date, true)}`;
        content.append(title, category);
        const amount = document.createElement("strong");
        amount.className = "db-expense-amount";
        amount.textContent = `−${money(record.amount)}`;
        row.append(recordIcon(record), content, amount);
        fragment.append(row);
      }
      if (!records.length) {
        const empty = document.createElement("p");
        empty.className = "db-caption db-empty-message";
        empty.textContent = translate("dash_recent_empty");
        fragment.append(empty);
      }
      container.replaceChildren(fragment);
    }

    function refreshCategories() {
      const selected = categoryInput.value;
      const fragment = document.createDocumentFragment();
      for (const group of GROUPS) {
        const optgroup = document.createElement("optgroup");
        optgroup.label = `${group.toUpperCase()} · ${translate(`group_${group}`)}`;
        for (const category of plan.categories.filter((item) => item.group === group)) {
          const option = document.createElement("option");
          option.value = category.id;
          option.textContent = categoryName(category);
          optgroup.append(option);
        }
        fragment.append(optgroup);
      }
      categoryInput.replaceChildren(fragment);
      categoryInput.value = plan.categories.some((item) => item.id === selected) ? selected : "food";
    }

    function render() {
      const groupPlans = Object.fromEntries(GROUPS.map((group) => [group, 0]));
      const groupSpent = Object.fromEntries(GROUPS.map((group) => [group, 0]));
      for (const category of plan.categories) groupPlans[category.group] += category.amount;
      const breakdown = Object.fromEntries(BREAKDOWN.map((category) => [category.id, 0]));
      let spent = 0;
      for (const record of state.records) {
        spent += record.amount;
        groupSpent[record.group] += record.amount;
        breakdown[Object.hasOwn(breakdown, record.categoryId) ? record.categoryId : "other"] += record.amount;
      }
      const planned = GROUPS.reduce((sum, group) => sum + groupPlans[group], 0);
      const remaining = planned - spent;
      const values = { planned, spent, remaining, available: plan.available, unallocated: plan.available - planned };
      for (const [key, value] of Object.entries(values)) text(`[data-db-value="${key}"]`, money(value));
      document.querySelectorAll('[data-db-value="remaining"]').forEach((node) => {
        node.classList.toggle("is-negative", remaining < 0);
        node.dataset.negative = String(remaining < 0);
      });
      if (byId("db-spent-share")) byId("db-spent-share").textContent = translate("dash_spent_help", { percent: percentages.format(spent / planned) });
      if (byId("db-remaining-help")) byId("db-remaining-help").textContent = translate("dash_remaining_help");
      for (const group of GROUPS) {
        const row = document.querySelector(`[data-db-group="${group}"]`);
        if (!row) continue;
        const ratio = groupSpent[group] / groupPlans[group];
        const spentNode = row.querySelector("[data-db-group-spent]");
        const planNode = row.querySelector("[data-db-group-plan]");
        const percent = row.querySelector("[data-db-group-percent]");
        const progress = row.querySelector("[data-db-progress]");
        if (spentNode) spentNode.textContent = numbers.format(groupSpent[group]);
        if (planNode) planNode.textContent = numbers.format(groupPlans[group]);
        if (percent) percent.textContent = percentages.format(ratio);
        if (progress) progress.style.width = `${Math.min(100, ratio * 100)}%`;
        row.classList.toggle("is-negative", ratio > 1);
      }
      renderChart(BREAKDOWN.map((category) => breakdown[category.id]), spent);
      const records = orderedRecords();
      renderRecords(byId("db-recent-list"), records.slice(0, 3));
      renderRecords(byId("db-history-list"), records);
      const updated = byId("db-updated");
      if (updated) updated.textContent = `${hasLocalPreview ? translate("dash_local_updates") :
        records.length ? translate("dash_updated", { date: formatDate(`${month}-11`) }) : translate("dash_no_records")} · ${translate("dash_example")}`;
      const savedPlan = byId("db-plan-source");
      if (savedPlan) {
        savedPlan.textContent = storedPlan ? translate("dash_saved_plan") : "";
        savedPlan.hidden = !storedPlan;
      }
      text(".db-unallocated-amount small", translate("dash_available_help", { amount: money(plan.available) }));
      const recordedToday = state.records.some((record) => record.date === snapshotDate);
      const checkedNoExpense = state.noExpenseDates.includes(snapshotDate);
      const checked = recordedToday || checkedNoExpense;
      const badge = byId("db-checkin-status");
      if (badge) {
        badge.textContent = translate(recordedToday ? "dash_checked_recorded" : checkedNoExpense ? "dash_checked_no_expense" : "dash_pending");
        badge.classList.toggle("is-complete", checked);
      }
      if (byId("db-checkin-date")) byId("db-checkin-date").textContent = formatDate(snapshotDate);
      if (byId("db-checkin-question")) byId("db-checkin-question").textContent = translate("dash_checkin_question");
      if (byId("db-checkin-help")) byId("db-checkin-help").textContent = translate(checked ? "dash_checked_help" : "dash_checkin_help");
      const noExpenseButton = byId("db-no-expense");
      if (noExpenseButton) noExpenseButton.disabled = blocked || checked;
      saveButton.disabled = blocked;
      showWarning();
    }

    function showFormError(key = "") {
      formError.textContent = key ? translate(key) : "";
      formError.hidden = !key;
    }

    function persist(candidate) {
      if (blocked) return previewWarning || "dash_error_storage";
      const valid = validateMonth(candidate, month);
      if (!valid) return "dash_error_limit";
      const latest = readPreview();
      if (latest.error) {
        previewWarning = latest.error;
        blocked = true;
        render();
        return latest.error;
      }
      const latestMonth = Object.hasOwn(latest.state.months, month) ? latest.state.months[month] : null;
      if (fingerprint(latestMonth) !== baselineFingerprint) {
        previewWarning = "dash_error_conflict";
        blocked = true;
        render();
        return previewWarning;
      }
      if (!latestMonth && Object.keys(latest.state.months).length >= MAX_MONTHS) return "dash_error_limit";
      latest.state.months[month] = valid;
      try {
        window.localStorage.setItem(PREVIEW_KEY, JSON.stringify(latest.state));
      } catch (_) {
        previewWarning = "dash_error_storage";
        blocked = true;
        render();
        return previewWarning;
      }
      state = valid;
      baselineFingerprint = fingerprint(valid);
      hasLocalPreview = true;
      render();
      return "";
    }

    document.querySelectorAll("[data-db-add]").forEach((button) => {
      button.addEventListener("click", () => {
        opener = button;
        expenseForm.reset();
        refreshCategories();
        categoryInput.value = "food";
        dateInput.min = `${month}-01`;
        dateInput.max = snapshotDate;
        dateInput.value = snapshotDate;
        expenseForm.querySelectorAll("[aria-invalid]").forEach((input) => input.setAttribute("aria-invalid", "false"));
        showFormError(blocked ? previewWarning : "");
        saveButton.disabled = blocked;
        expenseDialog.showModal();
        nameInput.focus();
      });
    });
    document.querySelectorAll("#db-expense-dialog [data-db-close], #db-history-dialog [data-db-close]").forEach((button) => {
      button.addEventListener("click", () => button.closest("dialog")?.close());
    });
    [expenseDialog, byId("db-history-dialog")].filter(Boolean).forEach((dialog) => {
      dialog.addEventListener("close", () => {
        if (opener?.isConnected) opener.focus();
      });
    });
    byId("db-view-all")?.addEventListener("click", (event) => {
      opener = event.currentTarget;
      byId("db-history-dialog")?.showModal();
    });
    amountInput.addEventListener("blur", () => {
      const amount = parseAmount(amountInput.value);
      if (amount !== null) amountInput.value = numbers.format(amount);
    });
    expenseForm.addEventListener("input", (event) => {
      event.target.setAttribute("aria-invalid", "false");
      if (!blocked) showFormError();
    });
    expenseForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const title = nameInput.value.trim();
      const amount = parseAmount(amountInput.value);
      const category = plan.categories.find((item) => item.id === categoryInput.value);
      const date = dateInput.value;
      const errors = [
        [nameInput, !validName(title), "dash_error_name"],
        [categoryInput, !category, "dash_error_category"],
        [amountInput, amount === null, "dash_error_amount"],
        [dateInput, !validDate(date, month), "dash_error_date"]
      ];
      for (const [input, invalid] of errors) input.setAttribute("aria-invalid", String(invalid));
      const first = errors.find(([, invalid]) => invalid);
      if (first) {
        showFormError(first[2]);
        first[0].focus();
        return;
      }
      if (state.records.length >= MAX_RECORDS) {
        showFormError("dash_error_limit");
        return;
      }
      let id;
      do {
        const suffix = typeof window.crypto?.randomUUID === "function" ? window.crypto.randomUUID() :
          `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
        id = `expense_${suffix}`;
      } while (state.records.some((record) => record.id === id));
      const record = { id, title, categoryId: category.id, group: category.group, date, amount };
      if (!defaultCategories.has(category.id)) record.categoryName = category.name;
      const error = persist({ records: [...state.records, record], noExpenseDates: state.noExpenseDates.filter((item) => item !== date) });
      if (error) {
        showFormError(error);
        return;
      }
      expenseDialog.close();
      announce("dash_expense_saved");
    });
    byId("db-no-expense")?.addEventListener("click", () => {
      if (state.records.some((record) => record.date === snapshotDate)) {
        announce("dash_no_expense_blocked");
        return;
      }
      if (state.noExpenseDates.includes(snapshotDate)) return;
      const error = persist({ records: state.records, noExpenseDates: [...state.noExpenseDates, snapshotDate] });
      if (error) {
        previewWarning = error;
        showWarning();
        return;
      }
      announce("dash_no_expense_saved");
    });
    window.addEventListener("storage", (event) => {
      if (event.key === PLAN_KEY || event.key === null) {
        readPlan();
        refreshCategories();
        render();
      }
      if (event.key === PREVIEW_KEY || event.key === null) {
        const latest = readPreview();
        const latestMonth = latest.state && Object.hasOwn(latest.state.months, month) ? latest.state.months[month] : null;
        if (latest.error || fingerprint(latestMonth) !== baselineFingerprint) {
          previewWarning = latest.error || "dash_error_conflict";
          blocked = true;
          render();
        }
      }
    });
    refreshCategories();
    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
