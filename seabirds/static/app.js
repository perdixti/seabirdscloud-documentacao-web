import { MarkdownEditor } from "./editor.js";
import { openTableBuilder } from "./table-editor.js";
import { setupWorkspace, updateWorkspace, openSettings } from "./workspace.js";
import { ImageManager } from "./image-manager.js";
import { renderProjectHistory } from "./project-history.js";
import { GitHubPublication } from "./github.js";
import { SiteManager } from "./site-manager.js";
import { openProjectCatalog } from "./catalog.js";
import {
  request,
  setupOperations,
  registerOperationResult,
} from "./operations.js";
import { ManagementUI } from "./management.js";
import { TextReviewer } from "./text-review.js";

const $ = (selector) => document.querySelector(selector);
const optionsDefault = {
  links: true,
  tables: true,
  table_cards: true,
  code_cards: true,
  copy_buttons: true,
  raw_html: true,
};
const generationDefault = {
  template_path: "",
  output_path: "",
  images_dir: "",
  image_web_path: "imagens",
  image_index: 0,
  site_dir: "",
  github_repository_path: "",
  history_interval: 60,
  history_limit: 10,
};
const state = {
  id: null,
  version: 0,
  template: "",
  generation: { ...generationDefault },
  options: { ...optionsDefault },
  dirty: false,
  tick: 0,
  config: null,
  view: null,
};
let saving,
  autoTimer,
  previewTimer,
  toastTimer,
  previewSequence = 0,
  pendingImages = 0,
  imageQueue = Promise.resolve();
const editor = new MarkdownEditor($("#editor"), markDirty);
const generationFields = {
  template_path: "template-path",
  output_path: "output-path",
  images_dir: "images-dir",
  image_web_path: "image-web-path",
  image_index: "image-index",
  site_dir: "site-dir",
  github_repository_path: "github-repo-path",
};
const images = new ImageManager({
  api,
  editor,
  data,
  modal,
  toast,
  changed: markDirty,
  setImages: (records) => (state.generation.images = records),
  pickFolder: (target) => pick("images", target),
});
const githubPublication = new GitHubPublication({
  api,
  data,
  modal,
  toast,
  generate,
  save: saveAll,
  repository: () => $("#github-repo-path").value.trim(),
  setRepository: (path) => {
    if ($("#github-repo-path").value !== path) {
      $("#github-repo-path").value = path;
      markDirty();
    }
  },
  pickFolder: (target) => pick("folder", target),
});
async function openDocument(doc) {
  await imageQueue;
  if (state.dirty || state.id) await saveAll();
  fill(doc);
  markDirty();
  document.querySelector('[data-tab="editor-tab"]').click();
}
const management = new ManagementUI({
  api,
  modal,
  toast,
  getRoot: () =>
    $("#site-directory").value.trim() ||
    $("#site-dir").value.trim() ||
    $("#github-repo-path").value.trim(),
  getTemplate: () => $("#template-path").value.trim(),
  pickFolder: (target) => pick("folder", target),
  pickTemplate: (target) => pick("template", target),
  pickImage: (target) => pick("image", target),
  openDocument,
  getDocument: data,
  setMetadata: (metadata) => {
    Object.assign(state.generation, metadata);
    for (const [key, value] of Object.entries(metadata))
      if (generationFields[key]) $("#" + generationFields[key]).value = value;
    markDirty();
  },
  saveDraft: saveAll,
  afterRestore: () => {
    clearInterval(autoTimer);
    state.dirty = false;
    forget(draftKey());
    location.reload();
  },
});
const reviewer = new TextReviewer({
  api,
  modal,
  toast,
  editor,
  getText: () => $("#editor").value,
  getMode: () => state.generation.review_mode || "suggest",
  setMode: (mode) => {
    state.generation.review_mode = mode;
    markDirty();
  },
});
registerOperationResult("github.review", (result) => {
  githubPublication.mode = "document";
  githubPublication.renderReview(result);
});
registerOperationResult("github.review-site", (result) => {
  githubPublication.mode = "site";
  githubPublication.siteDirectory = result.site_root;
  githubPublication.renderReview(result);
});
registerOperationResult("github.publish", (result) =>
  githubPublication.result(result),
);
registerOperationResult("github.retry", (result) =>
  githubPublication.result(result),
);
new SiteManager({
  api,
  modal,
  toast,
  repository: () =>
    $("#github-repo-path").value.trim() || $("#site-dir").value.trim(),
  pickFolder: (target) => pick("folder", target),
  publishSite: (root) => githubPublication.reviewSite(root),
  configureGitHub: (root, afterSave, onBack) =>
    githubPublication.configure(root, afterSave, onBack),
  openCatalog: (root) =>
    openProjectCatalog({
      api,
      modal,
      root,
      publishSite: (value) => githubPublication.reviewSite(value),
    }),
  newDocument: (root) => management.wizard(root),
  openSource: async (root, path) => {
    const doc = await api("/api/site/documents/source", {
      method: "POST",
      body: JSON.stringify({ root, path }),
    });
    await openDocument(doc);
  },
});

