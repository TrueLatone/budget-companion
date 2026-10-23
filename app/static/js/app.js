// Shared browser behavior (owned by UI/Dashboard module).
// No global fetch/auth handling until API contract is agreed.

document.addEventListener("DOMContentLoaded", () => {
  if (!document.body.classList.contains("bc-home")) return;

  const navigation = document.getElementById("mainNav");
  const links = document.querySelectorAll(".bc-nav-link");

  links.forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin || destination.pathname !== window.location.pathname) return;

      links.forEach((item) => {
        item.classList.remove("is-active");
        item.removeAttribute("aria-current");
      });
      link.classList.add("is-active");
      link.setAttribute("aria-current", destination.hash ? "location" : "page");

      if (navigation?.classList.contains("show") && window.bootstrap?.Collapse) {
        const target = destination.hash ? document.getElementById(destination.hash.slice(1)) : null;

        if (target) {
          // Wait for the header to shrink before measuring the anchor position.
          event.preventDefault();
          navigation.addEventListener("hidden.bs.collapse", () => {
            if (window.location.href !== destination.href) {
              window.history.pushState(null, "", destination.href);
            }
            target.scrollIntoView({
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
              block: "start"
            });
          }, { once: true });
        }

        window.bootstrap.Collapse.getOrCreateInstance(navigation, { toggle: false }).hide();
      }
    });
  });
});
