/* The public homepage: theme switch, mobile menu, sticky header border, reveal on scroll and counting numbers.
   Everything on the page works and reads correctly without this script. */
(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Light or dark, remembered with the app's own setting.
  document.querySelector("[data-lp-theme]")?.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    try { localStorage.setItem("cae-theme", root.dataset.theme); } catch (e) { /* storage unavailable */ }
  });

  // Mobile menu.
  const menuBtn = document.querySelector("[data-lp-menu]");
  const nav = document.getElementById("lp-nav");
  const setMenu = open => { nav.classList.toggle("is-open", open); menuBtn.setAttribute("aria-expanded", String(open)); };
  menuBtn?.addEventListener("click", () => setMenu(!nav.classList.contains("is-open")));
  nav?.addEventListener("click", e => { if (e.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && nav?.classList.contains("is-open")) { setMenu(false); menuBtn.focus(); } });

  // A border under the header once the page has scrolled.
  const header = document.querySelector("[data-lp-header]");
  const onScroll = () => header?.classList.toggle("is-scrolled", scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Numbers count up from zero to the figure already written in the page.
  const format = (el, value) => {
    const decimals = Number(el.dataset.decimals || 0);
    const text = value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    el.textContent = (el.dataset.prefix || "") + text + (el.dataset.suffix || "");
  };
  const countUp = el => {
    const target = Number(el.dataset.count);
    if (still || !Number.isFinite(target)) return;
    const start = performance.now(), length = 1400;
    const step = now => {
      const t = Math.min(1, (now - start) / length);
      format(el, target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(step); else format(el, target);
    };
    requestAnimationFrame(step);
  };

  const show = el => {
    el.classList.add("is-in");
    el.querySelectorAll("[data-count]").forEach(countUp);
  };
  const targets = document.querySelectorAll(".lp-reveal");
  if (!("IntersectionObserver" in window) || still) {
    targets.forEach(el => el.classList.add("is-in"));
    return;
  }
  const seen = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { show(entry.target); seen.unobserve(entry.target); }
  }), { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
  targets.forEach(el => seen.observe(el));
})();
