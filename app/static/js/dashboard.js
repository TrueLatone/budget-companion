// Enhance Thien's history dialog using server-rendered, owned records only.
// Native links remain usable without JavaScript. No financial writes/arithmetic.
(() => {
  "use strict";
  const link = document.getElementById("db-view-all");
  const dialog = document.getElementById("db-history-dialog");
  if (!link || !dialog || typeof dialog.showModal !== "function") return;
  link.addEventListener("click", (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    dialog.showModal();
  });
  dialog.querySelectorAll("[data-db-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => link.focus());
})();
