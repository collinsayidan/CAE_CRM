/* CAE CRM website chat. Paste <script src=".../chat/widget.js" data-chat="TOKEN" async></script> into your website.
   Adds a chat button; the chat itself opens in a frame served by CAE CRM, so it can't affect the rest of the page. */
(function () {
  "use strict";
  var script = document.currentScript;
  var token = script && script.getAttribute("data-chat");
  if (!token || window.__caeChat) return;
  window.__caeChat = true;
  var origin = {{ origin | tojson }};
  var label = script.getAttribute("data-label") || "Chat with us";
  var teal = "#0f766e";

  var button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-expanded", "false");
  button.textContent = label;
  button.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483000;border:0;border-radius:999px;" +
    "background:" + teal + ";color:#fff;font:600 15px/1 system-ui,-apple-system,'Segoe UI',sans-serif;" +
    "padding:14px 20px;box-shadow:0 8px 24px rgba(15,31,61,.25);cursor:pointer";

  var frame = null;
  function place() {
    if (!frame) return;
    var small = window.innerWidth < 520;
    frame.style.cssText = "position:fixed;z-index:2147483001;border:0;background:#fff;box-shadow:0 18px 50px rgba(15,31,61,.3);" +
      (small ? "inset:0;width:100%;height:100%;border-radius:0" :
               "right:20px;bottom:84px;width:380px;height:min(600px,calc(100vh - 110px));border-radius:16px");
  }
  function toggle() {
    if (!frame) {
      frame = document.createElement("iframe");
      frame.src = origin + "/chat/" + encodeURIComponent(token) + "?embed=1";
      frame.title = label;
      frame.setAttribute("allow", "clipboard-write");
      document.body.appendChild(frame);
      place();
      window.addEventListener("resize", place);
    } else {
      frame.style.display = frame.style.display === "none" ? "" : "none";
    }
    var open = frame.style.display !== "none";
    button.textContent = open ? "Close chat" : label;
    button.setAttribute("aria-expanded", String(open));
    if (open && window.innerWidth < 520) { button.style.zIndex = "2147483002"; }
  }
  button.addEventListener("click", toggle);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && frame && frame.style.display !== "none") toggle();
  });
  (document.body ? Promise.resolve() : new Promise(function (r) { document.addEventListener("DOMContentLoaded", r); }))
    .then(function () { document.body.appendChild(button); });
})();
