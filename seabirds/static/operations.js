const $ = (s) => document.querySelector(s);
const labels = {
  "github.review": "Revisar publicação",
  "github.review-site": "Revisar site",
  "github.sync": "Atualizar main",
  "github.publish": "Publicar no GitHub",
  "github.retry": "Reenviar commit",
  "site.clone": "Clonar repositório",
  "site.audit": "Verificar site",
  "site.delete-preview": "Revisar exclusão",
  "site.delete": "Excluir documentação",
  "document.generate": "Gerar documentação",
  "backup.create": "Criar backup",
  "backup.inspect": "Abrir backup",
  "backup.preview": "Revisar restauração",
  "backup.restore": "Restaurar backup",
  "text.review": "Revisar texto",
  diagnostics: "Diagnóstico",
  "diagnostics.git": "Testar Git",
};
const watchers = new Map(),
  renderers = new Map();
let options = {},
  panel,
  floating,
  lastJob,
  hideTimer;
export function registerOperationResult(kind, callback) {
  renderers.set(kind, callback);
}
export async function rawRequest(url, options = {}) {
  const { timeout = 20000, ...init } = options;
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init.body instanceof FormData || init.body instanceof Blob
          ? {}
          : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
    if (!response.ok) {
      let message = "Falha na operação (" + response.status + ").";
      try {
        const data = await response.json();
        message = Array.isArray(data.detail)
          ? data.detail.map((x) => x.msg).join("; ")
          : data.detail || message;
      } catch {}
      throw Error(message);
    }
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError")
      throw Error(
        "O servidor demorou a responder. Consulte Operações antes de repetir uma alteração.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
function draw(job) {
  lastJob = job;
  if (!floating) return;
  clearTimeout(hideTimer);
  const dialog = $("#modal");
  if (dialog?.open && floating.parentElement !== dialog)
    dialog.append(floating);
  else if (!dialog?.open && floating.parentElement !== document.body)
    document.body.append(floating);
  floating.hidden = false;
  $("#operation-name").textContent = labels[job.kind] || job.kind;
  $("#operation-step").textContent = job.error || job.step;
  $("#operation-progress").value = job.percent || 0;
  $("#operation-time").textContent =
    Math.max(0, Math.round((Date.now() - Date.parse(job.created_at)) / 1000)) +
    " s";
  floating.dataset.status = job.status;
  if (job.status === "succeeded")
    hideTimer = setTimeout(() => {
      if (lastJob?.id === job.id && lastJob.status === "succeeded")
        floating.hidden = true;
    }, 4000);
}
function watch(identifier, quiet = false) {
  if (watchers.has(identifier)) return watchers.get(identifier);
  const task = (async () => {
    const deadline = Date.now() + 660000;
    while (Date.now() < deadline) {
      let job;
      try {
        job = await rawRequest("/api/operations/" + identifier);
      } catch {
        throw Error(
          "A conexão foi interrompida. A operação pode continuar no servidor; consulte Operações para confirmar o resultado.",
        );
      }
      if (!quiet) draw(job);
      if (["succeeded", "failed", "interrupted"].includes(job.status))
        return job;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw Error(
      "A consulta demorou além do limite. Verifique o estado em Operações antes de repetir.",
    );
  })();
  watchers.set(identifier, task);
  task.finally(() => watchers.delete(identifier)).catch(() => {});
  return task;
}
export async function runOperation(kind, payload, { quiet = false } = {}) {
  const requestId =
    typeof crypto?.randomUUID === "function"
      ? crypto.randomUUID()
      : "job-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  const started = await rawRequest("/api/operations", {
    method: "POST",
    body: JSON.stringify({ kind, payload, request_id: requestId }),
  });
  if (!quiet) draw(started);
  const job = await watch(started.id, quiet);
  if (!quiet) draw(job);
  if (job.status !== "succeeded") throw Error(job.error || job.step);
  return job.result;
}
function operationKind(url) {
  const exact = {
    "/api/generator/github/review": "github.review",
    "/api/generator/github/review-site": "github.review-site",
    "/api/generator/github/sync": "github.sync",
    "/api/generator/github/publish": "github.publish",
    "/api/generator/site/clone": "site.clone",
    "/api/generator/generate": "document.generate",
  };
  if (exact[url]) return [exact[url], {}];
  let match = url.match(
    /^\/api\/generator\/site\/pages\/trash\/([^/]+)\/(delete-preview|delete)$/,
  );
  if (match) return ["site." + match[2], { identifier: match[1] }];
  match = url.match(/^\/api\/generator\/github\/publications\/([^/]+)\/retry$/);
  if (match) return ["github.retry", { identifier: match[1] }];
  return null;
}
export function request(url, init = {}) {
  const operation = operationKind(url);
  if (operation && init.method === "POST")
    return runOperation(operation[0], {
      ...JSON.parse(init.body),
      ...operation[1],
    });
  return rawRequest(url, init);
}
async function history() {
  const jobs = await rawRequest("/api/operations");
  options.modal(
    "Operações do servidor",
    '<p>Você pode fechar esta janela ou recarregar o navegador. As operações continuam no servidor. Uma operação interrompida por reinício exige conferir os arquivos antes de repetir.</p><div id="operations-list" class="asset-list"></div><button id="operations-refresh">Atualizar</button>',
  );
  $("#operations-refresh").onclick = () =>
    history().catch((e) => options.toast(e.message, true));
  for (const job of jobs) {
    const row = document.createElement("article"),
      info = document.createElement("div"),
      title = document.createElement("strong"),
      detail = document.createElement("small"),
      button = document.createElement("button");
    row.className = "asset-row";
    info.className = "asset-info";
    title.textContent = labels[job.kind] || job.kind;
    detail.textContent =
      job.status +
      " · " +
      (job.error || job.step) +
      " · " +
      new Date(job.updated_at).toLocaleString("pt-BR");
    info.append(title, detail);
    button.textContent =
      job.status === "succeeded" ? "Ver resultado" : "Consultar";
    button.onclick = async () => {
      try {
        const current = await rawRequest("/api/operations/" + job.id);
        if (current.status === "succeeded" && renderers.has(current.kind))
          return await renderers.get(current.kind)(current.result);
        options.modal(
          "Resultado da operação",
          '<p id="operation-result-step"></p><pre id="operation-result-data" class="tool-log"></pre>',
        );
        $("#operation-result-step").textContent = current.error || current.step;
        $("#operation-result-data").textContent = current.result
          ? JSON.stringify(current.result, null, 2)
          : "Consulte novamente para acompanhar o andamento.";
      } catch (e) {
        options.toast(e.message, true);
      }
    };
    row.append(info, button);
    $("#operations-list").append(row);
  }
  if (!jobs.length)
    $("#operations-list").textContent = "Nenhuma operação registrada.";
}
export function setupOperations(config) {
  options = config;
  panel = document.createElement("button");
  panel.id = "server-operations";
  panel.textContent = "Operações";
  panel.onclick = () => history().catch((e) => options.toast(e.message, true));
  document.querySelector(".header-actions, header")?.append(panel);
  if (!panel.isConnected) document.body.append(panel);
  floating = document.createElement("aside");
  floating.className = "operation-card";
  floating.hidden = true;
  floating.setAttribute("role", "status");
  floating.innerHTML =
    '<div><strong id="operation-name"></strong><button id="operation-hide" aria-label="Ocultar progresso">×</button></div><p id="operation-step"></p><progress id="operation-progress" max="100" value="0"></progress><small id="operation-time"></small><button id="operation-history">Ver operações</button>';
  document.body.append(floating);
  $("#operation-hide").onclick = () => (floating.hidden = true);
  $("#operation-history").onclick = () =>
    history().catch((e) => options.toast(e.message, true));
  rawRequest("/api/operations")
    .then((jobs) => {
      for (const job of jobs.filter((j) =>
        ["queued", "running"].includes(j.status),
      ))
        watch(job.id).catch((e) => options.toast(e.message, true));
    })
    .catch(() => {});
  return { show: history, last: () => lastJob };
}
