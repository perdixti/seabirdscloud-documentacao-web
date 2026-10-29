import { runOperation, registerOperationResult } from "./operations.js";
const $ = (s) => document.querySelector(s);
export class ManagementUI {
  constructor(options) {
    Object.assign(this, options);
    $("#site-audit").onclick = () => this.guard(() => this.audit());
    $("#site-diagnostics").onclick = () => this.guard(() => this.diagnostics());
    $("#server-backups").onclick = () => this.guard(() => this.backups());
    $("#document-metadata").onclick = () => this.guard(() => this.metadata());
    registerOperationResult("site.audit", (result) => this.showAudit(result));
    registerOperationResult("diagnostics", (result) =>
      this.showDiagnostics(result),
    );
  }
  async guard(action) {
    try {
      return await action();
    } catch (e) {
      this.toast(e.message, true);
    }
  }
  async root() {
    const value = this.getRoot();
    if (value) return value;
    const settings = await this.api("/api/generator/site/settings");
    if (settings.selected_root) return settings.selected_root;
    throw Error("Selecione primeiro a raiz do site em Site e repositórios.");
  }
  async audit() {
    this.showAudit(
      await runOperation("site.audit", { root: await this.root() }),
    );
  }
  showAudit(result) {
    this.modal(
      "Verificação do site",
      '<p id="audit-summary"></p><p id="audit-root" class="image-path"></p><div id="audit-list" class="asset-list"></div><p class="field-hint">A verificação é local e não executa scripts nem consulta links externos.</p><button id="audit-again">Verificar novamente</button>',
    );
    $("#audit-summary").textContent =
      result.checked_files +
      " arquivo(s) · " +
      result.errors +
      " erro(s) · " +
      result.warnings +
      " aviso(s)" +
      (result.truncated ? " · lista limitada a 1000 ocorrências" : "");
    $("#audit-root").textContent = result.root;
    for (const issue of result.issues) {
      const row = document.createElement("article"),
        info = document.createElement("div"),
        title = document.createElement("strong"),
        detail = document.createElement("small");
      row.className = "asset-row";
      info.className = "asset-info";
      title.textContent =
        (issue.severity === "error" ? "Erro: " : "Aviso: ") + issue.message;
      detail.textContent =
        issue.path + (issue.reference ? " → " + issue.reference : "");
      info.append(title, detail);
      row.append(info);
      $("#audit-list").append(row);
    }
    if (!result.issues.length)
      $("#audit-list").textContent =
        "Nenhum problema identificado nas referências locais verificadas.";
    $("#audit-again").onclick = () => this.guard(() => this.audit());
  }
  async diagnostics() {
    this.showDiagnostics(
      await runOperation("diagnostics", { root: await this.root() }),
    );
  }
  showDiagnostics(result) {
    this.modal(
      "Diagnóstico do ambiente",
      '<p id="diagnostic-root" class="image-path"></p><div id="diagnostic-list" class="asset-list"></div><p id="diagnostic-note" class="field-hint"></p><div class="modal-actions"><button id="diagnostic-again">Atualizar diagnóstico</button><button id="diagnostic-git">Testar acesso ao GitHub</button></div>',
    );
    $("#diagnostic-root").textContent = result.root;
    $("#diagnostic-note").textContent = result.note;
    for (const check of result.checks) {
      const row = document.createElement("article"),
        info = document.createElement("div"),
        title = document.createElement("strong"),
        detail = document.createElement("small");
      row.className = "asset-row";
      info.className = "asset-info";
      title.textContent = (check.status === "ok" ? "✓ " : "⚠ ") + check.name;
      detail.textContent = check.detail;
      info.append(title, detail);
      row.append(info);
      $("#diagnostic-list").append(row);
    }
    $("#diagnostic-again").onclick = () => this.guard(() => this.diagnostics());
    $("#diagnostic-git").onclick = () =>
      this.guard(async () => {
        const result = await runOperation("diagnostics.git", {
          root: await this.root(),
        });
        this.toast(result.message);
      });
  }
  async wizard(initialRoot = "", values = {}) {
    const settings = await this.api("/api/generator/site/settings");
    this.modal(
      "Nova documentação",
      '<p>Defina os dados uma vez. O gerador preparará os caminhos do HTML, das imagens e o cadastro no catálogo.</p><div class="stack"><label>Raiz do site<div class="path-input"><input id="wizard-root"><button id="wizard-choose-root">Selecionar</button></div></label><div class="two-columns"><label>Título<input id="wizard-title" maxlength="200"></label><label>Categoria<input id="wizard-category" list="wizard-categories" maxlength="100"><datalist id="wizard-categories"></datalist></label></div><label>Descrição do card<textarea id="wizard-description" maxlength="2000"></textarea></label><label>Imagem de capa, opcional por enquanto<input id="wizard-cover" placeholder="Caminho de uma imagem existente ou deixe vazio para usar a primeira imagem colada"></label><label>Template HTML<div class="path-input"><input id="wizard-template" placeholder="Usar template padrão"><button id="wizard-choose-template">Selecionar</button></div></label></div><p class="field-hint">A fonte Markdown e o template ficarão associados ao HTML. Cole as imagens e use Gerar HTML para gravar os arquivos e cadastrar o card.</p><div class="modal-actions"><button id="wizard-create" class="primary">Criar no editor</button><button id="wizard-empty">Documento sem assistente</button></div>',
    );
    $("#wizard-root").value =
      values.root ??
      (initialRoot || settings.selected_root || this.getRoot() || "");
    $("#wizard-template").value =
      values.template ?? (this.getTemplate?.() || "");
    for (const field of ["title", "category", "description", "cover"])
      $("#wizard-" + field).value = values[field] || "";
    const snapshot = () =>
      Object.fromEntries(
        ["root", "template", "title", "category", "description", "cover"].map(
          (field) => [field, $("#wizard-" + field).value],
        ),
      );
    const choose = async (field, picker) => {
      const saved = snapshot(),
        target = document.createElement("input");
      target.value = saved[field];
      await picker(target);
      saved[field] = target.value;
      await this.wizard(initialRoot, saved);
    };
    $("#wizard-choose-root").onclick = () =>
      this.guard(() => choose("root", this.pickFolder));
    $("#wizard-choose-template").onclick = () =>
      this.guard(() => choose("template", this.pickTemplate));
    const categories = async () => {
      try {
        const result = await this.api("/api/generator/site/catalog/read", {
          method: "POST",
          body: JSON.stringify({ root: $("#wizard-root").value }),
        });
        $("#wizard-categories").replaceChildren();
        for (const category of result.categories) {
          const item = document.createElement("option");
          item.value = category.categoria;
          $("#wizard-categories").append(item);
        }
      } catch {}
    };
    $("#wizard-root").onchange = categories;
    await categories();
    $("#wizard-create").onclick = () =>
      this.guard(async () => {
        const title = $("#wizard-title").value.trim(),
          category = $("#wizard-category").value.trim(),
          description = $("#wizard-description").value.trim();
        if (!title || !category || !description)
          throw Error("Preencha título, categoria e descrição.");
        const doc = await this.api("/api/site/documents/prepare", {
          method: "POST",
          body: JSON.stringify({
            root: $("#wizard-root").value.trim(),
            title,
            category,
            description,
            cover: $("#wizard-cover").value.trim(),
            template: $("#wizard-template").value.trim(),
          }),
        });
        await this.openDocument(doc);
        $("#modal").close();
        this.toast("Documento preparado. Cole as imagens e gere o HTML.");
      });
    $("#wizard-empty").onclick = () =>
      this.guard(async () => {
        await this.openDocument({});
        $("#modal").close();
      });
  }
  async metadata() {
    const generation = this.getDocument().generation;
    this.modal(
      "Dados da documentação",
      '<div class="stack"><label>Categoria<input id="metadata-category" maxlength="100"></label><label>Descrição do card<textarea id="metadata-description" maxlength="2000"></textarea></label><label>Capa<input id="metadata-image" placeholder="Vazio usa a primeira imagem colada"></label><label class="inline-check"><input id="metadata-register" type="checkbox">Cadastrar ou atualizar o card ao gerar HTML</label><label class="inline-check"><input id="metadata-source" type="checkbox">Salvar fonte Markdown e template junto do HTML</label></div><p class="field-hint">Os caminhos do HTML e das imagens continuam disponíveis em Configurar arquivos. A fonte não contém a chave do revisor nem o token do GitHub.</p><button id="metadata-save" class="primary">Salvar dados</button>',
    );
    $("#metadata-category").value = generation.catalog_category || "";
    $("#metadata-description").value = generation.catalog_description || "";
    $("#metadata-image").value = generation.catalog_image || "";
    $("#metadata-register").checked = !!generation.register_catalog;
    $("#metadata-source").checked = !!generation.save_source;
    $("#metadata-save").onclick = () => {
      this.setMetadata({
        catalog_category: $("#metadata-category").value.trim(),
        catalog_description: $("#metadata-description").value.trim(),
        catalog_image: $("#metadata-image").value.trim(),
        register_catalog: $("#metadata-register").checked,
        save_source: $("#metadata-source").checked,
      });
      $("#modal").close();
      this.toast("Dados atualizados. Gere o HTML para gravar.");
    };
  }
  async backups() {
    const state = await this.api("/api/maintenance/backups"),
      config = state.settings;
    this.modal(
      "Backups e restauração",
      '<p>O backup completo inclui banco, rascunhos, fontes, configurações, segredos, lixeiras e sites cadastrados, incluindo os arquivos Git locais. O arquivo é protegido por senha; guarde-a para conseguir restaurar.</p><div class="stack"><label>Senha dos próximos backups<input type="password" autocomplete="new-password" id="backup-password" placeholder="Vazio mantém a senha configurada"></label><div class="two-columns"><label>Intervalo em horas<input id="backup-hours" type="number" min="1" max="168"></label><label>Quantidade de backups agendados a manter<input id="backup-retention" type="number" min="1" max="100"></label></div><label class="inline-check"><input id="backup-enabled" type="checkbox">Ativar backup automático</label></div><p id="backup-config-status" class="field-hint"></p><div class="modal-actions"><button id="backup-save">Salvar agendamento e senha</button><button id="backup-create" class="primary">Criar backup agora</button><button id="backup-import">Importar para restaurar</button><input id="backup-file" type="file" accept=".sbbak" hidden></div><h3>Backups disponíveis</h3><div id="backup-files" class="asset-list"></div><p class="field-hint">A retenção remove somente backups agendados antigos. Backups manuais e cópias de recuperação são preservados. A configuração dos serviços e a senha de acesso do servidor atual não são substituídas na restauração.</p>',
    );
    $("#backup-hours").value = config.interval_hours;
    $("#backup-retention").value = config.retention;
    $("#backup-enabled").checked = config.enabled;
    $("#backup-config-status").textContent =
      (config.password_configured
        ? "Senha configurada."
        : "Defina uma senha de pelo menos 12 caracteres.") +
      (config.enabled
        ? " Próximo agendamento: " +
          new Date(config.next_at).toLocaleString("pt-BR")
        : " Agendamento desativado.") +
      " " +
      config.site_roots.length +
      " site(s) cadastrado(s).";
    const included = document.createElement("p");
    included.className = "field-hint";
    included.textContent = config.site_roots.length
      ? "Pastas incluídas: " + config.site_roots.join("; ")
      : "Nenhum site cadastrado. Selecione a raiz do site em Site e repositórios para incluí-lo no backup.";
    $("#backup-config-status").after(included);
    if (config.interrupted_restore)
      $("#backup-config-status").textContent +=
        " Uma restauração anterior foi interrompida. A cópia de recuperação está na lista: " +
        config.interrupted_restore.recovery_backup +
        ".";
    $("#backup-save").onclick = () =>
      this.guard(async () => {
        await this.api("/api/maintenance/backups/settings", {
          method: "POST",
          body: JSON.stringify({
            enabled: $("#backup-enabled").checked,
            interval_hours: Number($("#backup-hours").value),
            retention: Number($("#backup-retention").value),
            password: $("#backup-password").value,
          }),
        });
        await this.backups();
        this.toast("Configuração de backup salva.");
      });
    $("#backup-create").onclick = () =>
      this.guard(async () => {
        await this.saveDraft?.();
        await runOperation("backup.create", {});
        await this.backups();
        this.toast("Backup completo criado.");
      });
    $("#backup-import").onclick = () => $("#backup-file").click();
    $("#backup-file").onchange = () =>
      this.guard(async () => {
        const file = $("#backup-file").files[0];
        if (!file) return;
        if (file.size > 512 * 1024 * 1024)
          throw Error("Envie um backup de até 512 MB.");
        const uploaded = await this.api("/api/maintenance/backups/upload", {
          method: "POST",
          body: file,
          timeout: 180000,
        });
        await this.restoreForm(uploaded.identifier);
      });
    for (const file of [...state.files].reverse()) {
      const row = document.createElement("article"),
        info = document.createElement("div"),
        name = document.createElement("strong"),
        detail = document.createElement("small"),
        download = document.createElement("a"),
        restore = document.createElement("button");
      row.className = "asset-row";
      info.className = "asset-info";
      name.textContent =
        new Date(file.created_at).toLocaleString("pt-BR") +
        (file.recovery
          ? " · antes de restauração"
          : file.scheduled
            ? " · agendado"
            : file.imported
              ? " · importado"
              : " · manual");
      detail.textContent =
        (file.size / 1024 / 1024).toFixed(1) +
        " MB · " +
        file.sites +
        " site(s) · " +
        file.version;
      download.textContent = "Baixar";
      download.className = "button";
      download.href = "/api/maintenance/backups/" + file.id + "/download";
      download.download = "seabirds-" + file.id + ".sbbak";
      restore.textContent = "Restaurar";
      restore.onclick = () => this.guard(() => this.restoreForm(file.id));
      info.append(name, detail);
      row.append(info, download, restore);
      $("#backup-files").append(row);
    }
    if (!state.files.length)
      $("#backup-files").textContent = "Nenhum backup disponível.";
  }
  async restoreForm(identifier) {
    await this.saveDraft?.();
    this.modal(
      "Abrir backup para restauração",
      '<p>Informe a senha usada para criar este backup. Nenhum arquivo será substituído nesta etapa.</p><label>Senha do arquivo<input id="restore-password" type="password" autocomplete="off"></label><button id="restore-inspect" class="primary">Conferir conteúdo</button>',
    );
    $("#restore-inspect").onclick = () =>
      this.guard(async () => {
        const password = $("#restore-password").value;
        const info = await runOperation("backup.inspect", {
          identifier,
          password,
        });
        const state = await this.api("/api/maintenance/backups");
        this.modal(
          "Escolher destinos da restauração",
          '<p id="restore-information"></p><div id="restore-sites" class="stack"></div><p class="field-hint">Confira os caminhos desta máquina. Ao migrar do Windows para Linux, selecione os diretórios do servidor Linux.</p><button id="restore-preview" class="primary">Revisar restauração</button>',
        );
        $("#restore-information").textContent =
          info.files +
          " arquivo(s) · versão " +
          info.version +
          " · " +
          new Date(info.created_at).toLocaleString("pt-BR");
        const targets = [];
        for (const site of info.sites) {
          const label = document.createElement("label"),
            input = document.createElement("input");
          label.textContent = site.name + " · origem: " + site.root;
          input.value =
            state.settings.site_roots.find(
              (path) =>
                path.replaceAll("\\", "/").split("/").at(-1) === site.name,
            ) || site.root;
          label.append(input);
          $("#restore-sites").append(label);
          targets.push({ site, input });
        }
        $("#restore-preview").onclick = () =>
          this.guard(async () => {
            const paths = Object.fromEntries(
              targets.map(({ site, input }) => [site.id, input.value.trim()]),
            );
            const plan = await runOperation("backup.preview", {
              identifier,
              password,
              targets: paths,
            });
            this.modal(
              "Confirmar restauração",
              '<p id="restore-message"></p><ul id="restore-destinations" class="image-path"></ul><label class="inline-check"><input id="restore-confirmation" type="checkbox">Confirmo a substituição dos arquivos presentes neste backup.</label><p class="field-hint">Uma cópia de recuperação do estado atual será criada antes. Aguarde a conclusão; depois a página será recarregada.</p><button id="restore-confirm" class="danger-button" disabled>Restaurar backup</button>',
            );
            $("#restore-message").textContent = plan.message;
            for (const site of plan.sites) {
              const item = document.createElement("li");
              item.textContent = site.name + " → " + site.target;
              $("#restore-destinations").append(item);
            }
            $("#restore-confirmation").onchange = () =>
              ($("#restore-confirm").disabled = !$("#restore-confirmation")
                .checked);
            $("#restore-confirm").onclick = () =>
              this.guard(async () => {
                if (!$("#restore-confirmation").checked) return;
                $("#restore-confirm").disabled = true;
                try {
                  const result = await runOperation("backup.restore", {
                    token: plan.token,
                    password,
                    confirm: true,
                  });
                  this.toast(result.message);
                  this.afterRestore();
                } finally {
                  if ($("#restore-confirm"))
                    $("#restore-confirm").disabled = false;
                }
              });
          });
      });
  }
}
