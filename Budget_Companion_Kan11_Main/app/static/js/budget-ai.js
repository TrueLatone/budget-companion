"use strict";
// Optional guidance, never saves data or changes an expense automatically.
(() => {
  function init(widget) {
    if (widget.dataset.aiReady === '1') return;
    const row = widget.closest('[data-custom-id]');
    const form = widget.closest('form');
    const context = row || form;
    const name = row ? context.querySelector('[name$="_expense_name"]') : context?.querySelector('[name="expense_name"]');
    const priority = row ? context.querySelector('[name$="_priority"]') : context?.querySelector('[name="priority"]');
    const suggest = widget.querySelector('[data-budget-ai-suggest]');
    const apply = widget.querySelector('[data-budget-ai-apply]');
    const result = widget.querySelector('[data-budget-ai-result]');
    if (!form || !name || !priority || !suggest || !apply || !result) return;
    widget.dataset.aiReady = '1';
    let last = null;
    suggest.addEventListener('click', async () => {
      last = null;
      apply.hidden = true;
      if (!name.value.trim()) { result.textContent = widget.dataset.invalid; return; }
      result.textContent = widget.dataset.wait;
      suggest.disabled = true;
      const payload = new FormData();
      payload.append('expense_name', name.value);
      payload.append('csrf_token', form.querySelector('[name="csrf_token"]')?.value || '');
      try {
        const response = await fetch(widget.dataset.url, {method:'POST',credentials:'same-origin',body:payload,headers:{Accept:'application/json'}});
        const data = await response.json();
        if (!response.ok || !['P1','P2'].includes(data.priority)) throw Error('Invalid suggestion');
        last = {priority:data.priority, name:name.value};
        result.textContent = `${data.priority === 'P1' ? 'Thiết yếu' : 'Linh hoạt'} · ${data.reason} (${data.source === 'Gemini' ? 'AI' : 'Gợi ý tự động'})`;
        apply.hidden = false;
      } catch (_) { result.textContent = widget.dataset.unavailable; }
      finally { suggest.disabled = false; }
    });
    apply.addEventListener('click', () => {
      if (last && last.name === name.value) {
        priority.value = last.priority;
        priority.dispatchEvent(new Event('change',{bubbles:true}));
      }
      apply.hidden = true;
    });
    name.addEventListener('input', () => {last=null;apply.hidden=true;});
  }
  document.querySelectorAll('[data-budget-ai-widget]').forEach(init);
  document.addEventListener('budget:extra-added', event => {
    event.detail?.row?.querySelectorAll('[data-budget-ai-widget]').forEach(init);
  });
})();