function toast(message, error = false) {
  const target = $("#toast");
  target.textContent = message;
  target.hidden = false;
  target.classList.toggle("error", error);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (target.hidden = true), error ? 9000 : 4500);
}
async function guarded(action) {
  try {
    return await action();
  } catch (error) {
    toast(error.message, true);
  }
}
function on(selector, action) {
  $(selector).addEventListener("click", () => guarded(action));
}
async function api(url, options = {}) {
  return request(url, options);
}
function data() {
  const generation = { ...state.generation };
  const previousOutput = generation.output_path;
  for (const [field, id] of Object.entries(generationFields))
    generation[field] =
      field === "image_index"
        ? Math.max(0, Number($("#" + id).value) || 0)
        : $("#" + id).value.trim();
  if (generation.output_path !== previousOutput) generation.output_version = "";
  return {
    title: $("#title").value.trim() || "Documentação",
    markdown: $("#editor").value,
    template: state.template,
    options: { ...state.options },
    generation,
    version: state.version,
  };
}
function draftKey() {
  return `seabirds-generator:${state.id || "new"}`;
}
function remember() {
  try {
    localStorage.setItem(draftKey(), JSON.stringify(data()));
  } catch {}
}
function forget(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}
function markDirty() {
  state.dirty = true;
  state.tick++;
  state.view = null;
  remember();
  updateViewLink();
  $("#save-status").textContent = "Alterações pendentes no rascunho";
  if ($("#generation-result").classList.contains("success")) {
    $("#generation-result").classList.remove("success");
    $("#generation-result").textContent =
      "Rascunho alterado. Gere o HTML para atualizar o arquivo.";
  }
  scheduleAuto();
  schedulePreview();
  updateCounts();
  updateWorkspace(true);
  images.render();
  reviewer.changed();
}
function scheduleAuto(restart = false) {
  if (autoTimer && !restart) return;
  clearInterval(autoTimer);
  autoTimer = setInterval(() => {
    if (state.dirty && !saving) guarded(saveAll);
  }, state.generation.history_interval * 1000);
}
function updateCounts() {
  const text = $("#editor").value.trim();
  $("#word-count").textContent =
    `${text ? text.split(/\s+/).length : 0} palavras`;
  const lines = $("#editor")
    .value.slice(0, $("#editor").selectionStart)
    .split("\n");
  $("#cursor-position").textContent =
    `Ln ${lines.length}, Col ${lines.at(-1).length + 1}`;
}
async function saveOnce() {
  if (saving) return saving;
  if (!state.dirty && state.id) return;
  const snapshot = data(),
    tick = state.tick,
    key = draftKey();
  $("#save-status").textContent = "Salvando histórico…";
  saving = (async () => {
    const result = await api(
      state.id ? `/api/documents/${state.id}` : "/api/documents",
      { method: state.id ? "PUT" : "POST", body: JSON.stringify(snapshot) },
    );
    state.id = result.id;
    state.version = result.version;
    if (tick === state.tick) {
      state.generation = { ...state.generation, ...snapshot.generation };
      state.dirty = false;
      forget(key);
      forget(draftKey());
      $("#save-status").textContent = "Rascunho salvo no histórico";
      updateWorkspace(false);
    } else {
      forget(key);
      remember();
    }
    await api("/api/generator/snapshot", {
      method: "POST",
      body: JSON.stringify({ ...snapshot, version: result.version }),
    });
  })();
  try {
    await saving;
  } catch (error) {
    remember();
    $("#save-status").textContent = "Rascunho não salvo — confira o aviso";
    throw error;
  } finally {
    saving = null;
  }
}
async function saveAll() {
  await imageQueue;
  await saveOnce();
  while (state.dirty) await saveOnce();
}
function fill(doc) {
  clearInterval(autoTimer);
  autoTimer = null;
  state.id = doc.id || null;
  state.version = doc.version || 0;
  state.template = doc.template || "";
  state.options = { ...optionsDefault, ...doc.options };
  state.generation = { ...generationDefault, ...doc.generation };
  if (!state.generation.template_path && !doc.template)
    state.generation.template_path = state.config.template_path;
  $("#title").value = doc.title || "Documentação";
  editor.reset(doc.markdown || "");
  for (const [key, id] of Object.entries(generationFields))
    $("#" + id).value = state.generation[key];
  updateViewLink();
  state.dirty = false;
  state.tick++;
  state.view = null;
  $("#image-thumbnails").replaceChildren();
  images.load(state.generation.images || []);
  $("#save-status").textContent = state.id
    ? "Rascunho aberto"
    : "Pronto para editar";
  $("#generation-result").textContent =
    "Clique em Gerar HTML para gravar o arquivo de saída.";
  $("#generation-result").classList.remove("success");
  renderOptions();
  templateStatus();
  reviewer.reset();
  reviewer.changed();
  scheduleAuto(true);
  schedulePreview();
  updateCounts();
  updateWorkspace(false);
}
function recover() {
  try {
    const previousKey = `seabirds-draft:${state.id || "new"}`;
    const raw =
      localStorage.getItem(draftKey()) || localStorage.getItem(previousKey);
    if (!raw) return;
    const draft = JSON.parse(raw);
    if (confirm("Recuperar o rascunho local que ainda não foi salvo?")) {
      fill({ ...draft, id: state.id, version: state.version });
      markDirty();
      forget(previousKey);
    } else {
      forget(draftKey());
      forget(previousKey);
    }
  } catch {}
}
function renderOptions() {
  const labels = {
    links: "Links como botões",
    table_cards: "Tabelas em cards (tablecard)",
    tables: "Tabelas Markdown (table)",
    copy_buttons: "Botão para copiar código",
    code_cards: "Blocos de código em cards",
    raw_html: "Permitir HTML no Markdown",
  };
  const container = $("#generation-options");
  container.replaceChildren();
  for (const [key, text] of Object.entries(labels)) {
    const label = document.createElement("label"),
      input = document.createElement("input");
    input.type = "checkbox";
    input.checked = state.options[key];
    input.dataset.option = key;
    input.onchange = () => {
      state.options[key] = input.checked;
      markDirty();
    };
    label.append(input, document.createTextNode(text));
    container.append(label);
  }
}
function templateStatus() {
  $("#template-status").textContent = $("#template-path").value
    ? "Template: " + $("#template-path").value
    : state.template
      ? "Template enviado pelo navegador"
      : "Template original do projeto";
}
function schedulePreview() {
  clearTimeout(previewTimer);
  const sequence = ++previewSequence;
  previewTimer = setTimeout(() => refreshPreview(sequence, false), 700);
}
async function refreshPreview(sequence = ++previewSequence, notify = true) {
  $("#preview-status").textContent = "Atualizando a prévia…";
  try {
    const result = await api("/api/generator/preview", {
      method: "POST",
      body: JSON.stringify(data()),
    });
    if (sequence !== previewSequence) return;
    $("#preview").src = result.url;
    showPreviewLocation(result);
    if (notify) toast("Prévia atualizada.");
  } catch (error) {
    if (sequence === previewSequence) {
      $("#preview-status").textContent = error.message;
      if (notify) toast(error.message, true);
    }
  }
}
function showPreviewLocation(result) {
  const missing = result.missing_stylesheets || [];
  $("#preview-status").textContent = missing.length
    ? "CSS não encontrado: " +
      missing.join(", ") +
      ". Confira o caminho ou selecione a raiz do site."
    : "Prévia do site · " + (result.site_root || "");
  if (!$("#site-dir").value && result.site_root)
    $("#site-dir").placeholder =
      "Detectada automaticamente: " + result.site_root;
}
function modal(title, html) {
  $("#modal").classList.remove("html-editor-modal");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
}
function blobDownload(blob, name) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function pick(kind, target) {
  if (!state.config.native_dialogs) {
    return pickServer(kind, target);
  }
  const result = await api(`/api/generator/pick/${kind}`, { method: "POST" });
  if (!result.supported) {
    state.config.native_dialogs = false;
    return pickServer(kind, target);
  }
  if (result.path && target) {
    target.value = result.path;
    markDirty();
  }
  return !!result.path;
}
function pickServer(kind, target) {
  const fileMode = ["template", "output", "markdown", "image"].includes(kind);
  modal(
    fileMode
      ? "Selecionar arquivo na máquina do aplicativo"
      : "Selecionar pasta na máquina do aplicativo",
    `<p>Informe o caminho da máquina que executa o aplicativo. Você pode digitar a pasta completa e clicar em Selecionar.</p><div class="path-input"><input id="browse-path" aria-label="Caminho da pasta"><button id="browse-go">Ir</button><button id="browse-parent">Pasta acima</button></div><p id="browse-status" class="field-hint" role="status"></p><div id="browse-list" class="history-list file-picker"></div><div class="path-input"><input id="browse-new-dir" placeholder="Nome de nova pasta" aria-label="Nome de nova pasta"><button id="browse-create">Criar pasta</button></div><label id="browse-name-label">Nome do arquivo<input id="browse-name"></label><div class="modal-actions"><button id="browse-select" class="primary">Selecionar</button></div>`,
  );
  $("#browse-name-label").hidden = !fileMode;
  $("#browse-name").value = fileMode
    ? target?.value.split(/[\\/]/).at(-1) ||
      (kind === "output" ? "documentacao.html" : "")
    : "";
  return new Promise((resolve) => {
    let current = "",
      parent = "",
      loading = 0,
      closed = false;
    $("#modal").addEventListener(
      "close",
      () => {
        closed = true;
        loading++;
        resolve(false);
      },
      { once: true },
    );
    async function load(path) {
      const sequence = ++loading;
      $("#browse-status").textContent = "Abrindo pasta…";
      let result;
      try {
        result = await api("/api/generator/browse", {
          method: "POST",
          body: JSON.stringify({ path, kind }),
        });
      } catch (error) {
        if (!closed && sequence === loading) {
          current = "";
          $("#browse-list").replaceChildren();
          $("#browse-status").textContent = error.message;
        }
        throw error;
      }
      if (closed || sequence !== loading) return false;
      current = result.path;
      parent = result.parent;
      $("#browse-path").value = current;
      $("#browse-status").textContent =
        result.access?.writable === false
          ? "Somente leitura para o usuário " +
            result.access.user +
            ". A pasta pode ser selecionada para visualização; o administrador precisa liberar a escrita para editar."
          : "Pasta aberta: " + current;
      if (result.skipped)
        $("#browse-status").textContent +=
          " · " + result.skipped + " entrada(s) sem acesso.";
      const list = $("#browse-list");
      list.replaceChildren();
      for (const entry of result.entries) {
        const button = document.createElement("button");
        button.textContent = (entry.directory ? "▸ " : "▧ ") + entry.name;
        button.onclick = () =>
          guarded(async () => {
            if (entry.directory) await load(entry.path);
            else $("#browse-name").value = entry.name;
          });
        list.append(button);
      }
      if (!list.children.length) list.textContent = "Pasta vazia.";
      return true;
    }
    on("#browse-go", () => load($("#browse-path").value));
    on("#browse-parent", () => load(parent));
    $("#browse-path").oninput = () => {
      loading++;
    };
    $("#browse-path").onkeydown = (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        guarded(() => load($("#browse-path").value));
      }
    };
    on("#browse-create", async () => {
      if (!(await load($("#browse-path").value))) return;
      const name = $("#browse-new-dir").value.trim();
      if (!name || /[\\/]/.test(name) || name === "." || name === "..")
        throw Error("Informe apenas o nome da nova pasta.");
      const result = await api("/api/generator/mkdir", {
        method: "POST",
        body: JSON.stringify({
          path: current.replace(/[\\/]+$/, "") + "/" + name,
        }),
      });
      $("#browse-new-dir").value = "";
      await load(result.path);
    });
    on("#browse-select", async () => {
      if (!(await load($("#browse-path").value))) return;
      if (!current) throw Error("Selecione uma pasta.");
      let path = current;
      if (fileMode) {
        const name = $("#browse-name").value.trim();
        if (!name || /[\\/]/.test(name) || name === "." || name === "..")
          throw Error("Selecione ou informe o nome do arquivo.");
        path = current.replace(/[\\/]+$/, "") + "/" + name;
      }
      target.value = path;
      markDirty();
      resolve(true);
      $("#modal").close();
    });
    guarded(async () => {
      let initial = target?.value || "";
      if (fileMode && initial) initial = initial.replace(/[^\\/]+$/, "");
      $("#browse-path").value = initial;
      try {
        await load(initial);
      } catch (error) {
        if (initial) {
          await load("");
          $("#browse-status").textContent =
            "O caminho salvo não foi encontrado neste servidor. Informe a pasta correta.";
        } else throw error;
      }
    });
  });
}
async function loadTemplate() {
  const path = $("#template-path").value.trim();
  if (!path) {
    templateStatus();
    markDirty();
    return;
  }
  const result = await api("/api/generator/template", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
  state.template = result.template;
  $("#template-path").value = result.path;
  templateStatus();
  markDirty();
}
async function generate() {
  if (!$("#output-path").value.trim()) {
    await pick("output", $("#output-path"));
    if (!$("#output-path").value.trim())
      throw Error("Selecione ou informe o arquivo HTML de saída.");
  }
  await saveAll();
  const requested = data();
  $("#generation-result").classList.remove("success");
  $("#generation-result").textContent = "Gerando HTML…";
  let result;
  try {
    result = await api("/api/generator/generate", {
      method: "POST",
      body: JSON.stringify(requested),
    });
  } catch (error) {
    $("#generation-result").textContent =
      "Não foi possível confirmar a geração. Consulte Operações: " +
      error.message;
    throw error;
  }
  if (data().generation.output_path !== requested.generation.output_path) {
    toast(
      "HTML gerado em " +
        result.path +
        ". O destino atual foi alterado durante a operação.",
    );
    return;
  }
  const context = Object.fromEntries(
    Object.entries(result.context || {}).filter(
      ([key]) => data().generation[key] === requested.generation[key],
    ),
  );
  if (result.output_version || Object.keys(context).length) {
    Object.assign(state.generation, context);
    for (const [key, value] of Object.entries(context))
      if (generationFields[key]) $("#" + generationFields[key]).value = value;
    if (result.output_version)
      state.generation.output_version = result.output_version;
    markDirty();
    await saveAll();
  }
  state.view = result.url;
  $("#preview").src = result.url;
  showPreviewLocation(result);
  $("#generation-result").textContent = "HTML gerado em: " + result.path;
  $("#generation-result").classList.add("success");
  toast("HTML gerado em " + result.path);
}
async function uploadImage(file) {
  if (!file) return;
  if (!$("#images-dir").value.trim()) {
    openSettings("images-dir");
    throw Error("Selecione a pasta de imagens antes de colar.");
  }
  if (file.size > 10 * 1024 * 1024) throw Error("A imagem deve ter até 10 MB.");
  const form = new FormData();
  form.append("file", file);
  form.append("generation", JSON.stringify(data().generation));
  const result = await api("/api/generator/image", {
    method: "POST",
    body: form,
  });
  $("#image-index").value = result.next_index;
  images.add(result.attachment);
  editor.replace("\n" + result.markdown + "\n");
  toast("Imagem salva em " + result.path);
}
function queueImage(file) {
  pendingImages++;
  imageQueue = imageQueue
    .then(() => uploadImage(file))
    .catch((error) => toast(error.message, true))
    .finally(() => pendingImages--);
  return imageQueue;
}
function showTable(mode) {
  openTableBuilder(mode, modal, (text) => editor.replace(text));
}

document.querySelectorAll("[data-tab]").forEach((button) =>
  button.addEventListener("click", () => {
    document
      .querySelectorAll("[data-tab]")
      .forEach((item) => item.classList.toggle("active", item === button));
    document
      .querySelectorAll(".tab-page")
      .forEach((page) => (page.hidden = page.id !== button.dataset.tab));
  }),
);
document
  .querySelectorAll("[data-command]")
  .forEach((button) =>
    button.addEventListener("click", () =>
      editor.command(button.dataset.command),
    ),
  );
for (const id of ["title", ...Object.values(generationFields)])
  $("#" + id).addEventListener("input", markDirty);
$("#template-path").addEventListener("change", () => guarded(loadTemplate));
$("#editor").addEventListener("keyup", updateCounts);
$("#editor").addEventListener("click", updateCounts);
$("#editor").addEventListener("paste", (event) => {
  const images = [...event.clipboardData.items].filter((item) =>
    item.type.startsWith("image/"),
  );
  if (images.length) {
    event.preventDefault();
    images.forEach((item) => queueImage(item.getAsFile()));
  }
});
$("#editor").addEventListener("dragover", (event) => event.preventDefault());
$("#editor").addEventListener("drop", (event) => {
  const images = [...event.dataTransfer.files].filter((file) =>
    file.type.startsWith("image/"),
  );
  if (images.length) {
    event.preventDefault();
    images.forEach(queueImage);
  }
});
on("#choose-template", async () => {
  if (await pick("template", $("#template-path"))) await loadTemplate();
});
on("#choose-images", () => pick("images", $("#images-dir")));
on("#choose-output", () => pick("output", $("#output-path")));
on("#choose-site", () => pick("site", $("#site-dir")));
on("#choose-github-repo", () => pick("folder", $("#github-repo-path")));
on("#generate", generate);
on("#document-catalog", async () => {
  await imageQueue;
  const document = data();
  const resolved = await api("/api/site/documents/context", {
    method: "POST",
    body: JSON.stringify({
      ...document,
      generation: { ...document.generation, catalog_image: "" },
    }),
  });
  const root = resolved.generation.site_dir;
  for (const key of ["site_dir", "github_repository_path"]) {
    state.generation[key] = resolved.generation[key];
    $("#" + generationFields[key]).value = resolved.generation[key];
  }
  markDirty();
  await openProjectCatalog({
    api,
    modal,
    root,
    publishSite: (value) => githubPublication.reviewSite(value),
    draft: {
      title: document.title,
      output_path: document.generation.output_path,
      image_path:
        document.generation.catalog_image ||
        document.generation.images?.[0]?.path ||
        "",
    },
  });
});
on("#refresh-preview", () => refreshPreview());
function updateViewLink() {
  const path = $("#output-path").value.trim().replace(/\\/g, "/");
  const escaped = encodeURI(path).replace(/#/g, "%23").replace(/\?/g, "%3F");
  $("#view-html").href = /^[A-Za-z]:\//.test(path)
    ? "file:///" + escaped
    : path.startsWith("//")
      ? "file:" + escaped
      : path.startsWith("/")
        ? "file://" + escaped
        : "#";
}
async function viewOutput() {
  if (!$("#output-path").value.trim())
    throw Error("Informe o arquivo HTML de saída.");
  if (state.config.local_file_open) {
    await api("/api/generator/open-local", {
      method: "POST",
      body: JSON.stringify({ path: $("#output-path").value.trim() }),
    });
    return;
  }
  const tab = window.open("about:blank", "_blank");
  try {
    const result = await api("/api/generator/open-output", {
      method: "POST",
      body: JSON.stringify(data()),
    });
    state.view = result.url;
    $("#preview").src = result.url;
    if (tab) {
      tab.opener = null;
      tab.location.href = result.url;
    }
  } catch (error) {
    tab?.close();
    throw error;
  }
}
$("#view-html").addEventListener("click", (event) => {
  event.preventDefault();
  guarded(viewOutput);
});
on("#download-html", async () => {
  await imageQueue;
  const response = await fetch("/api/generator/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data()),
  });
  if (!response.ok) {
    const error = await response.json();
    throw Error(error.detail || "Não foi possível gerar o HTML.");
  }
  const name =
    $("#output-path").value.split(/[\\/]/).at(-1) || "documentacao.html";
  blobDownload(
    await response.blob(),
    /\.html?$/i.test(name) ? name : "documentacao.html",
  );
  toast("Download do arquivo HTML iniciado.");
});
on("#save-markdown", () =>
  blobDownload(
    new Blob([$("#editor").value], { type: "text/markdown;charset=utf-8" }),
    "documentacao.md",
  ),
);
on("#new-project", () => management.wizard());
on("#open-markdown", () => $("#markdown-file").click());
$("#markdown-file").addEventListener("change", () =>
  guarded(async () => {
    const file = $("#markdown-file").files[0];
    if (!file) return;
    if (file.size > 1_000_000) throw Error("Markdown excede 1 MB.");
    if (state.dirty || state.id) await saveAll();
    fill({
      title: file.name.replace(/\.[^.]+$/, ""),
      markdown: await file.text(),
    });
    markDirty();
    $("#markdown-file").value = "";
  }),
);
on("#import-template", () => $("#template-file").click());
$("#template-file").addEventListener("change", () =>
  guarded(async () => {
    const file = $("#template-file").files[0];
    if (!file) return;
    if (file.size > 250_000) throw Error("Template excede 250 KB.");
    const template = await file.text();
    if (!template.includes("{{content}}"))
      throw Error("O template precisa conter {{content}}.");
    state.template = template;
    $("#template-path").value = "";
    templateStatus();
    markDirty();
    $("#template-file").value = "";
    toast("Template HTML selecionado.");
  }),
);
on("#upload-image", () => {
  if (!$("#images-dir").value.trim()) {
    openSettings("images-dir");
    throw Error("Selecione a pasta de imagens primeiro.");
  }
  $("#image-file").click();
});
$("#image-file").addEventListener("change", () => {
  queueImage($("#image-file").files[0]);
  $("#image-file").value = "";
});
on("#insert-table", () => showTable("table"));
on("#insert-tablecard", () => showTable("tablecard"));
on("#close-modal", () => $("#modal").close());
$("#modal").addEventListener("click", (event) => {
  if (event.target !== $("#modal")) return;
  const bounds = $("#modal").getBoundingClientRect();
  if (
    event.clientX < bounds.left ||
    event.clientX > bounds.right ||
    event.clientY < bounds.top ||
    event.clientY > bounds.bottom
  )
    $("#modal").close();
});
on("#theme", () => {
  const theme =
    document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("seabirds-generator-theme", theme);
  } catch {}
});

