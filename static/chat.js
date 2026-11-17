// Chat widget: sends questions to /api/ask and renders answers with their page citation.
(function () {
  const chat = document.getElementById("chat");
  const log = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const modeLabel = document.getElementById("chat-mode");

  document.getElementById("chat-toggle").addEventListener("click", () => {
    chat.classList.toggle("hidden");
    if (!chat.classList.contains("hidden")) input.focus();
  });
  document.getElementById("chat-close").addEventListener("click", () => chat.classList.add("hidden"));

  // Suggested questions
  document.querySelectorAll("#chips button").forEach((chip) =>
    chip.addEventListener("click", () => ask(chip.textContent))
  );

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (question) ask(question);
    input.value = "";
  });

  // Show whether the backend answers with AI or in offline demo mode.
  fetch("/api/status")
    .then((r) => r.json())
    .then((s) => {
      modeLabel.textContent = s.mode === "offline"
        ? "Offline demo mode - answers quoted from the guide"
        : "AI answers from our patient guide";
    })
    .catch(() => (modeLabel.textContent = "Server not reachable"));

  // Presentation mode: open /?autoplay to open the chat and ask sample questions automatically.
  if (new URLSearchParams(location.search).has("autoplay")) {
    chat.classList.remove("hidden");
    (async () => {
      for (const q of ["What are your opening hours?", "How much is a root canal?", "Do you do braces?"]) {
        await ask(q);
      }
    })();
  }

  function addMessage(text, cls) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    div.textContent = text; // textContent avoids HTML injection
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  async function ask(question) {
    addMessage(question, "user");
    const typing = addMessage("Looking that up...", "bot typing");
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      typing.remove();
      if (!res.ok) return addMessage(data.error || "Something went wrong.", "bot");
      const msg = addMessage(data.answer, data.found ? "bot" : "bot not-found");
      if (data.sources && data.sources.length) {
        const src = document.createElement("span");
        src.className = "source";
        src.textContent = "Source: " + data.sources.join("; ");
        msg.appendChild(src);
      }
    } catch (err) {
      typing.remove();
      addMessage("Sorry, I can't reach the server right now.", "bot");
    }
  }
})();
