/* The public homepage: theme switch, sticky header border, reveal on scroll and counting numbers.
   Everything on the page works and reads correctly without this script. */
(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Light or dark, remembered with the app's own setting.
  document.querySelector("[data-lp-theme]")?.addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("cae-theme", root.dataset.theme); } catch (e) { /* storage unavailable */ }
  });

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

  // Pricing: the monthly cost for a team of the size chosen, worked out from the price in the page.
  const card = document.querySelector("[data-lp-price]");
  const calc = card?.querySelector(".lp-calc");
  if (calc) {
    const seat = Number(card.dataset.seat), slider = calc.querySelector("input"), out = calc.querySelector("output"),
      total = calc.querySelector("[data-lp-total]");
    const pounds = pence => "£" + (pence / 100).toLocaleString("en-GB", { minimumFractionDigits: pence % 100 ? 2 : 0, maximumFractionDigits: 2 });
    const update = () => {
      const n = Number(slider.value);
      out.textContent = n === 1 ? "1 person" : `${n} people`;
      total.textContent = pounds(seat * n);
    };
    slider.addEventListener("input", update);
    calc.hidden = false;
    update();
  }

  // The launch film plays in a pop-up player; closing it (button, Escape or a click outside) pauses it.
  const filmLink = document.querySelector("[data-lp-film]");
  const film = document.querySelector("[data-lp-film-dialog]");
  if (filmLink && film?.showModal) {
    const video = film.querySelector("video");
    filmLink.addEventListener("click", event => {
      event.preventDefault();
      film.showModal();
      video.play().catch(() => { /* the visitor can press play */ });
    });
    const shut = () => { video.pause(); if (film.open) film.close(); };
    film.querySelector("[data-lp-film-close]").addEventListener("click", shut);
    film.addEventListener("click", event => { if (event.target === film) shut(); });
    film.addEventListener("cancel", () => video.pause());   // Escape
    film.addEventListener("close", () => video.pause());
  }

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
