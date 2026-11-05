// Films the real app: starts a fresh demo workspace on the local server (made-up UK businesses), walks the
// story from the storyboard, and saves a sharp screenshot of each step plus the on-screen position of the
// things the video points at (public/shots/*.png and public/shots/boxes.json).
//
//   FILM_LOGIN=<film-login.txt> node capture/capture.mjs [base-url]     default http://localhost:5070
//
// Never point this at the live site: it creates a demo, submits a web form, moves a deal and signs a quote.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = (process.argv[2] || "http://localhost:5070").replace(/\/$/, "");
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(BASE)) throw new Error("Capture only runs against a local server.");
const OUT = path.resolve("public/shots");
fs.mkdirSync(OUT, { recursive: true });
const boxes = {};

// Things that belong to the demo or the moment, not to the product: hidden while filming.
const FILM_CSS = `
  .plan-banner, .demo-banner, .flash, .flashes, .toast, .getting-started { display: none !important; }
  ::-webkit-scrollbar { display: none; } html { scrollbar-width: none; }
  *, *::before, *::after { caret-color: transparent !important; }`;

const browser = await chromium.launch({ args: ["--lang=en-GB"] });

async function newPage(viewport, scale, storageState) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: scale, colorScheme: "light", locale: "en-GB",
    timezoneId: "Europe/London", storageState, reducedMotion: "reduce" });
  await context.addInitScript(css => {
    try { localStorage.setItem("cae-theme", "light"); } catch (e) {}
    addEventListener("DOMContentLoaded", () => {
      const s = document.createElement("style"); s.textContent = css; document.head.append(s);
      // The headless browser draws date and time fields the American way; show them as a UK browser does.
      document.querySelectorAll('input[type="date"]').forEach(el => {
        const [y, m, d] = (el.value || "").split("-"); el.type = "text"; if (y) el.value = `${d}/${m}/${y}`;
      });
      document.querySelectorAll('input[type="time"]').forEach(el => { el.type = "text"; });
    });
  }, FILM_CSS);
  return { context, page: await context.newPage() };
}

// Saves a screenshot and the boxes of the named elements, in CSS pixels of the viewport.
async function shot(page, name, targets = {}) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  const found = {};
  for (const [key, locator] of Object.entries(targets)) {
    const box = await locator.first().boundingBox().catch(() => null);
    if (box) found[key] = Object.fromEntries(Object.entries(box).map(([k, v]) => [k, Math.round(v)]));
    else console.warn(`  ${name}: couldn't find "${key}"`);
  }
  boxes[name] = { viewport: page.viewportSize(), ...found };
  console.log(`saved ${name}`);
}

// A POST from inside the signed-in page, with the page's own anti-forgery token, returning where it landed.
async function post(page, url, fields) {
  return page.evaluate(async ([url, fields]) => {
    const csrf = document.querySelector('input[name="csrf"]')?.value;
    const body = new URLSearchParams({ csrf, ...fields });
    const res = await fetch(url, { method: "POST", body, redirect: "follow" });
    return res.url;
  }, [url, fields]);
}

const DESKTOP = { width: 1920, height: 1080 };
const DS = Number(process.env.DESKTOP_SCALE || 3), PS = Number(process.env.PHONE_SCALE || 4);  // 3x desktop and 4x phone, sharp at 4K
// 1. Sign in to the filming copy (run_film.py): a full workspace with made-up businesses, where every feature works.
//    The demo can't be used: it blocks sending quotes, which this story needs. FILM_LOGIN is the file run_film.py wrote.
const [email, password] = fs.readFileSync(process.env.FILM_LOGIN, "utf8").trim().split(/\s+/);
let { context, page } = await newPage(DESKTOP, DS);
await page.goto(`${BASE}/login`);
await page.fill('input[name="email"]', email);
await page.fill('input[name="password"]', password);
await Promise.all([page.waitForURL(u => !u.pathname.startsWith("/login")), page.click("form button[type=submit], form.auth-form button")]);

// 2. The dashboard.
await page.goto(`${BASE}/`);
await shot(page, "dashboard", { track: page.locator("section.track"), stats: page.locator("section.stats") });

// 3. A website enquiry, filled in on the public form, then arriving as a lead.
await page.goto(`${BASE}/forms`);
await page.locator("main a[href^='/forms/']").first().click();
const formUrl = await page.locator("a[href*='/f/'], input[readonly]").first()
  .evaluate(el => el.getAttribute("href") || el.value);
await page.goto(formUrl);
await page.fill('[name="first_name"]', "Eilidh");
await page.fill('[name="last_name"]', "Campbell");
await page.fill('[name="email"]', "eilidh.campbell@example.co.uk");
await page.fill('[name="company"]', "Leith Harbour Cafés Ltd");
await page.fill('[name="message"]', "Hi, we run three cafés in Leith and want one place for orders, invoices and support. Could we have a quote for five users?");
await shot(page, "webform", { card: page.locator(".public-form-card, form").first(), message: page.locator('[name="message"]') });
await page.waitForTimeout(4000);  // the form ignores submissions made faster than a person could type
await page.locator("form button[type=submit], form button").last().click();
await page.waitForLoadState("networkidle");
await page.goto(`${BASE}/contacts?lifecycle=Lead&lead_status=New`);
await page.locator("main a[href^='/contacts/']", { hasText: "Eilidh" }).first().click();
boxes.contactId = page.url().match(/\/contacts\/(\d+)/)[1];
await shot(page, "contact", { activity: page.getByText("Submitted the form").first(), lead: page.getByText("Eilidh Campbell").nth(1) });

