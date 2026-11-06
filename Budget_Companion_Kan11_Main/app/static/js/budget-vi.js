"use strict";
(() => {
  const error = document.getElementById('budget-form-error');
  if (error) error.focus({preventScroll:true});
  const form = document.getElementById('bv-generate-form');
  if (!form) return;
  const sample = document.getElementById('bv-sample-button');
  sample?.addEventListener('click', () => {
    const defaults = {rent: '1500000', electricity: '200000', water: '100000', internet: '100000'};
    const due = {rent: '5', electricity: '12', water: '12', internet: '1'};
    for (const [key, value] of Object.entries(defaults)) {
      const row = form.querySelector(`[data-suggestion="${key}"]`);
      if (!row) continue;
      const toggle = row.querySelector('input[type="checkbox"][name="suggestion"]');
      if (toggle && !toggle.checked) continue;
      const amount = row.querySelector(`[name="${key}_estimated_amount"]`);
      const day = row.querySelector(`[name="${key}_due_day"]`);
      if (amount && !amount.value.trim()) amount.value = value;
      if (day && !day.value.trim()) day.value = due[key];
    }
  });
  // An added expense stays in this same unsaved form until Generate.
  // Do not POST/redirect on add; browser state survives other field edits.
  const rows = document.getElementById('bv-custom-rows');
  const add = document.getElementById('bv-add-custom');
  const template = document.getElementById('bv-custom-template');
  let nextIndex = 0;
  const updateRow = (row) => {
    const priority = row.querySelector('[name$="_priority"]').value;
    const frequency = row.querySelector('[name$="_allocation_frequency"]').value;
    const minimum = row.querySelector('[name$="_minimum_amount"]');
    const due = row.querySelector('[name$="_due_day"]');
    const estimate = row.querySelector('[name$="_estimated_amount"]');
    minimum.closest('[data-custom-minimum]').hidden = priority !== 'P1';
    due.closest('[data-custom-due]').hidden = frequency !== 'MONTHLY';
    estimate.required = priority === 'P0';
  };
  const attachRow = (row) => {
    nextIndex = Math.max(nextIndex, Number(row.dataset.customId || 0) + 1);
    row.querySelector('[data-remove-custom]').addEventListener('click', () => row.remove());
    row.querySelector('[name$="_priority"]').addEventListener('change', () => {
      if (row.querySelector('[name$="_priority"]').value !== 'P1')
        row.querySelector('[name$="_minimum_amount"]').value = '';
      updateRow(row);
    });
    row.querySelector('[name$="_allocation_frequency"]').addEventListener('change', () => {
      if (row.querySelector('[name$="_allocation_frequency"]').value !== 'MONTHLY')
        row.querySelector('[name$="_due_day"]').value = '';
      updateRow(row);
    });
    updateRow(row);
  };
  rows?.querySelectorAll('[data-custom-id]').forEach(attachRow);
  add?.addEventListener('click', () => {
    if (rows.querySelectorAll('[data-custom-id]').length >= 40) return;
    const index = String(nextIndex++);
    const holder = document.createElement('div');
    // Only our static template content is interpolated, never user input.
    holder.innerHTML = template.innerHTML.replaceAll('__INDEX__', index);
    const row = holder.firstElementChild;
    rows.appendChild(row);
    attachRow(row);
    document.dispatchEvent(new CustomEvent('budget:extra-added', {detail:{row}}));
    row.querySelector('[name$="_expense_name"]').focus();
  });
  for (const item of form.querySelectorAll('[data-suggestion]')) {
    const check = item.querySelector('input[type="checkbox"][name="suggestion"]');
    if (!check) continue;
    const sync = () => {
      for (const inp of item.querySelectorAll('input:not([type="checkbox"])')) inp.disabled = !check.checked;
      item.classList.toggle('bv-dimmed',!check.checked);
    };
    check.addEventListener('change',sync);
    sync();
  }
})();
