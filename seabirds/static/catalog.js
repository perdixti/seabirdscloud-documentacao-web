const $ = (selector) => document.querySelector(selector);
const fields = ["categoria", "titulo", "imagem", "descricao", "link"];

export class ProjectCatalog {
  constructor(options) {
    Object.assign(this, options);
    this.form = {};
    this.entryId = "";
    this.dirty = false;
    this.data = null;
    this.closed = false;
  }
  post(action, body) {
    return this.api("/api/generator/site/catalog/" + action, {method: "POST", body: JSON.stringify({root: this.root, ...body})});
  }
  async open() {
    this.modal("Catálogo de documentações", '<p id="catalog-loading">Carregando categorias e documentações…</p>');
    const dialog = $("#modal");
    this.onClose = () => {
      this.closed = true;
      this.dirty = false;
      dialog.classList.remove("catalog-modal");
      dialog.removeEventListener("click", this.preventClose, true);
      dialog.removeEventListener("cancel", this.preventClose, true);
      window.removeEventListener("beforeunload", this.unload);
    };
    this.preventClose = (event) => {
      if (this.closed || !this.dirty || !$("#catalog-form")) return;
      const bounds = dialog.getBoundingClientRect();
      const closing = event.type === "cancel" || event.target.closest?.("#close-modal") || (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom));
      if (closing && !this.discard()) {event.preventDefault(); event.stopImmediatePropagation();}
    };
    this.unload = event => {if (!this.closed && this.dirty) {event.preventDefault(); event.returnValue = "";}};
    dialog.addEventListener("close", this.onClose, {once: true});
    dialog.addEventListener("click", this.preventClose, true);
    dialog.addEventListener("cancel", this.preventClose, true);
    window.addEventListener("beforeunload", this.unload);
    await this.load();
  }
  discard() {
    if (this.dirty && !confirm("Descartar as alterações ainda não salvas neste cadastro?")) return false;
    this.dirty = false;
    return true;
  }
  async load(config = {}) {
    this.data = null;
    try {
      this.data = await this.post("read", {...config, ...this.draft});
      if (this.closed) return;
      this.form = {...this.data.prefill};
      this.entryId = "";
      const found = this.entries().find(entry => this.sameLink(entry.link, this.form.link));
      if (found) {this.form = {...found}; this.entryId = found.id;}
      this.dirty = false;
      this.render();
    } catch (error) {
      if (this.closed) return;
      this.render(error.message);
    }
  }
  sameLink(first, second) {
    if (!first || !second) return false;
    const base = new URL(this.data.page, "https://site.invalid/");
    try {return new URL(first, base).href === new URL(second, base).href;} catch {return false;}
  }
  entries() {
    return this.data?.categories.flatMap(category => category.projetos.map(entry => ({...entry, categoria: category.categoria}))) || [];
  }
  readForm() {
    this.form = Object.fromEntries(fields.map(key => [key, $("#catalog-" + key).value]));
    return this.form;
  }
  render(error = "") {
    if (this.closed) return;
    this.modal("Catálogo de documentações",
      '<p>Cadastre os cards exibidos na página de projetos. Ao salvar, a alteração fica na cópia local do site para revisão e publicação.</p><details id="catalog-config"><summary>Arquivo e página do catálogo</summary><div class="stack"><label>Arquivo do catálogo, relativo à raiz do site<input id="catalog-path" placeholder="js/projetos-conteudo.js"></label><label>Página que exibe o catálogo<input id="catalog-page" placeholder="paginas/projetos.html"></label><button id="catalog-load">Carregar catálogo</button></div></details><p id="catalog-error" class="github-notice" role="alert" hidden></p><div class="catalog-columns"><section><div class="catalog-heading"><h3>Documentações cadastradas</h3><button id="catalog-new">Novo cadastro</button></div><input id="catalog-search" placeholder="Buscar por título, categoria ou link" aria-label="Buscar no catálogo"><p id="catalog-count" class="field-hint"></p><div id="catalog-list" class="catalog-list"></div></section><section id="catalog-form"><h3 id="catalog-form-title">Novo cadastro</h3><div class="stack"><label>Categoria<input id="catalog-categoria" list="catalog-categories" maxlength="100" placeholder="Selecione ou digite uma nova categoria"><datalist id="catalog-categories"></datalist></label><label>Título<input id="catalog-titulo" maxlength="200"></label><label>Imagem do card<input id="catalog-imagem" list="catalog-images" placeholder="../imagens/projetos/linux/spnego/logo.png"><datalist id="catalog-images"></datalist></label><label>Descrição<textarea id="catalog-descricao" rows="3" maxlength="2000"></textarea></label><label>Link da documentação<input id="catalog-link" placeholder="../projetos/linux/spnego.html"></label></div><p class="field-hint">Imagem e link são relativos à página que exibe o catálogo. Gere o HTML antes de cadastrar a documentação.</p><details><summary>Ver formato do cadastro</summary><pre id="catalog-code"></pre></details><div class="modal-actions"><button id="catalog-save" class="primary">Salvar no catálogo</button><button id="catalog-remove" class="danger-button" hidden>Remover do catálogo</button></div></section></div><p id="catalog-message" class="field-hint" role="status"></p><div class="modal-actions"><button id="catalog-undo" disabled>Desfazer última alteração</button><button id="catalog-publish">Revisar publicação do site</button></div>');
    $("#modal").classList.add("catalog-modal");
    $("#catalog-path").value = this.data?.path || this.config?.path || "js/projetos-conteudo.js";
    $("#catalog-page").value = this.data?.page || this.config?.page || "paginas/projetos.html";
    for (const key of fields) $("#catalog-" + key).value = this.form[key] || "";
    $("#catalog-form-title").textContent = this.entryId ? "Editar cadastro" : "Novo cadastro";
    $("#catalog-remove").hidden = !this.entryId;
    $("#catalog-save").disabled = !this.data;
    $("#catalog-undo").disabled = !this.data?.can_undo;
    if (error) this.error(error);
    for (const category of this.data?.categories || []) {
      const option = document.createElement("option"); option.value = category.categoria;
      $("#catalog-categories").append(option);
    }
    const images = new Set([this.data?.prefill.imagem, ...this.entries().map(entry => entry.imagem)].filter(Boolean));
    for (const image of images) {const option = document.createElement("option"); option.value = image; $("#catalog-images").append(option);}
    $("#catalog-form").oninput = () => {this.readForm(); this.dirty = true; this.preview();};
    $("#catalog-search").oninput = () => this.draw();
    $("#catalog-new").onclick = () => {if (this.discard()) {this.form = {...this.data?.prefill}; this.entryId = ""; this.render();}};
    $("#catalog-load").onclick = async () => {
      if (!this.discard()) return;
      this.config = {path: $("#catalog-path").value.trim(), page: $("#catalog-page").value.trim()};
      const button = $("#catalog-load"); button.disabled = true;
      try {await this.load(this.config);} finally {button.disabled = false;}
    };
    $("#catalog-save").onclick = () => this.mutate("save");
    $("#catalog-remove").onclick = () => {
      if (confirm("Remover este cadastro do catálogo? O HTML e as imagens permanecerão no site. Você poderá desfazer esta alteração.")) return this.mutate("remove");
    };
    $("#catalog-undo").onclick = () => {if (this.discard()) return this.mutate("undo");};
    $("#catalog-publish").onclick = async () => {
      if (!this.discard()) return;
      const button = $("#catalog-publish"); button.disabled = true;
      try {await this.publishSite(this.root); this.onClose();} catch (failure) {this.render(failure.message);} finally {button.disabled = false;}
    };
    $("#catalog-config").open = !this.data;
    this.draw();
    this.preview();
  }
  error(message) {
    const target = $("#catalog-error");
    if (target) {target.textContent = message; target.hidden = false;}
  }
  draw() {
    const list = $("#catalog-list"); list.replaceChildren();
    const filter = $("#catalog-search").value.toLocaleLowerCase();
    const entries = this.entries().filter(entry => (entry.categoria + " " + entry.titulo + " " + entry.link).toLocaleLowerCase().includes(filter));
    $("#catalog-count").textContent = entries.length + " cadastro(s)" + (entries.length > 500 ? "; refine a busca para mostrar outros." : "");
    const groups = new Map();
    for (const entry of entries.slice(0, 500)) {
      if (!groups.has(entry.categoria)) {
        const group = document.createElement("details"), summary = document.createElement("summary");
        summary.textContent = entry.categoria; group.open = !!filter || entry.categoria === this.form.categoria;
        group.append(summary); list.append(group); groups.set(entry.categoria, group);
      }
      const row = document.createElement("div"), info = document.createElement("div"), title = document.createElement("strong"), link = document.createElement("small"), button = document.createElement("button");
      row.className = "catalog-entry"; title.textContent = entry.titulo; link.textContent = entry.link;
      info.append(title, link); button.textContent = "Editar"; button.setAttribute("aria-label", "Editar cadastro " + entry.titulo);
      button.onclick = () => {if (this.discard()) {this.form = {...entry}; this.entryId = entry.id; this.render();}};
      row.append(info, button); groups.get(entry.categoria).append(row);
    }
    if (!entries.length) list.textContent = "Nenhum cadastro encontrado.";
  }
  preview() {
    const value = this.form;
    $("#catalog-code").textContent = '{\n    categoria: ' + JSON.stringify(value.categoria || "") + ',\n    projetos: [\n        {\n' + ["titulo", "imagem", "descricao", "link"].map(key => '            ' + key + ': ' + JSON.stringify(value[key] || "")).join(',\n') + '\n        }\n    ]\n}';
  }
  async mutate(action) {
    if (!this.data || this.pending) return;
    this.pending = true;
    const buttons = ["catalog-save", "catalog-remove", "catalog-undo", "catalog-load", "catalog-publish", "catalog-new"].map(id => $("#" + id));
    const inputs = [...document.querySelectorAll("#catalog-form input, #catalog-form textarea, #catalog-list button, #catalog-path, #catalog-page, #catalog-search")];
    buttons.forEach(button => {button.disabled = true;});
    inputs.forEach(input => {input.disabled = true;});
    $("#catalog-error").hidden = true;
    $("#catalog-message").textContent = "Salvando alteração no catálogo…";
    try {
      const body = {path: this.data.path, page: this.data.page, version: this.data.version};
      if (action === "save") Object.assign(body, this.readForm(), {entry_id: this.entryId});
      if (action === "remove") Object.assign(body, {entry_id: this.entryId, confirm: true});
      this.data = await this.post(action, body);
      if (this.closed) return;
      this.dirty = false;
      const saved = this.entries().find(entry => entry.link === this.data.saved_link);
      this.form = saved ? {...saved} : {};
      this.entryId = saved?.id || "";
      this.render();
      $("#catalog-message").textContent = action === "undo" ? "Última alteração desfeita na cópia local." : "Catálogo salvo na cópia local. Revise a publicação para enviar ao GitHub.";
    } catch (failure) {
      this.error(failure.message);
      if ($("#catalog-message")) $("#catalog-message").textContent = "Sua edição permanece no formulário.";
    } finally {
      this.pending = false;
      buttons.forEach(button => {button.disabled = false;});
      inputs.forEach(input => {input.disabled = false;});
      if ($("#catalog-undo")) $("#catalog-undo").disabled = !this.data?.can_undo;
    }
  }
}

export async function openProjectCatalog(options) {
  const editor = new ProjectCatalog(options);
  await editor.open();
  return editor;
}
