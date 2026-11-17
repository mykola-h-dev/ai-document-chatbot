// Admin page: manage knowledge sources and review unanswered questions and leads.
(function () {
  const $ = (id) => document.getElementById(id);
  const msg = (text, bad) => { $("msg").textContent = text; $("msg").style.color = bad ? "#b3261e" : "#1f6b3a"; };

  function cell(text, cls) {
    const td = document.createElement("td");
    td.textContent = text == null ? "" : String(text);
    if (cls) td.className = cls;
    return td;
  }
  function emptyRow(tbody, cols, text) {
    const tr = document.createElement("tr");
    const td = cell(text, "empty");
    td.colSpan = cols;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

  async function loadSources() {
    const data = await api("/api/admin/sources");
    $("biz").textContent = data.business;
    $("summary").textContent = `${data.sources.length} sources, ${data.chunks} chunks, mode: ${data.mode}`;
    const tbody = $("sources");
    tbody.textContent = "";
    if (!data.sources.length) emptyRow(tbody, 4, "No documents yet - upload one below.");
    data.sources.forEach((s) => {
      const tr = document.createElement("tr");
      const name = cell(s.title);
      const sub = document.createElement("div");
      sub.className = "muted";
      sub.textContent = s.name;
      name.appendChild(sub);
      if (s.error) { const e = document.createElement("div"); e.className = "err"; e.textContent = s.error; name.appendChild(e); }
      tr.appendChild(name);
      const kind = cell("");
      const tag = document.createElement("span"); tag.className = "tag";
      tag.textContent = s.kind === "url" ? "web page" : s.name.split(".").pop().toUpperCase();
      kind.appendChild(tag);
      tr.appendChild(kind);
      tr.appendChild(cell(s.chunks, "num"));
      const actions = cell("");
      const del = document.createElement("button");
      del.className = "danger"; del.textContent = "Remove";
      del.addEventListener("click", async () => {
        if (!confirm(`Remove "${s.title}" from the chatbot?`)) return;
        try { await post("/api/admin/remove", { name: s.name }); msg(`Removed ${s.title}.`); loadSources(); }
        catch (e) { msg(e.message, true); }
      });
      actions.appendChild(del);
      tr.appendChild(actions);
      tbody.appendChild(tr);
    });
  }

  async function loadUnanswered() {
    const data = await api("/api/admin/unanswered");
    const tbody = $("unanswered");
    tbody.textContent = "";
    if (!data.grouped.length) emptyRow(tbody, 3, "Nothing yet - every question so far was answered.");
    data.grouped.slice(0, 50).forEach((g) => {
      const tr = document.createElement("tr");
      tr.append(cell(g.question), cell(g.count, "num"), cell(g.last));
      tbody.appendChild(tr);
    });
  }

  async function loadLeads() {
    const data = await api("/api/admin/leads");
    const tbody = $("leads");
    tbody.textContent = "";
    if (!data.leads.length) emptyRow(tbody, 4, "No leads yet.");
    data.leads.forEach((l) => {
      const tr = document.createElement("tr");
      tr.append(cell(l.ts), cell(l.name), cell(l.email), cell(l.question));
      tbody.appendChild(tr);
    });
  }

  $("upload").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = e.target.querySelector("input").files[0];
    if (!file) return;
    msg(`Uploading ${file.name}...`);
    try {
      await api("/api/admin/upload?name=" + encodeURIComponent(file.name), { method: "POST", body: file });
      msg(`Added ${file.name}.`);
      e.target.reset();
      loadSources();
    } catch (err) { msg(err.message, true); }
  });

  $("addurl").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = e.target.querySelector("input").value.trim();
    msg(`Fetching ${url}...`);
    try { const r = await post("/api/admin/url", { url }); msg(`Added "${r.title}".`); e.target.reset(); loadSources(); }
    catch (err) { msg(err.message, true); }
  });

  $("reindex").addEventListener("click", async () => {
    try { const r = await post("/api/admin/reindex", {}); msg(`Re-indexed: ${r.chunks} chunks.`); loadSources(); }
    catch (err) { msg(err.message, true); }
  });
  $("refetch").addEventListener("click", async () => {
    msg("Downloading web pages again...");
    try { const r = await post("/api/admin/reindex", { refetch: true }); msg(`Re-fetched and re-indexed: ${r.chunks} chunks.`); loadSources(); }
    catch (err) { msg(err.message, true); }
  });

  $("embed").textContent =
    `<script src="${location.origin}/widget.js"\n        data-title="Ask us anything"\n        data-color="#1f5f8b"\n        data-greeting="Hi! How can I help?"><\/script>`;

  Promise.all([loadSources(), loadUnanswered(), loadLeads()]).catch((e) => msg(e.message, true));
})();
