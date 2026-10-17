/* CAE CRM interactions. Every page still works without this file. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const csrf = $('meta[name="csrf-token"]').content;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
  const gbp2 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });

  async function post(url, data) {
    const body = new URLSearchParams({ csrf, ...data });
    const res = await fetch(url, { method: "POST", body, headers: { "X-Requested-With": "fetch", "X-CSRF-Token": csrf } });
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
  }

  /* Toasts ---------------------------------------------------------------- */
  const toastBox = $(".toasts");
  function dismiss(el) {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 260);
  }
  function toast(message, kind = "ok") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.setAttribute("role", "status");
    el.textContent = message;
    toastBox.append(el);
    setTimeout(() => dismiss(el), 5000);
  }
  $$(".toast").forEach(el => setTimeout(() => dismiss(el), 6000));

  /* Theme ----------------------------------------------------------------- */
  $("#theme-toggle")?.addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("cae-theme", root.dataset.theme); } catch (e) { /* storage unavailable */ }
    document.dispatchEvent(new Event("themechange"));
  });

  /* Mobile sidebar -------------------------------------------------------- */
  $$("[data-open-sidebar]").forEach(b => b.addEventListener("click", () => document.body.classList.add("nav-open")));
  $$("[data-close-sidebar]").forEach(b => b.addEventListener("click", () => document.body.classList.remove("nav-open")));

  /* Menus: close <details> menus on outside click or Escape ---------------- */
  document.addEventListener("click", e => {
    $$("details.new-menu[open], details.card-menu[open]").forEach(d => { if (!d.contains(e.target)) d.open = false; });
  });

  /* Dialogs --------------------------------------------------------------- */
  function openDialog(id) {
    const dlg = document.getElementById(id);
    if (!dlg) return;
    $$("details[open]").forEach(d => { d.open = false; });
    dlg.showModal();
    (dlg.querySelector("[aria-invalid=true]") || dlg.querySelector("input:not([type=hidden]), select"))?.focus();
  }
  document.addEventListener("click", e => {
    const opener = e.target.closest("[data-open]");
    if (opener) { e.preventDefault(); openDialog(opener.dataset.open); }
    const closer = e.target.closest("[data-close]");
    if (closer) closer.closest("dialog")?.close();
  });
  $$("dialog").forEach(dlg => dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); }));
  $$("dialog[data-autoopen]").forEach(dlg => openDialog(dlg.id));
  $$("form[data-confirm]").forEach(f => f.addEventListener("submit", e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
  $$("[data-print]").forEach(b => b.addEventListener("click", () => print()));

  // Live VAT preview in the invoice dialog.
  const netInput = $("[data-net]");
  if (netInput) {
    const form = netInput.form;
    const preview = $("[data-invoice-preview]", form);
    const update = () => {
      const net = parseFloat(netInput.value.replace(/[£,\s]/g, ""));
      const rate = parseInt(form.vat_rate.value, 10);
      preview.textContent = net > 0
        ? `${gbp2.format(net)} plus ${gbp2.format(net * rate / 100)} VAT makes ${gbp2.format(net * (1 + rate / 100))}. Payment due in 30 days.`
        : "Payment due in 30 days.";
    };
    netInput.addEventListener("input", update);
    form.vat_rate.addEventListener("change", update);
  }

  /* Command palette ------------------------------------------------------- */
  const palette = $("#palette");
  const pInput = palette && $("input", palette);
  const pList = $("#palette-results");
  const jumps = [
    { kind: "Go to", title: "Overview", url: "/" },
    { kind: "Go to", title: "Pipeline", url: "/pipeline" },
    { kind: "Go to", title: "Customers", url: "/customers" },
    { kind: "Go to", title: "Schedule", url: "/schedule" },
    { kind: "Go to", title: "Finance", url: "/finance" },
    { kind: "Go to", title: "Growth", url: "/growth" },
    { kind: "Go to", title: "Projects", url: "/projects" },
    { kind: "Create", title: "New deal", dialog: "dlg-deal" },
    { kind: "Create", title: "New customer", dialog: "dlg-customer" },
    { kind: "Create", title: "Schedule an activity", dialog: "dlg-activity" },
    { kind: "Create", title: "Raise an invoice", dialog: "dlg-invoice" },
  ];
  let items = [], active = 0, searchTimer;

  function renderPalette(list) {
    items = list;
    active = 0;
    pList.replaceChildren(...(list.length ? list : [null]).map((item, i) => {
      const li = document.createElement("li");
      if (!item) {
        li.className = "none";
        li.textContent = "No matches. Try a company name, town or postcode.";
        return li;
      }
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === 0);
      li.innerHTML = '<span class="kind"></span><span class="title"></span><span class="detail"></span>';
      li.children[0].textContent = item.kind;
      li.children[1].textContent = item.title;
      li.children[2].textContent = item.detail || "";
      li.addEventListener("mousemove", () => select(i));
      li.addEventListener("click", () => choose(item));
      return li;
    }));
  }
  function select(i) {
    if (!items.length) return;
    active = (i + items.length) % items.length;
    $$("li", pList).forEach((li, j) => li.setAttribute("aria-selected", j === active));
    pList.children[active].scrollIntoView({ block: "nearest" });
  }
  function choose(item) {
    if (!item) return;
    palette.close();
    if (item.dialog) openDialog(item.dialog);
    else location.href = item.url;
  }
  function openPalette() {
    if (!palette || palette.open) return;
    pInput.value = "";
    renderPalette(jumps);
    palette.showModal();
    pInput.focus();
  }
  if (palette) {
    $$("[data-palette]").forEach(b => b.addEventListener("click", openPalette));
    document.addEventListener("keydown", e => {
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing && !document.querySelector("dialog[open]"))) {
        e.preventDefault();
        openPalette();
      }
    });
    pInput.addEventListener("keydown", e => {
      if (e.key === "ArrowDown") { e.preventDefault(); select(active + 1); }
      if (e.key === "ArrowUp") { e.preventDefault(); select(active - 1); }
      if (e.key === "Enter") { e.preventDefault(); choose(items[active]); }
    });
    pInput.addEventListener("input", () => {
      const q = pInput.value.trim().toLowerCase();
      const local = jumps.filter(j => j.title.toLowerCase().includes(q));
      clearTimeout(searchTimer);
      if (q.length < 2) { renderPalette(q ? local : jumps); return; }
      searchTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
          renderPalette([...(await res.json()), ...local]);
        } catch (e) { renderPalette(local); }
      }, 140);
    });
  }

  /* Month track: one load-time moment ------------------------------------ */
  const track = $(".track");
  if (track) {
    const counter = $("[data-countup]", track);
    const target = Number(counter?.dataset.countup || 0);
    requestAnimationFrame(() => requestAnimationFrame(() => track.classList.add("is-ready")));
    if (counter && !reduceMotion) {
      const start = performance.now(), dur = 1100;
      const step = now => {
        const p = Math.min(1, (now - start) / dur);
        counter.textContent = gbp.format(Math.round(target * (1 - Math.pow(1 - p, 3))));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
  }

  /* Revenue chart -------------------------------------------------------- */
  const chartEl = $("#revenue-chart");
  const chartData = $("#revenue-data");
  if (chartEl && chartData) {
    const { series, target } = JSON.parse(chartData.textContent);
    const summary = $("[data-chart-summary]");
    const NS = "http://www.w3.org/2000/svg";
    let range = 12;

    const el = (name, attrs) => {
      const node = document.createElementNS(NS, name);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
      return node;
    };

    function draw() {
      const data = series.slice(-range);
      const W = chartEl.clientWidth || 800, H = chartEl.clientHeight || 290;
      const pad = { l: 52, r: 12, t: 18, b: 30 };
      const step = 50000;
      const yMax = Math.max(step, Math.ceil(Math.max(target, ...data.map(d => d.value)) * 1.12 / step) * step);
      const y = v => pad.t + (H - pad.t - pad.b) * (1 - v / yMax);
      const slot = (W - pad.l - pad.r) / data.length;
      const barW = Math.min(46, slot * 0.58);
      const cx = i => pad.l + slot * (i + 0.5);

      const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Monthly won revenue against target" });
      // Hatching marks the current month, which is still in progress.
      const defs = el("defs", {});
      const hatch = el("pattern", { id: "partial-hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
      hatch.append(el("rect", { width: 6, height: 6, fill: "var(--chart-fill)" }), el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "var(--chart-hit)", "stroke-width": 2, opacity: 0.5 }));
      defs.append(hatch);
      svg.append(defs);

      for (let v = 0; v <= yMax; v += step) {
        svg.append(el("line", { class: "grid", x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
        const t = el("text", { class: "axis", x: pad.l - 10, y: y(v) + 4, "text-anchor": "end" });
        t.textContent = v === 0 ? "£0" : `£${v / 1000}K`;
        svg.append(t);
      }

      const bars = data.map((d, i) => {
        const x0 = cx(i) - barW / 2, top = y(d.value), base = y(0);
        const h = Math.max(0, base - top), r = Math.min(7, barW / 2, h);
        // Rounded top corners, square base.
        const path = h > 0
          ? `M${x0},${base} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + barW - r} Q${x0 + barW},${top} ${x0 + barW},${top + r} V${base} Z`
          : `M${x0},${base} H${x0 + barW}`;
        const bar = el("path", { class: `bar${d.value >= target ? " hit" : ""}${d.partial ? " partial" : ""}`, d: path });
        svg.append(bar);
        const label = el("text", { class: "axis", x: cx(i), y: H - 8, "text-anchor": "middle" });
        label.textContent = d.label;
        if (range <= 6 || slot > 44 || i % 2 === (data.length - 1) % 2) svg.append(label);
        return bar;
      });

      svg.append(el("line", { class: "target", x1: pad.l, x2: W - pad.r, y1: y(target), y2: y(target) }));
      const tl = el("text", { class: "target-label", x: W - pad.r, y: y(target) - 7, "text-anchor": "end" });
      tl.textContent = `Target ${gbp.format(target)}`;
      svg.append(tl);

      const tip = document.createElement("div");
      tip.className = "chart-tip";
      chartEl.replaceChildren(svg, tip);

      chartEl.onpointermove = e => {
        const box = chartEl.getBoundingClientRect();
        const px = (e.clientX - box.left) * (W / box.width);
        const i = Math.max(0, Math.min(data.length - 1, Math.floor((px - pad.l) / slot)));
        const d = data[i];
        bars.forEach((bar, j) => bar.classList.toggle("active", j === i));
        const diff = d.value - target;
        tip.innerHTML = `<span></span><b></b><span></span>`;
        tip.children[0].textContent = d.full + (d.partial ? " so far" : "");
        tip.children[1].textContent = gbp.format(d.value);
        tip.children[2].textContent = d.partial ? "Month in progress" : `${gbp.format(Math.abs(diff))} ${diff >= 0 ? "over" : "under"} target`;
        tip.style.left = `${cx(i) / W * 100}%`;
        tip.style.top = `${Math.min(y(d.value), y(target)) / H * 100}%`;
        chartEl.classList.add("hovering");
      };
      chartEl.onpointerleave = () => {
        chartEl.classList.remove("hovering");
        bars.forEach(bar => bar.classList.remove("active"));
      };

      const total = data.reduce((s, d) => s + d.value, 0);
      const complete = data.filter(d => !d.partial);
      const hits = complete.filter(d => d.value >= target).length;
      summary.textContent = `${gbp.format(total)} won in ${range} months. Target met in ${hits} of ${complete.length} complete months.`;
    }

    $$("[data-range]").forEach(b => b.addEventListener("click", () => {
      range = Number(b.dataset.range);
      $$("[data-range]").forEach(o => o.setAttribute("aria-pressed", o === b));
      draw();
    }));
    new ResizeObserver(() => draw()).observe(chartEl);
  }

  /* Pipeline drag and drop ---------------------------------------------- */
  const board = $("[data-board]");
  if (board) {
    const dock = $("[data-dock]");
    let dragged = null;

    const refreshTotals = () => $$(".column", board).forEach(col => {
      const cards = $$(".card", col);
      $("[data-col-total]", col).textContent = gbp.format(cards.reduce((s, c) => s + Number(c.dataset.value), 0) / 100);
      $("[data-col-count]", col).textContent = cards.length;
    });

    board.addEventListener("dragstart", e => {
      dragged = e.target.closest(".card");
      if (!dragged) return;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragged.dataset.deal);
      requestAnimationFrame(() => dragged.classList.add("dragging"));
      dock.classList.add("show");
    });
    document.addEventListener("dragend", () => {
      dragged?.classList.remove("dragging");
      dragged = null;
      dock.classList.remove("show");
      $$(".over").forEach(z => z.classList.remove("over"));
    });
    $$("[data-dropzone]").forEach(zone => {
      zone.addEventListener("dragover", e => {
        if (!dragged) return;
        e.preventDefault();
        zone.classList.add("over");
      });
      zone.addEventListener("dragleave", e => { if (!zone.contains(e.relatedTarget)) zone.classList.remove("over"); });
      zone.addEventListener("drop", async e => {
        e.preventDefault();
        zone.classList.remove("over");
        const card = dragged;
        if (!card) return;
        const stage = zone.dataset.stage || zone.closest("[data-stage]").dataset.stage;
        const from = card.closest("[data-stage]").dataset.stage;
        if (stage === from) return;
        const home = card.parentElement, next = card.nextSibling;
        if (stage === "Won" || stage === "Lost") card.remove();
        else zone.prepend(card);
        refreshTotals();
        try {
          const res = await post(`/deals/${card.dataset.deal}/stage`, { stage });
          toast(res.message);
          if (stage !== "Won" && stage !== "Lost") {
            // Keep the fallback menu in step with the card's new column.
            $$(".menu button[name=stage]", card).forEach(b => { b.hidden = b.value === stage; });
          }
        } catch (err) {
          home.insertBefore(card, next);
          refreshTotals();
          toast("That move didn't save. Check your connection and try again.", "error");
        }
      });
    });
  }

  /* Sortable tables ------------------------------------------------------ */
  $$("table[data-sortable]").forEach(table => {
    const heads = $$("th[data-sort]", table);
    heads.forEach((th, col) => th.addEventListener("click", () => {
      const index = [...th.parentElement.children].indexOf(th);
      const asc = th.getAttribute("aria-sort") === "descending";
      heads.forEach(h => h.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", asc ? "ascending" : "descending");
      const body = table.tBodies[0];
      const val = tr => { const td = tr.children[index]; return td?.dataset.v ?? td?.textContent.trim() ?? ""; };
      const rows = [...body.rows].filter(r => r.children.length > 1);
      rows.sort((a, b) => {
        const [x, y] = [val(a), val(b)];
        const cmp = th.dataset.sort === "num" ? Number(x) - Number(y) : x.localeCompare(y, "en-GB");
        return asc ? cmp : -cmp;
      });
      body.append(...rows);
    }));
  });

  /* Instant table filter ------------------------------------------------- */
  $$("[data-filter-table]").forEach(input => {
    const table = document.getElementById(input.dataset.filterTable);
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      $$("tbody tr", table).forEach(tr => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); });
    });
  });
  $$("[data-filter-group]").forEach(group => {
    const table = document.getElementById(group.dataset.filterGroup);
    group.addEventListener("click", e => {
      const b = e.target.closest("[data-filter]");
      if (!b) return;
      $$("[data-filter]", group).forEach(o => o.setAttribute("aria-pressed", o === b));
      $$("tbody tr[data-state]", table).forEach(tr => { tr.hidden = b.dataset.filter && tr.dataset.state !== b.dataset.filter; });
    });
  });

  /* Tabs ----------------------------------------------------------------- */
  $$("[role=tablist]").forEach(list => {
    const tabs = $$("[role=tab]", list);
    const show = tab => tabs.forEach(t => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    tabs.forEach((t, i) => {
      t.addEventListener("click", () => show(t));
      t.addEventListener("keydown", e => {
        const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (dir) { const n = tabs[(i + dir + tabs.length) % tabs.length]; show(n); n.focus(); }
      });
    });
    show(tabs[0]);
  });

  /* Activity tick-off without reload ------------------------------------- */
  $$("form.js-toggle").forEach(form => form.addEventListener("submit", async e => {
    e.preventDefault();
    const li = form.closest("li");
    try {
      const res = await post(form.action, {});
      li.classList.toggle("done", res.done);
      li.classList.toggle("late", false);
      form.querySelector(".tick").setAttribute("aria-pressed", res.done);
    } catch (err) { form.submit(); }
  }));

  /* Project autosave ----------------------------------------------------- */
  $$("form.js-autosave").forEach(form => {
    const range = form.progress, label = $("[data-progress-label]", form);
    const bar = $(".progress i", form.closest(".project"));
    range.addEventListener("input", () => { label.textContent = `${range.value}%`; bar.style.width = `${range.value}%`; });
    const card = form.closest(".project");
    // A status change moves the card to another column, so reload to re-sort.
    const save = async moved => {
      try {
        const res = await post(form.action, { progress: range.value, status: form.status.value });
        if (moved || res.status !== form.status.value) return location.reload();
        card.classList.remove("saved-flash");
        void card.offsetWidth;
        card.classList.add("saved-flash");
      } catch (err) { toast("Couldn't save that change. Try again.", "error"); }
    };
    range.addEventListener("change", () => save(false));
    form.status.addEventListener("change", () => save(true));
  });
})();
