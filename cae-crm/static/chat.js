/* The website chat window: send messages and the handover form without reloading. The page works without this. */
(() => {
  "use strict";
  const box = document.querySelector("[data-chat]");
  if (!box) return;
  const thread = box.querySelector("[data-chat-thread]");
  const latest = thread.querySelector("#latest");
  let session = box.dataset.session || "";

  function add(cls, html, text) {
    const div = document.createElement("div");
    div.className = `chat-msg ${cls}`;
    if (html !== null) div.innerHTML = html; else div.append(Object.assign(document.createElement("p"), { textContent: text }));
    thread.insertBefore(div, latest);
    thread.scrollTop = thread.scrollHeight;
    return div;
  }
  function notice(text) {
    const p = Object.assign(document.createElement("p"), { className: "chat-notice", textContent: text });
    p.setAttribute("role", "status");
    thread.insertBefore(p, latest);
    thread.scrollTop = thread.scrollHeight;
  }
  async function send(form) {
    const data = new URLSearchParams(new FormData(form));
    data.set("session", session);
    const res = await fetch(form.action, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } });
    return res.json().catch(() => ({ error: "Something went wrong. Please try again." }));
  }

  const form = box.querySelector("[data-chat-form]");
  const area = form?.querySelector("textarea");
  area?.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  form?.addEventListener("submit", async e => {
    e.preventDefault();
    const text = area.value.trim();
    if (!text) return;
    box.querySelector(".chat-articles")?.remove();
    add("visitor", null, text);
    area.value = "";
    const thinking = add("bot thinking", null, "Thinking…");
    form.querySelector("button").disabled = true;
    try {
      const out = await send(form);
      thinking.remove();
      if (out.session) session = out.session;
      if (out.error) notice(out.error);
      if (out.notice) notice(out.notice);
      if (out.reply) {
        const msg = add("bot", out.reply, null);
        if (out.links?.length) {
          const p = Object.assign(document.createElement("p"), { className: "chat-sources", textContent: "From: " });
          out.links.forEach((l, i) => {
            const a = Object.assign(document.createElement("a"), { href: l.url, textContent: l.title, target: "_blank", rel: "noopener" });
            p.append(a, i < out.links.length - 1 ? ", " : "");
          });
          msg.append(p);
        }
      }
      if (out.offer_person) box.querySelector("[data-chat-person]").open = true;
    } catch (err) {
      thinking.remove();
      notice("The message didn't send. Check your connection and try again.");
      area.value = text;
    } finally {
      form.querySelector("button").disabled = false;
      area.focus();
    }
  });

  const person = box.querySelector("[data-chat-person-form]");
  person?.addEventListener("submit", async e => {
    e.preventDefault();
    const button = person.querySelector("button");
    button.disabled = true;
    try {
      const out = await send(person);
      if (out.done) {
        notice(out.done);
        box.querySelector("[data-chat-person]").remove();
        form?.remove();
      } else notice(out.error || "Please check your details and try again.");
    } catch (err) {
      notice("That didn't send. Check your connection and try again.");
    } finally { button.disabled = false; }
  });
})();
