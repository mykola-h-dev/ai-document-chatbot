/*
 * Document chatbot widget - embed on any website with ONE script tag:
 *
 *   <script src="https://YOUR-SERVER/widget.js"
 *           data-title="Ask Maple Street Dental"
 *           data-color="#1f5f8b"
 *           data-greeting="Hi! Ask me about prices, hours or bookings."
 *           data-chips="What are your opening hours?|How much is a root canal?"
 *           data-position="right"></script>
 *
 * The widget lives in a Shadow DOM, so the host page's CSS cannot break it and
 * it cannot break the host page. Answers stream in token by token (Server-Sent
 * Events), carry numbered citations [1] that expand to the source passage, and
 * when the documents do not cover a question the visitor can leave name + email.
 * All server text is inserted with textContent (no HTML injection).
 */
(function () {
  "use strict";
  var script = document.currentScript || document.querySelector('script[src*="widget.js"]');
  if (!script || window.__docChatLoaded) return;
  window.__docChatLoaded = true;

  var API = new URL(script.src, location.href).origin;
  var cfg = {
    title: script.dataset.title || "Ask us anything",
    color: /^#[0-9a-fA-F]{3,8}$/.test(script.dataset.color || "") ? script.dataset.color : "#1f5f8b",
    greeting: script.dataset.greeting || "Hi! How can I help?",
    chips: (script.dataset.chips || "").split("|").map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 4),
    position: script.dataset.position === "left" ? "left" : "right",
    open: script.dataset.open === "true",
  };

  function sessionId() {
    var key = "docchat-session";
    try {
      var existing = sessionStorage.getItem(key);
      if (existing) return existing;
      var fresh = Array.from(crypto.getRandomValues(new Uint8Array(12)), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
      sessionStorage.setItem(key, fresh);
      return fresh;
    } catch (e) {
      return "s" + Math.random().toString(36).slice(2, 14);
    }
  }
  var SESSION = sessionId();

  var CSS = [
    ":host{all:initial}",
    "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}",
    ".toggle{position:fixed;bottom:24px;" + cfg.position + ":24px;width:60px;height:60px;border-radius:50%;border:0;background:var(--c);color:#fff;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.25);z-index:2147483000;display:flex;align-items:center;justify-content:center}",
    ".panel{position:fixed;bottom:96px;" + cfg.position + ":24px;width:min(390px,calc(100vw - 32px));height:min(600px,calc(100vh - 120px));background:#fff;border-radius:18px;box-shadow:0 16px 48px rgba(20,40,60,.25);display:flex;flex-direction:column;overflow:hidden;z-index:2147483000;color:#1d2733}",
    ".panel[hidden]{display:none}",
    ".head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;background:var(--c);color:#fff}",
    ".head strong{font-size:15px}.head .mode{display:block;font-size:12px;opacity:.85;margin-top:2px}",
    ".head button{background:none;border:0;color:#fff;font-size:26px;cursor:pointer;line-height:1}",
    ".log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f7f9fb}",
    ".msg{max-width:88%;padding:10px 13px;border-radius:14px;line-height:1.45;font-size:14px;white-space:pre-wrap;word-wrap:break-word}",
    ".bot{background:#fff;border:1px solid #e3e9ef;align-self:flex-start;border-bottom-left-radius:4px}",
    ".user{background:var(--c);color:#fff;align-self:flex-end;border-bottom-right-radius:4px}",
    ".nf{border-color:#f2a541;background:#fff8ee}",
    ".typing{color:#6b7b8b;font-style:italic}",
    ".cite{display:inline-block;min-width:18px;padding:0 4px;margin:0 1px;border:0;border-radius:6px;background:#e8f0f7;color:var(--c);font-size:11px;font-weight:700;cursor:pointer;vertical-align:super;line-height:16px}",
    ".sources{margin-top:8px;border-top:1px solid #eef2f6;padding-top:6px;font-size:12px;color:#5b6b7b}",
    ".sources details{margin-top:3px}.sources summary{cursor:pointer}",
    ".sources .snip{margin:4px 0 2px 14px;padding:6px 8px;background:#f4f7fa;border-left:3px solid var(--c);border-radius:4px;color:#33414f;white-space:normal}",
    ".chips[hidden]{display:none}",
    ".chips{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px 0;background:#fff}",
    ".chips button{border:1px solid #cfdbe6;background:#fff;border-radius:999px;padding:5px 10px;font-size:12px;cursor:pointer;color:var(--c)}",
    "form.ask{display:flex;gap:8px;padding:12px;border-top:1px solid #eef2f6;background:#fff}",
    "input{flex:1;border:1px solid #cfdbe6;border-radius:999px;padding:10px 14px;font-size:14px;outline:none;min-width:0}",
    "input:focus{border-color:var(--c)}",
    "form button,.lead button{border:0;background:var(--c);color:#fff;border-radius:999px;padding:0 16px;font-weight:600;cursor:pointer;font-size:14px}",
    ".lead{display:flex;flex-direction:column;gap:6px;margin-top:8px}",
    ".lead input{border-radius:8px;padding:8px 10px;font-size:13px}",
    ".lead button{padding:8px 12px;border-radius:8px;align-self:flex-start}",
    ".lead .hp{position:absolute;left:-9999px;width:1px;height:1px}",
    ".small{font-size:12px;color:#5b6b7b}",
  ].join("\n");

  var host = document.createElement("div");
  host.id = "docchat-widget";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" + CSS + "</style>" +
    '<button class="toggle" aria-label="Open chat"><svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path fill="currentColor" d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z"/></svg></button>' +
    '<section class="panel" hidden aria-live="polite">' +
    '<div class="head"><div><strong class="title"></strong><span class="mode">connecting...</span></div><button class="close" aria-label="Close chat">&times;</button></div>' +
    '<div class="log"></div><div class="chips"></div>' +
    '<form class="ask"><input type="text" maxlength="500" placeholder="Type your question..." autocomplete="off" required aria-label="Your question"><button type="submit">Send</button></form>' +
    "</section>";
  host.style.setProperty("--c", cfg.color);

  var $ = function (sel) { return root.querySelector(sel); };
  var panel = $(".panel"), log = $(".log"), input = $("form.ask input"), modeLabel = $(".mode");
  $(".title").textContent = cfg.title;
  var busy = false;

  function setOpen(open) {
    panel.hidden = !open;
    if (open) input.focus();
  }
  $(".toggle").addEventListener("click", function () { setOpen(panel.hidden); });
  $(".close").addEventListener("click", function () { setOpen(false); });

  cfg.chips.forEach(function (text) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", function () { ask(text); });
    $(".chips").appendChild(b);
  });
  if (!cfg.chips.length) $(".chips").remove();

  $("form.ask").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (q) ask(q);
    input.value = "";
  });

  fetch(API + "/api/status").then(function (r) { return r.json(); }).then(function (s) {
    modeLabel.textContent = s.mode === "offline"
      ? "Offline demo mode - answers quoted from our documents"
      : "AI answers from our documents, with sources";
  }).catch(function () { modeLabel.textContent = "Server not reachable"; });

  function addMessage(text, cls) {
    var div = document.createElement("div");
    div.className = "msg " + cls;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  // Render "text [1] more [2]" with clickable citation markers.
  function renderAnswer(el, text) {
    el.textContent = "";
    text.split(/(\[\d\])/).forEach(function (part) {
      var m = /^\[(\d)\]$/.exec(part);
      if (!m) { el.appendChild(document.createTextNode(part)); return; }
      var b = document.createElement("button");
      b.type = "button"; b.className = "cite"; b.textContent = m[1];
      b.title = "Show source " + m[1];
      b.addEventListener("click", function () {
        var d = el.querySelector('details[data-n="' + m[1] + '"]');
        if (d) { d.open = true; d.scrollIntoView({ block: "nearest" }); }
      });
      el.appendChild(b);
    });
  }

  function renderSources(el, sources) {
    if (!sources || !sources.length) return;
    var box = document.createElement("div");
    box.className = "sources";
    var label = document.createElement("div");
    label.textContent = sources.length === 1 ? "Source" : "Sources";
    box.appendChild(label);
    sources.forEach(function (s) {
      var d = document.createElement("details");
      d.dataset.n = s.n;
      var sum = document.createElement("summary");
      sum.textContent = "[" + s.n + "] " + s.label;
      var snip = document.createElement("div");
      snip.className = "snip";
      snip.textContent = s.snippet;
      d.appendChild(sum); d.appendChild(snip);
      box.appendChild(d);
    });
    el.appendChild(box);
  }

  function leadForm(el, question) {
    var f = document.createElement("form");
    f.className = "lead";
    f.innerHTML = '<input name="name" placeholder="Your name" maxlength="100" required aria-label="Your name">' +
      '<input name="email" type="email" placeholder="Email" maxlength="200" required aria-label="Email">' +
      '<input name="website" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">' +
      '<button type="submit">Ask the team</button>';
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var field = function (n) { return f.elements.namedItem(n).value; };
      var body = { name: field("name"), email: field("email"), website: field("website"), question: question };
      fetch(API + "/api/lead", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          var note = document.createElement("div");
          note.className = "small";
          note.textContent = res.ok ? (res.d.message || "Thanks!") : (res.d.error || "Could not send.");
          if (res.ok) f.replaceWith(note); else f.appendChild(note);
        })
        .catch(function () { f.appendChild(document.createTextNode(" Could not reach the server.")); });
    });
    el.appendChild(f);
  }

  function finish(el, data, question) {
    renderAnswer(el, data.answer);
    if (!data.found) el.classList.add("nf");
    renderSources(el, data.sources);
    if (data.offer_lead) leadForm(el, question);
    log.scrollTop = log.scrollHeight;
  }

  // Read a Server-Sent Events stream from a POST response.
  async function readStream(res, onEvent) {
    var reader = res.body.getReader(), decoder = new TextDecoder(), buffer = "";
    for (;;) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var blocks = buffer.split("\n\n");
      buffer = blocks.pop();
      blocks.forEach(function (block) {
        var ev = "message", data = "";
        block.split("\n").forEach(function (line) {
          if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
          else if (line.indexOf("data:") === 0) data += line.slice(5).trim();
        });
        if (data) onEvent(ev, JSON.parse(data));
      });
    }
  }

  async function ask(question) {
    if (busy) return;
    busy = true;
    var chips = $(".chips");
    if (chips) chips.hidden = true; // suggestions only before the first question
    addMessage(question, "user");
    var el = addMessage("Looking that up...", "bot typing");
    var text = "", done = false;
    try {
      var res = await fetch(API + "/api/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, session_id: SESSION }),
      });
      if (!res.ok || !res.body) {
        var err = await res.json().catch(function () { return {}; });
        el.classList.remove("typing");
        el.textContent = err.error || "Something went wrong.";
        return;
      }
      await readStream(res, function (ev, data) {
        if (ev === "token") {
          if (!text) el.classList.remove("typing");
          text += data;
          el.textContent = text;
          log.scrollTop = log.scrollHeight;
        } else if (ev === "replace") {
          text = data;
          el.textContent = text;
        } else if (ev === "done") {
          done = true;
          finish(el, data, question);
        }
      });
      if (!done) el.textContent = text || "The answer was interrupted.";
    } catch (e) {
      el.classList.remove("typing");
      el.textContent = "Sorry, I can't reach the server right now.";
    } finally {
      busy = false;
    }
  }

  addMessage(cfg.greeting, "bot");
  if (cfg.open) setOpen(true);

  // Presentation mode: add ?autoplay to the page URL to watch sample questions.
  var params = new URLSearchParams(location.search);
  if (params.has("autoplay")) {
    setOpen(true);
    var demo = (params.get("autoplay") || "").split("|").filter(Boolean);
    if (!demo.length) demo = cfg.chips.slice(0, 3);
    (async function () {
      for (var i = 0; i < demo.length; i++) await ask(demo[i]);
      var all = log.querySelectorAll("details");
      if (all.length) { all[all.length - 1].open = true; log.scrollTop = log.scrollHeight; } // show a source passage
    })();
  }
  window.DocChat = { ask: ask, open: function () { setOpen(true); } };
})();