let matches = [],
  matchIndex = -1;
function searchText(reset = true) {
  const term = $("#find-text").value.toLocaleLowerCase(),
    text = $("#editor").value.toLocaleLowerCase();
  matches = [];
  if (term) {
    let from = 0;
    while (from <= text.length) {
      const index = text.indexOf(term, from);
      if (index < 0) break;
      matches.push(index);
      from = index + Math.max(1, term.length);
    }
  }
  if (reset) matchIndex = matches.length ? 0 : -1;
  $("#find-count").textContent = `${matchIndex + 1}/${matches.length}`;
  if (matchIndex >= 0) {
    $("#editor").setSelectionRange(
      matches[matchIndex],
      matches[matchIndex] + term.length,
    );
    const line = $("#editor")
      .value.slice(0, matches[matchIndex])
      .split("\n").length;
    $("#editor").scrollTop = Math.max(0, (line - 5) * 23);
  }
}
function showFind() {
  $("#find-bar").hidden = false;
  $("#find-text").focus();
  $("#find-text").select();
}
on("#find", showFind);
$("#find-text").addEventListener("input", () => searchText());
on("#find-next", () => {
  if (!matches.length) return;
  matchIndex = (matchIndex + 1) % matches.length;
  searchText(false);
});
on("#find-prev", () => {
  if (!matches.length) return;
  matchIndex = (matchIndex + matches.length - 1) % matches.length;
  searchText(false);
});
on("#find-close", () => {
  $("#find-bar").hidden = true;
  $("#editor").focus();
});

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase(),
    modifier = event.ctrlKey || event.metaKey;
  if (modifier && key === "s" && !$("#editor-tab").hidden) {
    event.preventDefault();
    guarded(generate);
    return;
  }
  if (event.target !== $("#editor")) return;
  if (key === "tab") {
    event.preventDefault();
    editor.replace("    ");
    return;
  }
  if (!modifier) return;
  const actions = {
    b: () => editor.command("bold"),
    i: () => editor.command("italic"),
    n: () => editor.command("inline"),
    p: () => editor.command("code"),
    h: () => editor.command("heading1"),
    j: () => editor.command("heading2"),
    k: () => editor.command("heading3"),
    l: () => editor.command("heading4"),
    d: () => editor.command("dash"),
    e: () => editor.command("numbered"),
    t: () => showTable("table"),
    r: () => showTable("tablecard"),
    f: showFind,
    z: () => editor.command(event.shiftKey ? "redo" : "undo"),
    y: () => editor.command("redo"),
  };
  if (actions[key]) {
    event.preventDefault();
    actions[key]();
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty || saving || pendingImages) {
    remember();
    event.preventDefault();
    event.returnValue = "";
  }
});

