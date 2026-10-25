// Browser-local interactions for the My budget UI preview.
// Plans are isolated by month; this page does not save data to a server.
(() => {
  "use strict";

  const STORAGE_KEY = "budget-companion:workspace:v1";
  const MAX_AMOUNT = 1_000_000_000_000;
  const MAX_CATEGORIES = 30;
  const MAX_MONTHS = 600;
  const GROUPS = ["p0", "p1", "p2"];
  const MONTH_PATTERN = /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/;
  const SVG_NS = "http://www.w3.org/2000/svg";

  function initialize() {
    if (!document.body.classList.contains("bc-workspace")) return;
    initializeSidebar();

    const dataNode = document.getElementById("workspace-data");
    const copyNode = document.getElementById("workspace-copy");
    if (!dataNode || !copyNode) return;

    let data;
    let copy;
    try {
      data = JSON.parse(dataNode.textContent);
      copy = JSON.parse(copyNode.textContent);
    } catch (_) {
      return;
    }
    if (!isRecord(data) || !isRecord(copy)) return;

    const translate = (key) => typeof copy[key] === "string" ? copy[key] : key;
    const locale = data.locale === "vi" ? "vi-VN" : "en-US";
    const numberFormat = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
    const percentFormat = new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const month = MONTH_PATTERN.test(data.month) ? data.month : null;
    const money = (value) => value === null ? "—" : `${numberFormat.format(value)} ₫`;
    const amountText = (value) => numberFormat.format(value);

    const monthPicker = document.getElementById("workspace-month");
    monthPicker?.addEventListener("change", () => {
      if (!MONTH_PATTERN.test(monthPicker.value)) return;
      const destination = new URL(window.location.href);
      destination.searchParams.set("month", monthPicker.value);
      window.location.assign(destination.href);
    });

    const form = document.getElementById("budget-form");
    if (!form || !month) return;
    const availableInput = document.getElementById("budget-available");
    const groupsElement = document.getElementById("budget-groups");
    const errorElement = document.getElementById("budget-error");
    const statusElement = document.getElementById("budget-status");
    const saveButton = document.getElementById("budget-save");
    const addButton = document.getElementById("add-category");
    if (!availableInput || !groupsElement || !errorElement || !saveButton) return;
    const defaultIcons = new Map([...groupsElement.querySelectorAll("[data-category-id]")].map((row) =>
      [row.dataset.categoryId, row.querySelector(".ws-row-icon")?.cloneNode(true)]));

    const defaultCategories = new Map();
    if (!isRecord(data.defaultPlan) || !Array.isArray(data.defaultPlan.categories)) return;
    for (const category of data.defaultPlan.categories) {
      if (!isRecord(category) || typeof category.id !== "string" ||
          typeof category.labelKey !== "string" || !GROUPS.includes(category.group)) return;
      defaultCategories.set(category.id, {
        id: category.id,
        labelKey: category.labelKey,
        group: category.group
      });
    }

    function validatePlan(candidate) {
      if (!isRecord(candidate) || !isAmount(candidate.available) ||
          !Array.isArray(candidate.categories) || candidate.categories.length < defaultCategories.size ||
          candidate.categories.length > MAX_CATEGORIES) return null;
      const ids = new Set();
      const categories = [];
      let planned = 0;
      for (const row of candidate.categories) {
        if (!isRecord(row) || typeof row.id !== "string" || ids.has(row.id) ||
            !GROUPS.includes(row.group) || !isAmount(row.amount)) return null;
        ids.add(row.id);
        planned += row.amount;
        if (!Number.isSafeInteger(planned)) return null;
        const original = defaultCategories.get(row.id);
        if (original) {
          if (row.labelKey !== original.labelKey || row.group !== original.group) return null;
          categories.push({ ...original, amount: row.amount });
        } else {
          if (!/^custom_[a-z0-9_-]{1,70}$/i.test(row.id) || !validName(row.name)) return null;
          categories.push({ id: row.id, name: row.name.trim(), group: row.group, amount: row.amount });
        }
      }
      if ([...defaultCategories.keys()].some((id) => !ids.has(id)) || planned > candidate.available) return null;
      return { available: candidate.available, categories };
    }

    const defaultPlan = validatePlan(data.defaultPlan);
    if (!defaultPlan) return;
    let plan = clonePlan(defaultPlan);
    let storageState = { version: 1, plans: {} };
    let persistentError = "";

    function readStorage() {
      let raw;
      try {
        raw = window.localStorage.getItem(STORAGE_KEY);
      } catch (_) {
        return { error: "budget_error_storage" };
      }
      if (raw === null) return { state: { version: 1, plans: {} } };
      try {
        const parsed = JSON.parse(raw);
        if (!isRecord(parsed) || parsed.version !== 1 || !isRecord(parsed.plans)) throw new Error("Invalid storage");
        const entries = Object.entries(parsed.plans);
        if (entries.length > MAX_MONTHS) throw new Error("Too many months");
        const plans = {};
        for (const [key, value] of entries) {
          const validated = MONTH_PATTERN.test(key) ? validatePlan(value) : null;
          if (!validated) throw new Error("Invalid plan");
          plans[key] = validated;
        }
        return { state: { version: 1, plans } };
      } catch (_) {
        return { error: "budget_error_corrupt" };
      }
    }

    const stored = readStorage();
    if (stored.state) {
      storageState = stored.state;
      if (Object.hasOwn(storageState.plans, month)) plan = clonePlan(storageState.plans[month]);
    } else {
      persistentError = translate(stored.error);
    }

    function parseAmount(value) {
      const text = String(value).trim();
      const grouped = data.locale === "vi" ? /^\d{1,3}(?:\.\d{3})+$/ : /^\d{1,3}(?:,\d{3})+$/;
      // A decimal such as 1.5 must never become 15 when punctuation is removed.
      if (!/^\d+$/.test(text) && !grouped.test(text)) return null;
      const separator = data.locale === "vi" ? /\./g : /,/g;
      const valueAsNumber = Number(text.replace(separator, ""));
      return isAmount(valueAsNumber) ? valueAsNumber : null;
    }

    function categoryName(category) {
      return category.labelKey ? translate(category.labelKey) : category.name;
    }

    function createIcon(group) {
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("class", "ws-icon");
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "1.7");
      svg.setAttribute("stroke-linecap", "round");
      svg.setAttribute("stroke-linejoin", "round");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      const path = document.createElementNS(SVG_NS, "path");
      const paths = {
        p0: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
        p1: "M4 12h16a8 8 0 0 1-16 0ZM8 4v4m4-4v4m4-4v4M7 21h10",
        p2: "M5 8h14l1 13H4L5 8Zm3 0V6a4 4 0 0 1 8 0v2"
      };
      path.setAttribute("d", paths[group]);
      svg.append(path);
      return svg;
    }

    function renderRows() {
      for (const group of GROUPS) {
        const rowsElement = groupsElement.querySelector(`[data-group="${group}"] [data-group-rows]`);
        if (!rowsElement) continue;
        const fragment = document.createDocumentFragment();
        for (const category of plan.categories.filter((item) => item.group === group)) {
          const row = document.createElement("div");
          row.className = "ws-budget-row";
          row.dataset.categoryId = category.id;
          const icon = defaultIcons.get(category.id)?.cloneNode(true) || document.createElement("span");
          icon.className = "ws-row-icon";
          icon.setAttribute("aria-hidden", "true");
          if (!icon.childElementCount) icon.append(createIcon(group));
          const label = document.createElement("label");
          label.className = "ws-category-label";
          label.htmlFor = `budget-amount-${category.id}`;
          label.textContent = categoryName(category);
          const field = document.createElement("div");
          field.className = "ws-money-field";
          const input = document.createElement("input");
          input.type = "text";
          input.required = true;
          input.name = `amount-${category.id}`;
          input.inputMode = "numeric";
          input.autocomplete = "off";
          input.id = label.htmlFor;
          input.dataset.categoryAmount = "";
          input.value = amountText(category.amount);
          input.setAttribute("aria-describedby", "budget-error");
          const suffix = document.createElement("span");
          suffix.className = "ws-currency-suffix";
          suffix.textContent = "VND";
          suffix.setAttribute("aria-hidden", "true");
          field.append(input, suffix);
          row.append(icon, label, field);
          if (!defaultCategories.has(category.id)) {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "ws-remove-category";
            remove.dataset.removeCategory = category.id;
            remove.setAttribute("aria-label", `${translate("budget_remove")}: ${category.name}`);
            remove.textContent = "×";
            row.append(remove);
          }
          fragment.append(row);
        }
        rowsElement.replaceChildren(fragment);
      }
    }

    function setInvalid(input, invalid) {
      input.setAttribute("aria-invalid", String(invalid));
      input.closest(".ws-money-field")?.classList.toggle("is-invalid", invalid);
    }

    function readForm() {
      const available = parseAmount(availableInput.value);
      setInvalid(availableInput, available === null);
      const categories = [];
      const groupTotals = { p0: 0, p1: 0, p2: 0 };
      const invalidGroups = new Set();
      let firstInvalid = available === null ? availableInput : null;
      for (const category of plan.categories) {
        const row = [...groupsElement.querySelectorAll("[data-category-id]")].find((node) => node.dataset.categoryId === category.id);
        const input = row?.querySelector("[data-category-amount]");
        const amount = input ? parseAmount(input.value) : null;
        if (input) setInvalid(input, amount === null);
        if (amount === null) {
          invalidGroups.add(category.group);
          if (!firstInvalid) firstInvalid = input;
        } else {
          groupTotals[category.group] += amount;
        }
        categories.push({ ...category, amount });
      }
      const planned = invalidGroups.size ? null : GROUPS.reduce((sum, group) => sum + groupTotals[group], 0);
      const unallocated = available === null || planned === null ? null : available - planned;
      const error = firstInvalid || invalidGroups.size ? "budget_error_amount" :
        unallocated < 0 ? "budget_error_total" : "";
      return { available, categories, groupTotals, invalidGroups, planned, unallocated, firstInvalid, error };
    }

    function showError(message) {
      errorElement.textContent = message;
      errorElement.hidden = !message;
    }

    function showStatus(key) {
      if (!statusElement) return;
      statusElement.textContent = translate(key);
      statusElement.hidden = false;
      statusElement.dataset.state = key === "budget_success" ? "saved" : "unsaved";
    }

    function updateSummary() {
      const state = readForm();
      const values = {
        available: state.available,
        ...Object.fromEntries(GROUPS.map((group) => [group, state.invalidGroups.has(group) ? null : state.groupTotals[group]])),
        planned: state.planned,
        unallocated: state.unallocated
      };
      for (const element of document.querySelectorAll("[data-summary]")) {
        const key = element.dataset.summary;
        if (Object.hasOwn(values, key)) element.textContent = money(values[key]);
      }
      for (const element of document.querySelectorAll("[data-share]")) {
        const amount = values[element.dataset.share];
        element.textContent = state.available !== null && amount !== null && amount !== undefined ?
          percentFormat.format(amount / state.available) : "—";
      }
      const chartValid = state.available !== null && state.planned !== null;
      const denominator = chartValid ? Math.max(state.available, state.planned) : 1;
      for (const element of document.querySelectorAll("[data-allocation]")) {
        const key = element.dataset.allocation;
        const amount = chartValid ? Math.max(0, values[key] || 0) : 0;
        element.style.width = `${Math.max(0, Math.min(100, amount / denominator * 100))}%`;
      }
      const overallocated = state.unallocated !== null && state.unallocated < 0;
      document.querySelector(".ws-unallocated")?.classList.toggle("is-negative", overallocated);
      const allocationHelp = document.querySelector(".ws-unallocated p");
      if (allocationHelp) allocationHelp.textContent = translate(overallocated ? "budget_error_total" : "budget_buffer_help");
      saveButton.disabled = Boolean(state.error);
      showError(state.error ? translate(state.error) : persistentError);
      return state;
    }

    function markUnsaved() {
      persistentError = "";
      showStatus("budget_unsaved");
      updateSummary();
    }

    availableInput.value = amountText(plan.available);
    renderRows();
    updateSummary();

    form.addEventListener("input", (event) => {
      if (event.target === availableInput || event.target.matches("[data-category-amount]")) markUnsaved();
    });
    form.addEventListener("focusout", (event) => {
      if (event.target !== availableInput && !event.target.matches("[data-category-amount]")) return;
      const amount = parseAmount(event.target.value);
      if (amount !== null) event.target.value = amountText(amount);
    });
    groupsElement.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-category]");
      if (!button) return;
      const id = button.dataset.removeCategory;
      if (defaultCategories.has(id)) return;
      // Keep all current input strings intact when another category is removed.
      plan.categories = plan.categories.filter((category) => category.id !== id);
      button.closest(".ws-budget-row")?.remove();
      markUnsaved();
      addButton?.focus();
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const state = updateSummary();
      if (state.error) {
        state.firstInvalid?.focus();
        return;
      }
      const validated = validatePlan({ available: state.available, categories: state.categories });
      if (!validated) {
        showError(translate("budget_error_amount"));
        return;
      }
      // Refresh before saving so another tab's month is not silently overwritten.
      const latest = readStorage();
      if (latest.error === "budget_error_storage") {
        persistentError = translate("budget_error_storage");
        showError(persistentError);
        if (statusElement) statusElement.hidden = true;
        return;
      }
      storageState = latest.state || { version: 1, plans: {} };
      if (!Object.hasOwn(storageState.plans, month) && Object.keys(storageState.plans).length >= MAX_MONTHS) {
        showError(translate("budget_error_storage"));
        if (statusElement) statusElement.hidden = true;
        return;
      }
      storageState.plans[month] = validated;
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(storageState));
      } catch (_) {
        persistentError = translate("budget_error_storage");
        showError(persistentError);
        if (statusElement) statusElement.hidden = true;
        return;
      }
      plan = clonePlan(validated);
      persistentError = "";
      updateSummary();
      showStatus("budget_success");
    });

    const dialog = document.getElementById("category-dialog");
    const categoryForm = document.getElementById("category-form");
    const nameInput = document.getElementById("category-name");
    const groupInput = document.getElementById("category-group");
    const amountInput = document.getElementById("category-amount");
    const categoryError = document.getElementById("category-error");
    if (dialog && categoryForm && nameInput && groupInput && amountInput && categoryError && addButton) {
      const dialogError = (key = "") => {
        categoryError.textContent = key ? translate(key) : "";
        categoryError.hidden = !key;
      };
      addButton.addEventListener("click", () => {
        categoryForm.reset();
        groupInput.value = "p2";
        nameInput.setAttribute("aria-invalid", "false");
        amountInput.setAttribute("aria-invalid", "false");
        dialogError();
        dialog.showModal();
        nameInput.focus();
      });
      dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
      });
      dialog.addEventListener("close", () => addButton.focus());
      amountInput.addEventListener("blur", () => {
        const amount = parseAmount(amountInput.value);
        if (amount !== null) amountInput.value = amountText(amount);
      });
      categoryForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const name = nameInput.value.trim();
        const duplicate = plan.categories.some((category) => categoryName(category).toLocaleLowerCase(locale) === name.toLocaleLowerCase(locale));
        const atLimit = plan.categories.length >= MAX_CATEGORIES;
        const badName = !validName(name) || duplicate || !GROUPS.includes(groupInput.value);
        const amount = parseAmount(amountInput.value);
        nameInput.setAttribute("aria-invalid", String(badName));
        amountInput.setAttribute("aria-invalid", String(amount === null));
        if (atLimit || badName || amount === null) {
          dialogError(atLimit ? "budget_error_limit" : badName ? "budget_error_name" : "budget_error_amount");
          (atLimit || badName ? nameInput : amountInput).focus();
          return;
        }
        let id;
        do {
          const suffix = typeof window.crypto?.randomUUID === "function" ? window.crypto.randomUUID() :
            `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
          id = `custom_${suffix}`;
        } while (plan.categories.some((category) => category.id === id));
        // Capture existing strings before rebuilding; invalid amounts remain editable.
        const drafts = new Map([...groupsElement.querySelectorAll(".ws-budget-row")].map((row) =>
          [row.dataset.categoryId, row.querySelector("[data-category-amount]")?.value]));
        plan.categories.push({ id, name, group: groupInput.value, amount });
        renderRows();
        for (const row of groupsElement.querySelectorAll(".ws-budget-row")) {
          const draft = drafts.get(row.dataset.categoryId);
          if (draft !== undefined) row.querySelector("[data-category-amount]").value = draft;
        }
        markUnsaved();
        dialog.close();
      });
    }
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isAmount(value) {
    return Number.isSafeInteger(value) && value > 0 && value <= MAX_AMOUNT;
  }

  function validName(value) {
    return typeof value === "string" && value.trim().length > 0 && value.trim().length <= 60 &&
      !/[\u0000-\u001f\u007f]/.test(value);
  }

  function clonePlan(plan) {
    return { available: plan.available, categories: plan.categories.map((category) => ({ ...category })) };
  }

  function initializeSidebar() {
    const sidebar = document.getElementById("workspace-sidebar");
    const toggles = [...document.querySelectorAll("[data-sidebar-toggle]")];
    const overlay = document.querySelector(".ws-sidebar-overlay");
    if (!sidebar || !toggles.length) return;
    const mobile = window.matchMedia("(max-width: 1023px)");
    const main = document.querySelector(".ws-main");
    let open = false;
    let returnFocus = null;
    const focusable = () => [...sidebar.querySelectorAll("a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])")]
      .filter((element) => !element.closest("[hidden]") && element.getAttribute("aria-disabled") !== "true");

    function setOpen(next, restoreFocus = true) {
      open = Boolean(next && mobile.matches);
      document.body.classList.toggle("ws-sidebar-open", open);
      toggles.forEach((toggle) => toggle.setAttribute("aria-expanded", String(open)));
      sidebar.inert = mobile.matches && !open;
      if (mobile.matches && !open) sidebar.setAttribute("aria-hidden", "true");
      else sidebar.removeAttribute("aria-hidden");
      if (main) main.inert = open;
      if (overlay) {
        overlay.hidden = !open;
        overlay.setAttribute("aria-hidden", String(!open));
      }
      if (open) {
        returnFocus = document.activeElement;
        queueMicrotask(() => (focusable()[0] || sidebar).focus());
      } else if (restoreFocus && returnFocus?.isConnected) {
        returnFocus.focus();
        returnFocus = null;
      }
    }

    toggles.forEach((toggle) => toggle.addEventListener("click", () => setOpen(!open)));
    document.querySelectorAll("[data-sidebar-close]").forEach((button) => button.addEventListener("click", () => setOpen(false)));
    overlay?.addEventListener("click", () => setOpen(false));
    sidebar.querySelectorAll("a[href]").forEach((link) => link.addEventListener("click", () => setOpen(false, false)));
    document.addEventListener("keydown", (event) => {
      if (!open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
      } else if (event.key === "Tab") {
        const items = focusable();
        if (!items.length) {
          event.preventDefault();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
    mobile.addEventListener("change", () => setOpen(false, false));
    setOpen(false, false);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
