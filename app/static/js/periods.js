// Calendar-period UI preview. This registry never changes budgets or expenses.
(() => {
  "use strict";
  const KEY = "budget-companion:periods:v1";
  const PLAN_KEY = "budget-companion:workspace:v1";
  const ACTIVITY_KEY = "budget-companion:dashboard-preview:v1";
  const validMonth = (value) => typeof value === "string" && /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(value);
  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  function range(month) {
    if (!validMonth(month)) return null;
    const start = new Date(`${month}-01T00:00:00Z`);
    const end = new Date(start);
    end.setUTCMonth(end.getUTCMonth() + 1);
    end.setUTCDate(0);
    return { start, end };
  }
  function read() {
    try {
      const raw = window.localStorage.getItem(KEY);
      const stored = raw === null ? { version: 1, periods: [] } : JSON.parse(raw);
      if (!object(stored) || stored.version !== 1 || !Array.isArray(stored.periods) || stored.periods.length > 600) return { error: "period_error_corrupt" };
      const merged = new Map();
      const created = [];
      for (const row of stored.periods) {
        if (!object(row) || !validMonth(row.month) || merged.has(row.month) || typeof row.createdAt !== "string" ||
            !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(row.createdAt) || !Number.isFinite(Date.parse(row.createdAt))) return { error: "period_error_corrupt" };
        created.push({ month: row.month, createdAt: row.createdAt });
        merged.set(row.month, { month: row.month, created: true, hasBudget: false, hasActivity: false });
      }
      for (const [key, field, flag] of [[PLAN_KEY, "plans", "hasBudget"], [ACTIVITY_KEY, "months", "hasActivity"]]) {
        const previous = window.localStorage.getItem(key);
        if (previous === null) continue;
        let legacy;
        try { legacy = JSON.parse(previous); } catch (_) { return { error: "period_error_legacy" }; }
        if (!object(legacy) || legacy.version !== 1 || !object(legacy[field]) || Object.keys(legacy[field]).length > 600) return { error: "period_error_legacy" };
        for (const [month, value] of Object.entries(legacy[field])) {
          if (!validMonth(month) || !object(value)) return { error: "period_error_legacy" };
          const row = merged.get(month) || { month, created: false, hasBudget: false, hasActivity: false };
          row[flag] = true;
          merged.set(month, row);
        }
      }
      if (merged.size > 600) return { error: "period_error_limit" };
      return { created, periods: [...merged.values()].sort((a, b) => b.month.localeCompare(a.month)) };
    } catch (error) {
      return { error: error instanceof SyntaxError ? "period_error_corrupt" : "period_error_storage" };
    }
  }
  function create(month) {
    if (!validMonth(month)) return { error: "period_error_month" };
    const latest = read();
    if (latest.error) return latest;
    if (latest.periods.some((period) => period.month === month)) return { error: "period_error_duplicate", duplicate: true };
    if (latest.periods.length >= 600) return { error: "period_error_limit" };
    try {
      window.localStorage.setItem(KEY, JSON.stringify({ version: 1, periods: [...latest.created, { month, createdAt: new Date().toISOString() }] }));
      return { month };
    } catch (_) { return { error: "period_error_storage" }; }
  }
  window.BudgetPeriodPreview = Object.freeze({ KEY, read, create, range, validMonth });

  function initialize() {
    let data, copy;
    try {
      data = JSON.parse(document.getElementById("workspace-data")?.textContent || "null");
      copy = JSON.parse(document.getElementById("workspace-copy")?.textContent || "null");
    } catch (_) { return; }
    if (!data || data.page !== "periods" || !copy) return;
    const t = (key, replacements = {}) => Object.entries(replacements).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), copy[key] || key);
    const locale = data.locale === "vi" ? "vi-VN" : "en-US";
    const months = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" });
    const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    const get = (id) => document.getElementById(id);
    const form = get("period-form"), input = get("period-month"), button = get("period-create"), list = get("period-list");
    if (!form || !input || !button || !list) return;
    const empty = list.firstElementChild.cloneNode(true);
    let lastCreated = "";
    const destination = (base, month) => {
      const url = new URL(base, window.location.origin);
      url.searchParams.set("month", month);
      url.searchParams.set("lang", data.locale);
      return `${url.pathname}${url.search}`;
    };
    function render() {
      const current = read();
      get("period-storage-error").textContent = current.error ? t(current.error) : "";
      get("period-storage-error").hidden = !current.error;
      button.disabled = Boolean(current.error);
      if (current.error) return;
      get("period-count").textContent = t("period_count", { count: current.periods.length });
      const fragment = document.createDocumentFragment();
      for (const period of current.periods) {
        const bounds = range(period.month);
        const row = document.createElement("article");
        row.className = `period-row${period.month === lastCreated ? " is-new" : ""}`;
        const mark = document.createElement("span");
        mark.className = "period-row-icon";
        mark.setAttribute("aria-hidden", "true");
        mark.append(document.querySelector(".period-hero-icon svg").cloneNode(true));
        const body = document.createElement("div");
        body.className = "period-row-copy";
        const title = document.createElement("h3");
        title.textContent = months.format(bounds.start);
        const duration = document.createElement("p");
        duration.textContent = `${dates.format(bounds.start)} – ${dates.format(bounds.end)}`;
        const badge = document.createElement("small");
        badge.textContent = t(period.hasBudget ? "period_budget_saved" : period.hasActivity ? "period_activity_saved" : "period_no_budget");
        body.append(title, duration, badge);
        const link = document.createElement("a");
        link.href = destination(data.dashboardUrl, period.month);
        link.textContent = `${t("period_open")} →`;
        link.setAttribute("aria-label", `${t("period_view_overview")}: ${title.textContent}`);
        row.append(mark, body, link);
        fragment.append(row);
      }
      if (!current.periods.length) fragment.append(empty.cloneNode(true));
      list.replaceChildren(fragment);
    }
    input.addEventListener("input", () => {
      const bounds = range(input.value);
      get("period-start").textContent = bounds ? dates.format(bounds.start) : "—";
      get("period-end").textContent = bounds ? dates.format(bounds.end) : "—";
      input.setAttribute("aria-invalid", "false");
      get("period-error").hidden = true;
      get("period-existing").hidden = true;
      get("period-success").hidden = true;
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const result = create(input.value);
      const error = get("period-error");
      error.hidden = !result.error;
      error.textContent = result.error ? t(result.error) : "";
      input.setAttribute("aria-invalid", String(Boolean(result.error)));
      if (result.error) {
        get("period-success").hidden = true;
        get("period-existing").hidden = !result.duplicate;
        if (result.duplicate) get("period-existing").href = destination(data.dashboardUrl, input.value);
        input.focus();
        return;
      }
      lastCreated = result.month;
      get("period-existing").hidden = true;
      get("period-success-copy").textContent = t("period_success_copy", { month: months.format(range(result.month).start) });
      get("period-success-overview").href = destination(data.dashboardUrl, result.month);
      get("period-success").hidden = false;
      render();
      get("period-success-overview").focus();
    });
    window.addEventListener("storage", () => { get("period-success").hidden = true; render(); });
    render();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