// 4. The deals board: a deal moves from the second column to the third.
await page.goto(`${BASE}/pipeline?owner=Alex+Morgan`);
const columns = page.locator("section.column");
let fromIndex = 0;
while (fromIndex < 3 && !(await columns.nth(fromIndex).locator("article.card").count())) fromIndex++;
const from = columns.nth(fromIndex), to = columns.nth(fromIndex + 1);
const card = from.locator("article.card").first();
const dealName = (await card.locator(".card-title").innerText()).trim();
await shot(page, "pipeline-before", { card, target: to.locator(".col-body"), from: from.locator(".col-body") });
await card.dragTo(to.locator(".col-body"));
await page.waitForTimeout(800);
await page.reload();
await page.evaluate(() => scrollTo(0, 0));
await shot(page, "pipeline-after", { card: page.locator("article.card", { hasText: dealName }), target: to.locator(".col-body") });
boxes.dealName = dealName;

// 5. A quote: sent, then signed online by the customer.
await page.goto(`${BASE}/quotes?status=Draft`);
let quoteLink = page.locator("main a[href^='/quotes/']").first();
if (!(await quoteLink.count())) {
  await page.goto(`${BASE}/quotes?status=Sent`);
  quoteLink = page.locator("main a[href^='/quotes/']").first();
}
await quoteLink.click();
const quoteUrl = page.url();
const quoteId = quoteUrl.match(/\/quotes\/(\d+)/)[1];
const send = page.locator(`form[action$="/quotes/${quoteId}/send"] button`);
if (await send.count()) await Promise.all([page.waitForResponse(r => r.url().endsWith("/send") && r.request().method() === "POST"), send.first().click()]);
await page.goto(quoteUrl);
const publicQuote = await page.evaluate(() => [...document.querySelectorAll("a[href], input[readonly]")]
  .map(el => el.getAttribute("href") || el.value).find(u => /\/q\/[^/]+$/.test(u || "")));
if (!publicQuote) throw new Error("No public quote link on " + quoteUrl);
const customer = await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: DS, colorScheme: "light", locale: "en-GB" });
const cpage = await customer.newPage();
await cpage.addInitScript(css => addEventListener("DOMContentLoaded", () => { const s = document.createElement("style"); s.textContent = css; document.head.append(s); }), FILM_CSS);
await cpage.goto(publicQuote);
await cpage.fill('[name="signer_name"]', "Eilidh Campbell");
await cpage.fill('[name="signer_position"]', "Director").catch(() => {});
await cpage.check('[name="agree"]');
await shot(cpage, "quote-sign", { sign: cpage.locator('[name="signer_name"]'), total: cpage.locator("text=/Total/").last(), accept: cpage.locator("form[action$='/accept'] button").first() });
await cpage.locator("form[action$='/accept'] button").first().click();
await shot(cpage, "quote-accepted", { badge: cpage.locator("text=/Accepted|accepted/").first() });

// 6. An invoice: the VAT line and its paid status.
await page.goto(`${BASE}/invoices`);
const paidRow = page.locator("main tr", { hasText: "Paid" }).first();
await (await paidRow.count() ? paidRow : page.locator("main tr").nth(1)).locator("a[href^='/invoices/']").first().click();
const markPaid = page.locator("form[action$='/paid'] button");
if (await markPaid.count()) {
  await Promise.all([page.waitForResponse(r => r.url().endsWith("/paid") && r.request().method() === "POST"), markPaid.first().click()]);
  await page.waitForLoadState("networkidle");
}
boxes.invoiceUrl = page.url();
await shot(page, "invoice", { vat: page.locator("text=/VAT/").last(), total: page.locator(".total").first(), status: page.getByText(/^Paid/).first(), doc: page.locator(".doc, .invoice-doc, article").first() });

// 7. A new support ticket, so its service deadline is counting down rather than overdue.
await page.goto(`${BASE}/tickets`);
const ticketUrl = await post(page, "/tickets", { subject: "Card reader not connecting at the Leith branch", priority: "Medium", contact_id: boxes.contactId,
  description: "Since this morning the card reader won't pair with the till." });
await page.goto(ticketUrl);
await shot(page, "ticket", { sla: page.locator(".sla-panel, .sla-box").first(), subject: page.locator("h1").first() });

// 8. Phone-height screens for the 9:16 ad.
const state = await context.storageState();
const phone = await newPage({ width: 430, height: 932 }, PS, state);
await phone.page.goto(`${BASE}/pipeline?owner=Alex+Morgan`);
await shot(phone.page, "m-pipeline", { card: phone.page.locator("article.card").first() });
await phone.page.goto(ticketUrl);
await phone.page.locator(".sla-panel, .sla-box").first().evaluate(el => scrollTo(0, el.getBoundingClientRect().top + scrollY - 260));
await shot(phone.page, "m-ticket", { sla: phone.page.locator(".sla-panel, .sla-box").first() });
await phone.page.goto(boxes.invoiceUrl);
await shot(phone.page, "m-invoice", { total: phone.page.locator(".total").first() });
const phoneCustomer = await browser.newContext({ viewport: { width: 430, height: 932 }, deviceScaleFactor: PS, colorScheme: "light", locale: "en-GB" });
const mq = await phoneCustomer.newPage();
await mq.addInitScript(css => addEventListener("DOMContentLoaded", () => { const s = document.createElement("style"); s.textContent = css; document.head.append(s); }), FILM_CSS);
await mq.goto(publicQuote);
await shot(mq, "m-quote-accepted", { badge: mq.locator("text=/Accepted|accepted/").first() });

fs.writeFileSync(path.join(OUT, "boxes.json"), JSON.stringify(boxes, null, 2));
console.log("done:", Object.keys(boxes).length, "entries");
await browser.close();
