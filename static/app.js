async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function jpost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function setFlow(status) {
  const order = ["parse", "validate", "gate1", "draft", "gate2", "import"];
  let active = 0;
  if (status === "blocked" || status === "paused") active = 0;
  else if (status === "held" || status === "awaiting_gate1") active = 2;
  else if (status === "awaiting_gate2" || status === "ready_to_import") active = 4;
  else if (status === "import_stub_logged") active = 5;
  else active = 1;
  document.querySelectorAll("#flow-steps li").forEach((li, idx) => {
    li.classList.toggle("active", idx === active);
    li.classList.toggle("done", idx < active || status === "import_stub_logged");
  });
}

function verdictClass(decision) {
  if (decision === "ALLOW") return "badge-allow";
  if (decision === "BLOCK") return "badge-block";
  return "badge-hold";
}

async function loadHouseholds() {
  const rows = await jget("/api/households");
  const sel = document.getElementById("household-select");
  sel.innerHTML = rows
    .map((h) => `<option value="${h.id}">${h.id} · ${h.account_type} · firm ${h.firm_id}</option>`)
    .join("");
}

async function loadEval() {
  try {
    const report = await jget("/api/evals/latest?mode=stub");
    const m = report.metrics;
    document.getElementById("eval-table").innerHTML = `
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Cases</td><td>${m.cases_passed}/${m.cases_total}</td></tr>
        <tr><td>Migration accuracy</td><td>${(m.migration_accuracy * 100).toFixed(2)}%</td></tr>
        <tr><td>Abstention (unanswerable)</td><td>${(m.abstention_rate_unanswerable * 100).toFixed(2)}%</td></tr>
        <tr><td>Injection block rate</td><td>${m.injection_block_rate}</td></tr>
        <tr><td>Citation coverage</td><td>${(m.citation_coverage * 100).toFixed(2)}%</td></tr>
        <tr><td>Pause detection</td><td>${(m.pause_detection * 100).toFixed(2)}%</td></tr>
        <tr><td>Fabrication-trap rate</td><td>${(m.fabrication_trap_rate * 100).toFixed(2)}%</td></tr>
        <tr><td>LLM cost</td><td>$${Number(m.llm_cost_usd).toFixed(2)}</td></tr>
      </table>`;
  } catch (e) {
    document.getElementById("eval-table").textContent = "No committed stub report yet.";
  }
}

async function loadReview() {
  const items = await jget("/api/review");
  const el = document.getElementById("review-list");
  if (!items.length) {
    el.textContent = "Queue empty.";
    return;
  }
  el.innerHTML = "";
  for (const item of items) {
    const div = document.createElement("div");
    div.className = "review-item";
    div.innerHTML = `
      <strong>${item.id}</strong>
      <span class="muted">${item.gate} · ${item.household_id} · ${item.status}</span>
      <div class="review-actions">
        <button type="button" data-act="approve">Approve</button>
        <button type="button" class="ghost" data-act="reject">Reject</button>
      </div>`;
    div.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await jpost(`/api/review/${item.id}`, {
          action: btn.dataset.act,
          reason: `${btn.dataset.act} from dashboard`,
          actor: "dashboard",
        });
        await loadReview();
      });
    });
    el.appendChild(div);
  }
}

document.getElementById("run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const household_id = document.getElementById("household-select").value;
  const auto_approve_gates = document.getElementById("auto-gates").checked;
  const body = document.getElementById("result-body");
  const badge = document.getElementById("verdict-badge");
  body.textContent = "Running…";
  try {
    const result = await jpost("/api/run", { household_id, auto_approve_gates });
    const g = result.guardrail || {};
    badge.textContent = g.decision || result.final_status || "done";
    badge.className = `badge ${verdictClass(g.decision)}`;
    setFlow(result.final_status);
    body.innerHTML = `<div class="mono">${JSON.stringify(
      {
        final_status: result.final_status,
        guardrail: g,
        gate1: result.gate1,
        gate2: result.gate2,
        abstained: result.abstained,
        import_log: result.import_log,
        plan_lines: (((result.plan_result || {}).plan || {}).lines || []).slice(0, 8),
      },
      null,
      2
    )}</div>`;
    await loadReview();
  } catch (err) {
    body.textContent = String(err);
  }
});

document.getElementById("refresh-review").addEventListener("click", loadReview);

loadHouseholds();
loadEval();
loadReview();