on("#history-settings", () => {
  modal(
    "Configurações de histórico",
    '<div class="stack"><label>Frequência de salvamento (segundos)<input id="history-interval" type="number" min="1" max="86400"></label><label>Quantidade máxima de versões por projeto<input id="history-limit" type="number" min="1" max="1000"></label></div><div class="modal-actions"><button id="save-history-settings" class="primary">Salvar configurações</button></div>',
  );
  $("#history-interval").value = state.generation.history_interval;
  $("#history-limit").value = state.generation.history_limit;
  on("#save-history-settings", async () => {
    const interval = Number($("#history-interval").value),
      limit = Number($("#history-limit").value);
    if (
      !Number.isInteger(interval) ||
      interval < 1 ||
      interval > 86400 ||
      !Number.isInteger(limit) ||
      limit < 1 ||
      limit > 1000
    )
      throw Error("Informe frequência e quantidade válidas.");
    state.generation.history_interval = interval;
    state.generation.history_limit = limit;
    scheduleAuto(true);
    markDirty();
    await saveAll();
    $("#modal").close();
    toast("Configurações de histórico salvas.");
  });
});
on("#history", async () => {
  await saveAll();
  const history = await api(`/api/documents/${state.id}/history`);
  modal(
    "Histórico do projeto atual",
    '<p>Selecione uma versão para restaurar. O arquivo HTML só será alterado quando você gerar novamente.</p><div id="current-history" class="history-list"></div>',
  );
  for (const version of history) {
    const button = document.createElement("button"),
      title = document.createElement("span"),
      date = document.createElement("small");
    title.textContent = "Versão " + version.version;
    date.textContent = new Date(version.created_at).toLocaleString("pt-BR");
    button.append(title, date);
    button.onclick = () =>
      guarded(async () => {
        if (!confirm("Restaurar esta versão no editor?")) return;
        await saveAll();
        const old = await api(
          `/api/documents/${state.id}/history/${version.id}`,
        );
        fill({ ...old, id: state.id, version: state.version });
        markDirty();
        await saveAll();
        $("#modal").close();
      });
    $("#current-history").append(button);
  }
});
on("#all-history", async () => {
  if (state.dirty) await saveAll();
  const [projects, legacy] = await Promise.all([
    api("/api/documents"),
    api("/api/generator/legacy-history"),
  ]);
  modal(
    "Históricos de projetos",
    '<label>Filtrar<input id="project-filter" placeholder="Nome ou caminho"></label><h3>Projetos recentes</h3><div id="project-list" class="history-list"></div><h3>Autosaves Markdown (incluindo a aplicação antiga)</h3><div id="legacy-list" class="history-list"></div>',
  );
  renderProjectHistory({
    projects,
    autosaves: legacy,
    onProject: (project) =>
      guarded(async () => {
        if (state.dirty) await saveAll();
        fill(await api(`/api/documents/${project.id}`));
        $("#modal").close();
        recover();
      }),
    onAutosave: (item) =>
      guarded(async () => {
        if (state.dirty) await saveAll();
        const text = await api("/api/generator/read-markdown", {
          method: "POST",
          body: JSON.stringify({ path: item.path }),
        });
        fill({ title: item.project, markdown: text.markdown });
        markDirty();
        $("#modal").close();
      }),
  });
});

