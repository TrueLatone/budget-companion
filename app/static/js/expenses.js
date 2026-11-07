(function () {
  'use strict';

  var root = document.querySelector('[data-expense-root]');
  if (!root) {
    return;
  }

  var scrollKey = 'expense-scroll:' + window.location.pathname;
  var focusKey = 'expense-focus';
  var scrollTimer = null;
  var scrollSaveEnabled = false;
  var SCROLL_FRESH_MS = 30 * 60 * 1000;

  if ('scrollRestoration' in window.history) {
    window.history.scrollRestoration = 'manual';
  }

  function timestamp() {
    return Date.now ? Date.now() : new Date().getTime();
  }

  function saveScroll() {
    if (!scrollSaveEnabled) {
      return;
    }
    try {
      window.sessionStorage.setItem(scrollKey, JSON.stringify({
        top: window.scrollY || window.pageYOffset || 0,
        at: timestamp()
      }));
    } catch (error) {
      /* Storage may be unavailable in private mode; navigation still works. */
    }
  }

  function savedScrollTop() {
    var raw;
    try {
      raw = window.sessionStorage.getItem(scrollKey);
    } catch (error) {
      return null;
    }
    if (raw === null) {
      return null;
    }
    var top;
    var at = null;
    try {
      var parsed = JSON.parse(raw);
      top = parsed.top;
      at = parsed.at;
    } catch (error) {
      top = parseInt(raw, 10);
    }
    if (!Number.isFinite(top) || top <= 0) {
      return null;
    }
    if (Number.isFinite(at) && timestamp() - at > SCROLL_FRESH_MS) {
      return null;
    }
    return top;
  }

  function restoreScroll() {
    var top = savedScrollTop();
    if (top === null) {
      return;
    }
    window.requestAnimationFrame(function () {
      window.scrollTo(0, top);
      window.requestAnimationFrame(function () {
        window.scrollTo(0, top);
      });
    });
  }

  function takeFocusSelector() {
    var selector;
    try {
      selector = window.sessionStorage.getItem(focusKey);
      window.sessionStorage.removeItem(focusKey);
    } catch (error) {
      return null;
    }
    return selector;
  }

  function restoreFocus() {
    var selector = takeFocusSelector();
    if (!selector) {
      return false;
    }
    var target = document.querySelector(selector);
    if (!target) {
      return false;
    }
    window.requestAnimationFrame(function () {
      target.scrollIntoView({ block: 'center', behavior: 'auto' });
      target.classList.add('bc-focus-pulse');
      window.setTimeout(function () {
        target.classList.remove('bc-focus-pulse');
      }, 2200);
    });
    return true;
  }

  window.addEventListener('scroll', function () {
    window.clearTimeout(scrollTimer);
    scrollTimer = window.setTimeout(saveScroll, 120);
  }, { passive: true });
  window.addEventListener('pagehide', saveScroll);
  window.addEventListener('beforeunload', saveScroll);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      saveScroll();
    }
  });

  document.addEventListener('click', function (event) {
    var source = event.target.closest('[data-focus-target]');
    if (source) {
      try {
        window.sessionStorage.setItem(focusKey, source.getAttribute('data-focus-target'));
      } catch (error) {
        /* Ignore unavailable storage. */
      }
    }
    var link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download')) {
      return;
    }
    var href = link.getAttribute('href');
    if (!href || href.charAt(0) === '#' || link.origin !== window.location.origin) {
      return;
    }
    saveScroll();
  });

  document.addEventListener('submit', saveScroll, true);

  document.querySelectorAll('details[data-expense-details]').forEach(function (details) {
    var key = 'expense-details:' + details.getAttribute('data-expense-details');
    try {
      var saved = window.sessionStorage.getItem(key);
      if (saved === 'open') {
        details.open = true;
      } else if (saved === 'closed') {
        details.open = false;
      }
    } catch (error) {
      /* Ignore unavailable storage. */
    }
    details.addEventListener('toggle', function () {
      try {
        window.sessionStorage.setItem(key, details.open ? 'open' : 'closed');
      } catch (error) {
        /* Ignore unavailable storage. */
      }
    });
  });

  document.querySelectorAll('form[data-checkin-form]').forEach(function (form) {
    var amount = form.querySelector('[name="amount"]');
    var radios = form.querySelectorAll('[name="action"]');
    if (!amount || !radios.length) {
      return;
    }
    function syncAction() {
      var selected = form.querySelector('[name="action"]:checked');
      var isActual = Boolean(selected && selected.value === 'actual');
      amount.disabled = !isActual;
      amount.required = isActual;
    }
    radios.forEach(function (radio) {
      radio.addEventListener('change', syncAction);
    });
    syncAction();
  });

  document.querySelectorAll('form[data-no-double-submit]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      var message = form.getAttribute('data-confirm');
      if (message && !window.confirm(message)) {
        event.preventDefault();
        return;
      }
      saveScroll();
      var button = event.submitter || form.querySelector('[type="submit"]');
      if (!button && form.id) {
        button = document.querySelector('[type="submit"][form="' + form.id + '"]');
      }
      if (!button) {
        return;
      }
      button.disabled = true;
      button.setAttribute('aria-disabled', 'true');
      if (!button.dataset.originalLabel) {
        button.dataset.originalLabel = button.textContent;
      }
      button.textContent = 'Processing…';
    });
  });

  var focusRestored = restoreFocus();
  if (!focusRestored) {
    restoreScroll();
  }
  window.setTimeout(function () {
    scrollSaveEnabled = true;
  }, 350);
})();
