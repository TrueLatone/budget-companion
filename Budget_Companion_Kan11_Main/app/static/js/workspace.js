// Sidebar interaction adapted from Thien UI 762ae29; no financial browser state.
(() => {
  "use strict";
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


  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeSidebar);
  else initializeSidebar();
})();