document
  .querySelectorAll("[data-pick-folder]")
  .forEach(
    (button) =>
      (button.onclick = () =>
        guarded(() => pick("folder", $("#" + button.dataset.pickFolder)))),
  );
async function scanTool(prefix, operation) {
  const payload = {
    folder: $("#" + prefix + "-folder").value.trim(),
    operation,
    old: prefix === "replace" ? $("#replace-old").value : "",
    new: prefix === "replace" ? $("#replace-new").value : "",
  };
  const result = await api("/api/generator/scan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const target = $("#" + prefix + "-results");
  target.replaceChildren();
  target.className = "scan-results";
  const controls = document.createElement("div");
  controls.className = "scan-controls";
  const filter = document.createElement("input");
  filter.placeholder = "Filtrar arquivos";
  filter.setAttribute("aria-label", "Filtrar arquivos encontrados");
  const all = document.createElement("button"),
    none = document.createElement("button");
  all.textContent = "Marcar todos";
  none.textContent = "Desmarcar todos";
  controls.append(filter, all, none);
  target.append(controls);
  const list = document.createElement("div");
  list.className = "scan-list";
  const inputs = [];
  for (const file of result.files) {
    const label = document.createElement("label"),
      checkbox = document.createElement("input"),
      name = document.createElement("span"),
      count = document.createElement("small");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.value = file.name;
    name.textContent = file.name;
    count.textContent =
      operation === "replace" ? file.count + " ocorrência(s)" : "";
    label.append(checkbox, name, count);
    list.append(label);
    inputs.push(checkbox);
  }
  target.append(list);
  filter.oninput = () =>
    inputs.forEach(
      (input) =>
        (input.parentElement.hidden = !input.value
          .toLocaleLowerCase()
          .includes(filter.value.toLocaleLowerCase())),
    );
  all.onclick = () =>
    inputs
      .filter((input) => !input.parentElement.hidden)
      .forEach((input) => (input.checked = true));
  none.onclick = () =>
    inputs
      .filter((input) => !input.parentElement.hidden)
      .forEach((input) => (input.checked = false));
  $("#" + prefix + "-log").textContent = [
    `${result.files.length} arquivo(s) encontrado(s).`,
    ...result.errors,
  ].join("\n");
  if (!result.files.length) return;
  const apply = document.createElement("button");
  apply.className = "primary";
  apply.textContent =
    operation === "replace"
      ? "Aplicar substituição nos selecionados"
      : "Formatar arquivos selecionados";
  apply.id = prefix + "-apply";
  apply.onclick = () =>
    guarded(async () => {
      const selected = inputs
        .filter((input) => input.checked)
        .map((input) => input.value);
      if (!selected.length) throw Error("Selecione ao menos um arquivo.");
      if (
        !confirm(
          `Alterar ${selected.length} arquivo(s) na pasta selecionada? Uma cópia anterior será preservada.`,
        )
      )
        return;
      apply.disabled = true;
      try {
        const done = await api("/api/generator/apply", {
          method: "POST",
          body: JSON.stringify({ token: result.token, selected }),
        });
        $("#" + prefix + "-log").textContent = done.changed
          .map(
            (file) => `Alterado: ${file.path}\nCópia anterior: ${file.backup}`,
          )
          .join("\n\n");
        toast(`${done.changed.length} arquivo(s) alterado(s).`);
      } finally {
        apply.disabled = false;
      }
    });
  target.append(apply);
}
on("#replace-scan", () => scanTool("replace", "replace"));
on("#format-scan", () => scanTool("format", "format"));

setupWorkspace();
setupOperations({ modal, toast });
guarded(async () => {
  try {
    document.documentElement.dataset.theme =
      localStorage.getItem("seabirds-generator-theme") || "light";
  } catch {}
  state.config = await api("/api/generator/config");
  $("#environment-label").textContent = state.config.local_file_open
    ? "Neste computador"
    : "Servidor conectado";
  $("#path-note").textContent = state.config.native_dialogs
    ? "Os seletores abrem pastas e arquivos desta máquina. No LXC, informe os caminhos do servidor."
    : "Os caminhos são da máquina que executa o aplicativo. No LXC, use caminhos Linux ou um diretório montado.";
  const projects = await api("/api/documents");
  if (projects.length) fill(await api(`/api/documents/${projects[0].id}`));
  else fill({});
  recover();
});
