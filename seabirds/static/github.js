const $ = (selector) => document.querySelector(selector);
const labels = { added: "Novo", modified: "Alterado", deleted: "Removido" };
const statuses = {
  queued: "Na fila",
  in_progress: "Em execução",
  waiting: "Aguardando",
  pending: "Pendente",
  requested: "Solicitada",
  completed: "Concluída",
};
const conclusions = {
  success: "Concluída com sucesso",
  failure: "Falhou",
  cancelled: "Cancelada",
  skipped: "Ignorada",
  timed_out: "Tempo esgotado",
  action_required: "Requer atenção",
  neutral: "Concluída",
};

export class GitHubPublication {
  constructor(options) {
    Object.assign(this, options);
    $("#publish-github").onclick = () => this.open();
  }
  async busy(button, action) {
    if (button.disabled) return;
    const text = button.textContent;
    button.disabled = true;
    button.textContent = "Aguarde…";
    try {
      await action();
    } catch (error) {
      this.toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = text;
    }
  }
  open(directory = this.repository()) {
    this.mode = "document";
    this.modal(
      "Publicar no GitHub",
      '<p>Gere o HTML, revise os arquivos e envie um commit para a <b>main</b>. O GitHub Actions executará a pipeline de publicação no S3.</p><label>Raiz do site (pasta do index.html)<div class="path-input"><input id="github-directory" placeholder="Detectada a partir do HTML gerado"><button id="github-choose" aria-label="Selecionar pasta do site">Selecionar</button></div></label><p class="field-hint">A busca inclui os HTML e imagens em todas as subpastas do site. A pasta precisa conter o HTML de saída e pertencer ao clone do site.</p><div class="modal-actions"><button id="github-review" class="primary">Gerar HTML e revisar</button></div>',
    );
    $("#github-directory").value = directory;
    $("#github-choose").onclick = () =>
      this.busy($("#github-choose"), async () => {
        const input = $("#github-directory");
        await this.pickFolder(input);
        this.open(input.value);
      });
    $("#github-review").onclick = () =>
      this.busy($("#github-review"), async () => {
        this.setRepository($("#github-directory").value.trim());
        await this.generate();
        await this.review();
      });
  }
  async review() {
    this.mode = "document";
    const review = await this.api("/api/generator/github/review", {
      method: "POST",
      body: JSON.stringify({
        directory: this.repository(),
        document: this.data(),
      }),
    });
    this.setRepository(review.site_root || review.root);
    await this.save();
    this.renderReview(review);
  }
  async reviewSite(root) {
    this.mode = "site";
    this.siteDirectory = root;
    const review = await this.api("/api/generator/github/review-site", {
      method: "POST",
      body: JSON.stringify({ directory: root }),
    });
    this.renderReview(review);
  }
  async refreshReview() {
    if (this.mode === "site") return this.reviewSite(this.siteDirectory);
    await this.generate();
    return this.review();
  }
  renderReview(review) {
    this.modal(
      "Revisar publicação na main",
      '<div class="github-repository"><div><span class="eyebrow">REPOSITÓRIO</span><strong id="github-repository-name"></strong><small id="github-author"></small></div><span class="github-branch">main</span></div><p class="field-hint">Raiz do site (index.html)</p><p id="github-root" class="image-path"></p><p id="github-scope" class="field-hint"></p><div id="github-notice" class="github-notice" hidden></div><div id="github-last"></div><p>Selecione os HTML e imagens que entrarão neste commit. As remoções selecionadas também serão enviadas.</p><div id="github-files" class="github-files"></div><div class="github-selection" id="github-selection"></div><label>Mensagem do commit<input id="github-message" maxlength="500"></label><p class="field-hint">O envio à main inicia a pipeline do repositório.</p><div class="modal-actions"><button id="github-publish" class="primary">Fazer commit e publicar na main</button><button id="github-rescan">Revisar novamente</button></div>',
    );
    $("#github-repository-name").textContent = review.repository;
    $("#github-root").textContent = review.site_root || review.root;
    $("#github-scope").textContent =
      (review.directory_corrected
        ? "A pasta salva foi corrigida para a raiz do site que contém o HTML de saída. "
        : "") +
      (review.site_only
        ? "Revise as alterações locais do site, incluindo as páginas removidas."
        : "Busca recursiva em todas as subpastas. O HTML gerado e suas imagens já estão selecionados.");
    $("#github-author").textContent =
      review.author.name && review.author.email
        ? `Autor: ${review.author.name} <${review.author.email}>`
        : "Configure user.name e user.email no Git deste repositório antes de publicar.";
    $("#github-message").value = review.site_only
      ? "docs: atualiza páginas do site"
      : "docs: atualiza " + this.data().title;
    const aligned = !review.ahead && !review.behind;
    if (!aligned) {
      const notice = $("#github-notice");
      notice.hidden = false;
      const explanation = document.createElement("p");
      explanation.textContent = review.ahead
        ? `A main local tem ${review.ahead} commit(s) ainda não enviados. Confira o commit pendente abaixo ou resolva a divergência pelo Git.`
        : `A main remota tem ${review.behind} commit(s) mais recentes. Atualize a cópia local antes de publicar.`;
      notice.append(explanation);
      if (!review.ahead) {
        const sync = document.createElement("button");
        sync.id = "github-sync";
        sync.textContent = "Atualizar main local";
        sync.onclick = () =>
          this.busy(sync, async () => {
            await this.api("/api/generator/github/sync", {
              method: "POST",
              body: JSON.stringify({ token: review.token }),
            });
            await this.refreshReview();
          });
        notice.append(sync);
      }
    }
    if (review.last) {
      const last = document.createElement("button");
      last.className = "quiet-button";
      last.textContent =
        review.last.status === "pending_push"
          ? "Reenviar commit pendente " + review.last.sha.slice(0, 7)
          : "Ver última publicação " + review.last.sha.slice(0, 7);
      last.onclick = () => {
        if (review.last.status === "pushed")
          this.result({ publication: review.last, push_error: null });
        else
          this.busy(last, async () =>
            this.result(
              await this.api(
                `/api/generator/github/publications/${review.last.id}/retry`,
                { method: "POST" },
              ),
            ),
          );
      };
      $("#github-last").append(last);
    }
    const checks = [];
    const updateSelection = () => {
      const count = checks.filter((input) => input.checked).length;
      $("#github-selection").textContent = count + " arquivo(s) selecionado(s)";
      $("#github-publish").disabled =
        !count || !aligned || !review.author.name || !review.author.email;
    };
    for (const file of review.files) {
      const row = document.createElement("article");
      row.className = "github-file";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = file.path;
      input.checked = file.selected;
      input.setAttribute("aria-label", "Publicar " + file.path);
      input.onchange = updateSelection;
      checks.push(input);
      const details = document.createElement("details"),
        summary = document.createElement("summary");
      const name = document.createElement("strong"),
        status = document.createElement("span"),
        diff = document.createElement("pre");
      name.textContent = file.path;
      status.textContent = labels[file.status] || file.status;
      status.className = "github-file-status " + file.status;
      summary.append(name, status);
      diff.textContent = file.diff;
      details.append(summary, diff);
      row.append(input, details);
      $("#github-files").append(row);
    }
    if (!review.files.length)
      $("#github-files").textContent =
        "Nenhum HTML ou imagem com alterações para publicar.";
    updateSelection();
    $("#github-rescan").onclick = () =>
      this.busy($("#github-rescan"), async () => {
        await this.refreshReview();
      });
    $("#github-publish").onclick = () =>
      this.busy($("#github-publish"), async () => {
        const selected = checks
          .filter((input) => input.checked)
          .map((input) => input.value);
        const message = $("#github-message").value.trim();
        if (!message) throw Error("Informe a mensagem do commit.");
        const result = await this.api("/api/generator/github/publish", {
          method: "POST",
          body: JSON.stringify({ token: review.token, selected, message }),
        });
        this.result(result);
      });
  }
  result(result) {
    const item = result.publication,
      pushed = item.status === "pushed";
    this.currentPublication = item.id;
    this.modal(
      pushed ? "Commit enviado ao GitHub" : "Commit aguardando envio",
      '<div class="github-repository"><div><strong id="github-result-repository"></strong><small id="github-result-sha"></small></div><span class="github-branch">main</span></div><p id="github-result-message"></p><p id="github-push-status" class="github-notice"></p><div id="github-result-links" class="modal-actions"></div><div id="github-pipeline"><h3>Pipeline de publicação</h3><p id="github-pipeline-status"></p><div id="github-runs"></div><button id="github-refresh-runs">Atualizar pipeline</button></div>',
    );
    $("#github-result-repository").textContent = item.repository;
    $("#github-result-sha").textContent = item.sha;
    $("#github-result-message").textContent = item.message;
    $("#github-push-status").textContent = pushed
      ? "Commit enviado à main. O GitHub Actions fará o deploy no S3."
      : "O commit foi criado localmente. O envio falhou: " +
        (result.push_error || "Confira a conexão e a autenticação do Git.");
    const link = (label, url) => {
      const a = document.createElement("a");
      a.className = "button-link";
      a.textContent = label;
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      $("#github-result-links").append(a);
    };
    if (pushed) link("Abrir commit", item.commit_url);
    link("Abrir GitHub Actions", item.actions_url);
    $("#github-pipeline").hidden = !pushed;
    if (!pushed) {
      const retry = document.createElement("button");
      retry.className = "primary";
      retry.id = "github-retry";
      retry.textContent = "Reenviar este commit";
      retry.onclick = () =>
        this.busy(retry, async () =>
          this.result(
            await this.api(
              `/api/generator/github/publications/${item.id}/retry`,
              { method: "POST" },
            ),
          ),
        );
      $("#github-result-links").append(retry);
    } else {
      const refresh = async () => {
        $("#github-pipeline-status").textContent =
          "Consultando o GitHub Actions…";
        try {
          const state = await this.api(
            `/api/generator/github/publications/${item.id}/runs`,
          );
          if (
            !$("#github-pipeline-status") ||
            this.currentPublication !== item.id
          )
            return;
          $("#github-pipeline-status").textContent = state.runs.length
            ? "Execuções deste commit:"
            : "Aguardando o GitHub Actions iniciar a execução. Atualize em instantes.";
          $("#github-runs").replaceChildren();
          for (const run of state.runs) {
            const a = document.createElement("a");
            a.href = run.url;
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            a.className = "github-run";
            a.textContent =
              run.name +
              " · " +
              (conclusions[run.conclusion] ||
                statuses[run.status] ||
                run.status);
            $("#github-runs").append(a);
          }
        } catch (error) {
          if (
            $("#github-pipeline-status") &&
            this.currentPublication === item.id
          )
            $("#github-pipeline-status").textContent = error.message;
        }
      };
      $("#github-refresh-runs").onclick = () =>
        this.busy($("#github-refresh-runs"), refresh);
      refresh();
    }
  }
}
