import { icon } from "./workspace.js";
const $ = (selector) => document.querySelector(selector);

export class SiteManager {
  constructor(options) {
    Object.assign(this, options);
    this.root = "";
    this.pages = [];
    this.trash = [];
    this.checked = new Set();
    this.editor = null;
    document
      .querySelector('[data-tab="site-tab"]')
      .addEventListener("click", () => this.guard(() => this.load()));
    $("#site-refresh").onclick = () => this.guard(() => this.load());
    $("#site-choose").onclick = () =>
      this.guard(async () => {
        if (await this.pickFolder($("#site-directory"))) await this.load();
      });
    $("#site-recent").onchange = () => {
      $("#site-directory").value = $("#site-recent").value;
      this.guard(() => this.load());
    };
    $("#site-filter").oninput = () => {
      this.checked.clear();
      this.draw();
    };
    $("#site-select-visible").onclick = () => {
      const rows = this.filtered();
      if (rows.length > 100)
        return this.toast(
          "Filtre a lista para selecionar até 100 páginas.",
          true,
        );
      rows.forEach((row) => this.checked.add(row.path));
      this.draw();
    };
    $("#site-clear-selection").onclick = () => {
      this.checked.clear();
      this.draw();
    };
    $("#site-trash-selected").onclick = () =>
      this.confirmTrash(this.pages.filter((row) => this.checked.has(row.path)));
    $("#site-show-trash").onclick = () => this.showTrash();
    $("#site-clone").onclick = () => this.cloneForm();
    $("#site-publish").onclick = () =>
      this.guard(() => this.publishSite(this.requireRoot()));
    $("#site-new-document").onclick = () =>
      this.guard(() => this.newDocument(this.requireRoot()));
    $("#site-editor-settings").onclick = () =>
      this.guard(() => this.editorSettings());
    $("#site-open-editor").onclick = () => this.guard(() => this.openEditor());
    $("#modal").addEventListener("close", () => {
      this.editor = null;
      $("#modal").classList.remove("html-editor-modal");
    });
    const allowClose = (event) => {
      if (!this.editor?.dirty) return;
      if (event.type === "click") {
        const close = event.target.closest?.("#close-modal");
        const dialog = $("#modal"),
          bounds = dialog.getBoundingClientRect();
        const outside =
          event.target === dialog &&
          (event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom);
        if (!close && !outside) return;
      }
      if (!confirm("Descartar as alterações ainda não salvas neste HTML?")) {
        event.preventDefault();
        event.stopImmediatePropagation();
      } else this.editor.dirty = false;
    };
    $("#modal").addEventListener("click", allowClose, true);
    $("#modal").addEventListener("cancel", allowClose, true);
    document.addEventListener(
      "keydown",
      (event) => {
        if (
          !(event.ctrlKey || event.metaKey) ||
          event.key.toLowerCase() !== "s" ||
          $("#site-tab").hidden
        )
          return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (this.editor) this.guard(() => this.saveHtml());
      },
      true,
    );
    window.addEventListener("beforeunload", (event) => {
      if (this.editor?.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }
  async guard(action) {
    try {
      return await action();
    } catch (error) {
      this.toast(error.message, true);
    }
  }
  async busy(button, action, text = "Aguarde…") {
    if (button.disabled) return;
    const label = button.textContent;
    button.disabled = true;
    button.textContent = text;
    try {
      return await action();
    } catch (error) {
      this.toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }
  post(route, body) {
    return this.api("/api/generator/site/" + route, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
  requireRoot() {
    const value = $("#site-directory").value.trim() || this.root;
    if (!value) throw Error("Selecione a raiz local do site.");
    return value;
  }
  async load() {
    const settings = await this.api("/api/generator/site/settings");
    this.settings = settings;
    const recent = $("#site-recent");
    recent.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Sites e clones recentes";
    recent.append(placeholder);
    for (const root of settings.roots) {
      const option = document.createElement("option");
      option.value = root.path;
      option.textContent = root.name;
      option.title = root.path;
      recent.append(option);
    }
    const value =
      $("#site-directory").value.trim() ||
      this.root ||
      settings.selected_root ||
      this.repository();
    if (!value) {
      $("#site-status").textContent =
        "Escolha a pasta do index.html ou clone um repositório.";
      return;
    }
    $("#site-status").textContent = "Lendo páginas locais…";
    const result = await this.post("pages", { root: value });
    this.root = result.root;
    this.info = result;
    this.pages = result.pages;
    this.trash = result.trash;
    this.checked.clear();
    $("#site-directory").value = result.root;
    if (![...recent.options].some((option) => option.value === result.root)) {
      const option = document.createElement("option");
      option.value = result.root;
      option.textContent = result.root.split(/[\\/]/).filter(Boolean).at(-1);
      option.title = result.root;
      recent.append(option);
    }
    recent.value = result.root;
    $("#site-status").textContent =
      (result.repository
        ? result.repository + " · " + result.branch + " · "
        : "") +
      result.pages.length +
      " página(s) local(is)" +
      (result.has_index ? "" : " · index.html ausente na raiz");
    $("#site-show-trash").textContent =
      "Lixeira de páginas (" + result.trash.length + ")";
    this.draw();
  }
  filtered() {
    const query = $("#site-filter").value.toLocaleLowerCase();
    return this.pages.filter((page) =>
      (page.path + " " + page.title).toLocaleLowerCase().includes(query),
    );
  }
  draw() {
    const list = $("#site-pages");
    list.replaceChildren();
    for (const page of this.filtered()) {
      const row = document.createElement("article");
      row.className = "site-page-row";
      row.dataset.pagePath = page.path;
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = this.checked.has(page.path);
      check.setAttribute("aria-label", "Selecionar " + page.path);
      check.onchange = () => {
        if (check.checked) this.checked.add(page.path);
        else this.checked.delete(page.path);
        this.selection();
      };
      const info = document.createElement("div");
      info.className = "site-page-info";
      const title = document.createElement("strong"),
        path = document.createElement("small"),
        meta = document.createElement("span");
      title.textContent = page.title;
      path.textContent = page.path;
      meta.textContent =
        Math.max(1, Math.round(page.size / 1024)) +
        " KB · " +
        new Date(page.modified_at).toLocaleString("pt-BR");
      info.append(title, path, meta);
      const actions = document.createElement("div");
      actions.className = "site-page-actions";
      const button = (name, label, callback, css = "") => {
        const control = document.createElement("button");
        control.innerHTML = icon(name);
        control.title = label;
        control.setAttribute("aria-label", label);
        control.className = css;
        control.onclick = () => this.guard(callback);
        actions.append(control);
      };
      button("edit", "Editar HTML " + page.path, () =>
        this.editPage(page.path),
      );
      button("external", "Visualizar " + page.path, () =>
        this.preview(page.path),
      );
      button(
        "trash",
        "Excluir página " + page.path,
        () => this.confirmTrash([page]),
        "danger-button",
      );
      row.append(check, info, actions);
      list.append(row);
    }
    if (!list.children.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "Nenhuma página HTML encontrada neste filtro.";
      list.append(empty);
    }
    this.selection();
  }
  selection() {
    $("#site-selection").textContent = this.checked.size + " selecionada(s)";
    $("#site-trash-selected").disabled = !this.checked.size;
  }
  async preview(path) {
    const result = await this.post("pages/view", {
      root: this.requireRoot(),
      path,
    });
    this.modal(
      "Prévia de " + path,
      '<iframe id="site-page-preview" title="Prévia da página" sandbox="allow-scripts"></iframe><p class="field-hint">Arquivo local com os recursos do site.</p>',
    );
    $("#site-page-preview").src = result.url;
  }
  async editPage(path) {
    const root = this.requireRoot();
    const page = await this.post("pages/read", { root, path });
    this.modal(
      "Editar HTML local",
      '<p id="site-edit-path" class="image-path"></p><textarea id="site-html-source" spellcheck="false" aria-label="Código HTML da página"></textarea><p id="site-edit-status" class="field-hint">As alterações são salvas no arquivo local, com cópia anterior. Ctrl+S salva.</p><div class="modal-actions"><button id="site-save-html" class="primary">Salvar HTML</button><button id="site-save-publish">Salvar e revisar publicação</button><button id="site-reload-html">Recarregar do disco</button></div>',
    );
    $("#modal").classList.add("html-editor-modal");
    this.editor = { root, path, version: page.version, dirty: false };
    $("#site-edit-path").textContent = root.replace(/[\\/]+$/, "") + "/" + path;
    $("#site-html-source").value = page.html;
    $("#site-html-source").oninput = () => {
      this.editor.dirty = true;
      $("#site-edit-status").textContent =
        "Alterações locais ainda não salvas.";
    };
    $("#site-save-html").onclick = () =>
      this.busy($("#site-save-html"), () => this.saveHtml());
    $("#site-save-publish").onclick = () =>
      this.busy($("#site-save-publish"), async () => {
        await this.saveHtml();
        this.editor = null;
        await this.publishSite(root);
      });
    $("#site-reload-html").onclick = () =>
      this.guard(async () => {
        if (
          this.editor.dirty &&
          !confirm("Descartar a edição e recarregar a versão do disco?")
        )
          return;
        await this.editPage(path);
      });
  }
  async saveHtml() {
    const editor = this.editor;
    if (!editor) return;
    const result = await this.post("pages/save", {
      root: editor.root,
      path: editor.path,
      version: editor.version,
      html: $("#site-html-source").value,
    });
    editor.version = result.version;
    editor.dirty = false;
    $("#site-edit-status").textContent =
      "HTML salvo localmente. Cópia anterior preservada.";
    this.toast("HTML salvo no site.");
    await this.load();
  }
  confirmTrash(pages) {
    if (!pages.length)
      return this.toast("Selecione as páginas para excluir.", true);
    const root = this.requireRoot();
    this.modal(
      "Excluir páginas do site",
      '<p>As páginas selecionadas serão movidas para uma lixeira recuperável. Depois, revise a publicação das remoções para enviá-las ao GitHub e ao S3.</p><ul id="site-trash-confirm-list" class="image-path"></ul><div class="modal-actions"><button id="site-confirm-trash" class="danger-button">Enviar páginas à lixeira</button><button id="site-cancel-trash">Cancelar</button></div>',
    );
    for (const page of pages) {
      const item = document.createElement("li");
      item.textContent = page.path;
      $("#site-trash-confirm-list").append(item);
    }
    $("#site-cancel-trash").onclick = () => $("#modal").close();
    $("#site-confirm-trash").onclick = () =>
      this.busy($("#site-confirm-trash"), async () => {
        try {
          await this.post("pages/trash", {
            root,
            pages: pages.map((page) => ({
              path: page.path,
              version: page.version,
            })),
            confirm: true,
          });
        } finally {
          await this.load();
        }
        this.modal(
          "Páginas enviadas à lixeira",
          '<p>As remoções estão no clone local. Revise os arquivos antes de enviá-las à main.</p><div class="modal-actions"><button id="site-publish-deletions" class="primary">Revisar publicação das remoções</button><button id="site-finish-trash">Continuar no site</button></div>',
        );
        $("#site-publish-deletions").onclick = () =>
          this.guard(() => this.publishSite(root));
        $("#site-finish-trash").onclick = () => $("#modal").close();
      });
  }
  showTrash() {
    this.modal(
      "Lixeira de páginas",
      '<p>Restaure as páginas para o caminho original. Arquivos existentes serão preservados.</p><div id="site-trash-list" class="asset-list"></div>',
    );
    for (const page of this.trash) {
      const row = document.createElement("article");
      row.className = "asset-row";
      const name = document.createElement("span");
      name.className = "site-page-info";
      name.textContent = page.relative;
      const restore = document.createElement("button");
      restore.textContent = "Restaurar";
      restore.setAttribute("aria-label", "Restaurar " + page.relative);
      restore.onclick = () =>
        this.busy(restore, async () => {
          await this.post("pages/trash/" + page.id + "/restore", {});
          await this.load();
          this.showTrash();
        });
      row.append(name, restore);
      $("#site-trash-list").append(row);
    }
    if (!this.trash.length)
      $("#site-trash-list").textContent = "A lixeira de páginas está vazia.";
  }
  cloneForm(values = {}) {
    this.modal(
      "Clonar repositório para esta máquina",
      '<p>O clone será gravado numa pasta nova desta máquina. Depois, você poderá editar seus arquivos locais e publicar pela revisão do GitHub.</p><div class="stack"><label>URL do repositório GitHub<input id="site-clone-url" placeholder="https://github.com/usuario/site.git"></label><label>Nova pasta de destino<div class="path-input"><input id="site-clone-destination" placeholder="C:\\sites\\meu-site ou /srv/seabirds/meu-site"><button id="site-clone-parent">Escolher pasta base</button></div></label><details><summary>Identidade dos commits (opcional)</summary><label>Nome<input id="site-clone-author"></label><label>Email<input id="site-clone-email" type="email"></label></details></div><div class="modal-actions"><button id="site-confirm-clone" class="primary">Clonar repositório</button></div>',
    );
    $("#site-clone-url").value =
      values.url ||
      (this.info?.repository
        ? "https://github.com/" + this.info.repository + ".git"
        : "");
    $("#site-clone-destination").value = values.destination || "";
    $("#site-clone-author").value = values.author_name || "";
    $("#site-clone-email").value = values.author_email || "";
    const data = () => ({
      url: $("#site-clone-url").value.trim(),
      destination: $("#site-clone-destination").value.trim(),
      author_name: $("#site-clone-author").value.trim(),
      author_email: $("#site-clone-email").value.trim(),
    });
    $("#site-clone-parent").onclick = () =>
      this.guard(async () => {
        const current = data();
        const input = document.createElement("input");
        input.value = current.destination || this.root;
        if (await this.pickFolder(input)) {
          const name =
            current.url
              .split(/[/:]/)
              .filter(Boolean)
              .at(-1)
              ?.replace(/\.git$/, "") || "meu-site";
          current.destination = input.value.replace(/[\\/]+$/, "") + "/" + name;
        }
        this.cloneForm(current);
      });
    $("#site-confirm-clone").onclick = () =>
      this.busy(
        $("#site-confirm-clone"),
        async () => {
          const result = await this.post("clone", data());
          $("#site-directory").value = result.root;
          this.root = result.root;
          await this.load();
          this.modal(
            "Clone local concluído",
            '<p id="site-clone-result" class="image-path"></p><div class="modal-actions"><button id="site-use-clone" class="primary">Gerenciar este site</button><button id="site-edit-clone">Abrir no VS Code Web local</button></div>',
          );
          $("#site-clone-result").textContent = result.root;
          $("#site-use-clone").onclick = () => $("#modal").close();
          $("#site-edit-clone").onclick = () =>
            this.guard(() => this.openEditor());
        },
        "Clonando…",
      );
  }
  async editorSettings() {
    const settings = await this.api("/api/generator/site/settings");
    this.settings = settings;
    this.modal(
      "VS Code Web nos arquivos locais",
      '<p>O editor deve executar na mesma máquina do gerador, usando a mesma pasta do clone.</p><div class="stack"><label>Tipo de editor<select id="site-editor-kind"><option value="code-server">code-server (LXC/Linux)</option><option value="vscode-serve-web">VS Code serve-web (local)</option></select></label><label>URL do editor local<input id="site-editor-url" placeholder="http://127.0.0.1:8765"></label></div><div class="modal-actions"><button id="site-save-editor" class="primary">Salvar conexão</button><button id="site-native-editor">Iniciar VS Code Web neste computador</button></div><p id="site-native-note" class="field-hint"></p>',
    );
    $("#site-editor-url").value = settings.editor_url || "";
    $("#site-editor-kind").value = settings.editor_kind || "code-server";
    $("#site-save-editor").onclick = () =>
      this.busy($("#site-save-editor"), async () => {
        await this.post("settings/editor", {
          url: $("#site-editor-url").value.trim(),
          kind: $("#site-editor-kind").value,
        });
        $("#modal").close();
        this.toast("Conexão com o editor local salva.");
      });
    $("#site-native-editor").hidden = !settings.local_editor_available;
    $("#site-native-note").textContent = settings.local_editor_available
      ? "O VS Code instalado pode servir um editor Web local. A primeira execução pede a aceitação dos termos do servidor."
      : "No LXC, conecte um code-server que tenha acesso à mesma pasta do site.";
    $("#site-native-editor").onclick = () => this.nativeEditorForm();
  }
  nativeEditorForm() {
    const root = this.requireRoot();
    this.modal(
      "Iniciar VS Code Web local",
      '<p>O servidor do VS Code será iniciado neste computador, acessível em 127.0.0.1, com autenticação por token. Ele editará a pasta local selecionada.</p><p id="site-native-root" class="image-path"></p><label class="inline-check"><input id="site-native-license" type="checkbox">Li e aceito os <a href="https://aka.ms/vscode-server-license" target="_blank" rel="noopener noreferrer">termos do Visual Studio Code Server</a>.</label><div class="modal-actions"><button id="site-start-native" class="primary" disabled>Iniciar editor local</button></div><p class="field-hint">Na primeira abertura, o VS Code pode baixar os componentes do servidor.</p>',
    );
    $("#site-native-root").textContent = root;
    $("#site-native-license").onchange = () =>
      ($("#site-start-native").disabled = !$("#site-native-license").checked);
    $("#site-start-native").onclick = () =>
      this.busy($("#site-start-native"), async () => {
        await this.post("editor/local/start", { root, confirm_license: true });
        await this.openEditor();
      });
  }
  async openEditor() {
    let result;
    try {
      result = await this.post("editor-link", { root: this.requireRoot() });
    } catch (error) {
      this.toast(error.message, true);
      return this.editorSettings();
    }
    this.modal(
      "Abrir VS Code Web local",
      '<p>O editor abrirá a mesma pasta usada pelo gerador. Salve os arquivos e use Atualizar páginas para ver as mudanças.</p><div class="modal-actions"><a id="site-editor-open-link" class="button-link primary" target="_blank" rel="noopener noreferrer">Abrir editor local</a></div>',
    );
    $("#site-editor-open-link").href = result.url;
  }
}
