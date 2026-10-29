import { runOperation } from "./operations.js";
const $ = (s) => document.querySelector(s);
export class TextReviewer {
  constructor(options) {
    Object.assign(this, options);
    this.sequence = 0;
    this.blocked = new Set();
    this.running = false;
    $("#review-text").onclick = () => this.guard(() => this.open());
    $("#review-settings").onclick = () => this.guard(() => this.settings());
    $("#review-mode").onchange = () => {
      this.setMode($("#review-mode").value);
      this.reset();
      this.changed();
    };
    $("#review-undo").onclick = () => this.undo();
  }
  async guard(action) {
    try {
      return await action();
    } catch (e) {
      this.toast(e.message, true);
    }
  }
  reset() {
    clearTimeout(this.timer);
    this.sequence++;
    this.result = null;
    this.lastAnalyzed = null;
    this.revision = null;
    this.blocked.clear();
    $("#review-mode").value = this.getMode();
    $("#review-undo").disabled = true;
    $("#review-text").textContent = "Revisar texto";
  }
  changed() {
    clearTimeout(this.timer);
    this.sequence++;
    if (this.revision && this.getText() === this.revision.before) {
      this.revision = null;
      $("#review-undo").disabled = true;
    }
    if (this.applying || this.getMode() === "off") return;
    this.timer = setTimeout(
      () => this.guard(() => this.analyze(false)),
      this.cloud ? 12000 : 1800,
    );
  }
  async analyze(manual = true) {
    if (this.running) {
      if (manual) this.toast("Uma revisão já está em andamento.");
      return;
    }
    const snapshot = this.getText(),
      element = this.editor.element;
    const offset =
      manual && element.selectionEnd > element.selectionStart
        ? element.selectionStart
        : 0;
    const text =
      manual && element.selectionEnd > element.selectionStart
        ? snapshot.slice(offset, element.selectionEnd)
        : snapshot;
    if (
      !text.trim() ||
      (!manual &&
        (this.lastAnalyzed === snapshot || this.blocked.has(snapshot)))
    )
      return;
    if (text.length > 50000) {
      if (manual)
        throw Error(
          "Selecione um trecho de até 50 mil caracteres para revisar.",
        );
      return;
    }
    this.running = true;
    const sequence = this.sequence;
    $("#review-text").textContent = "Revisando…";
    try {
      const result = await runOperation("text.review", { text });
      if (snapshot !== this.getText() || sequence !== this.sequence) {
        if (manual)
          this.toast("O texto mudou durante a revisão. Revise novamente.");
        return;
      }
      this.result = { ...result, snapshot, offset };
      this.cloud = result.provider === "openai";
      this.lastAnalyzed = snapshot;
      $("#review-text").textContent =
        "Revisar texto (" + result.suggestions.length + ")";
      if (!manual && ["auto", "auto-all"].includes(this.getMode())) {
        const safe =
          this.getMode() === "auto-all"
            ? result.suggestions
            : result.suggestions.filter((item) => item.automatic);
        if (safe.length) this.apply(safe);
      }
      return this.result;
    } finally {
      this.running = false;
      if (!this.result) $("#review-text").textContent = "Revisar texto";
      if (
        sequence !== this.sequence &&
        this.getMode() !== "off" &&
        !this.applying
      )
        this.changed();
    }
  }
  async open() {
    const result = await this.analyze(true);
    if (!result) return;
    this.modal(
      "Revisão de texto",
      '<p id="review-explanation"></p><div id="review-suggestions" class="asset-list"></div><div class="modal-actions"><button id="review-apply" class="primary">Aplicar selecionadas</button><button id="review-again">Revisar novamente</button><button id="review-close">Fechar</button></div><p class="field-hint">As alterações entram juntas no histórico do editor. Use Desfazer revisão ou Ctrl+Z. O revisor não gera HTML nem publica.</p>',
    );
    $("#review-explanation").textContent =
      result.provider === "local"
        ? "Regras e dicionário locais de português. Confira o contexto das sugestões; o modo leve não faz uma análise linguística completa."
        : "Revisão contextual por API. Confira as sugestões antes de aplicar.";
    const controls = [];
    for (const item of result.suggestions) {
      const row = document.createElement("label"),
        check = document.createElement("input"),
        info = document.createElement("div"),
        before = document.createElement("del"),
        after = document.createElement("ins"),
        reason = document.createElement("small");
      row.className = "asset-row";
      info.className = "asset-info";
      check.type = "checkbox";
      check.checked = item.automatic;
      before.textContent = item.before || "(inserção)";
      after.textContent = item.after || "(remover)";
      reason.textContent = item.reason;
      info.append(before, document.createTextNode(" → "), after, reason);
      row.append(check, info);
      $("#review-suggestions").append(row);
      controls.push({ check, item });
    }
    if (!controls.length)
      $("#review-suggestions").textContent =
        "Nenhuma correção identificada por este revisor.";
    $("#review-apply").disabled = !controls.length;
    $("#review-apply").onclick = () =>
      this.guard(() => {
        this.apply(controls.filter((c) => c.check.checked).map((c) => c.item));
        $("#modal").close();
      });
    $("#review-again").onclick = () => this.guard(() => this.open());
    $("#review-close").onclick = () => $("#modal").close();
  }
  apply(items) {
    const result = this.result;
    if (!result || result.snapshot !== this.getText())
      throw Error("O texto mudou. Revise novamente antes de aplicar.");
    if (!items.length) throw Error("Selecione ao menos uma sugestão.");
    const before = this.getText();
    let after = before;
    for (const item of [...items].sort(
      (a, b) => b.start - a.start || b.end - a.end,
    )) {
      const start = result.offset + item.start,
        end = result.offset + item.end;
      if (after.slice(start, end) !== item.before)
        throw Error(
          "A sugestão não corresponde ao trecho atual. Revise novamente.",
        );
      after = after.slice(0, start) + item.after + after.slice(end);
    }
    this.blocked.add(before);
    if (this.blocked.size > 100)
      this.blocked.delete(this.blocked.values().next().value);
    this.applying = true;
    try {
      this.editor.record();
      this.editor.replace(after, 0, before.length);
      this.revision = { before, after };
      $("#review-undo").disabled = false;
      this.result = null;
      this.lastAnalyzed = after;
      $("#review-text").textContent = "Revisar texto";
    } finally {
      this.applying = false;
    }
    this.toast(
      items.length + " correção(ões) aplicada(s). Você pode desfazer.",
    );
  }
  undo() {
    if (!this.revision) return;
    if (this.getText() !== this.revision.after)
      return this.toast(
        "Há outras edições depois da revisão. Use Ctrl+Z para percorrer o histórico.",
        true,
      );
    this.blocked.add(this.revision.before);
    this.editor.moveHistory(-1);
    this.revision = null;
    this.result = null;
    $("#review-undo").disabled = true;
    this.toast("Revisão desfeita.");
  }
  async settings() {
    const config = await this.api("/api/text-review/settings");
    this.modal(
      "Configurar revisor leve",
      '<p>O modo local usa regras de português e não carrega um modelo de linguagem. A API é opcional e processa os trechos fora do servidor.</p><div class="stack"><label>Revisor<select id="review-provider"><option value="local">Leve, local, sem GPU e sem chave</option><option value="openai">OpenAI por API (opcional)</option></select></label><label>Modelo da API<input id="review-model"></label><label>Chave da API<input id="review-key" type="password" autocomplete="new-password" placeholder="Vazio mantém a chave salva"></label><label>Operação da chave<select id="review-key-action"><option value="keep">Manter</option><option value="replace">Substituir</option><option value="remove">Remover</option></select></label><label class="inline-check"><input id="review-cloud" type="checkbox">Autorizo enviar trechos de texto à OpenAI quando este provedor estiver selecionado. O uso pode ser cobrado pela API.</label><label>Termos que devem ser preservados, um por linha<textarea id="review-words" rows="4"></textarea></label></div><p id="review-key-status" class="field-hint"></p><div class="modal-actions"><button id="review-save" class="primary">Salvar configuração</button><button id="review-test">Testar frase de exemplo</button></div>',
    );
    $("#review-provider").value = config.provider;
    $("#review-model").value = config.model;
    $("#review-cloud").checked = config.allow_cloud;
    $("#review-words").value = (config.ignored_words || []).join("\n");
    $("#review-key-status").textContent = config.key_configured
      ? "Chave salva no servidor; ela não é devolvida ao navegador."
      : "Nenhuma chave salva. O modo local já está disponível.";
    $("#review-key").oninput = () => {
      if ($("#review-key").value) $("#review-key-action").value = "replace";
    };
    $("#review-save").onclick = () =>
      this.guard(async () => {
        await this.api("/api/text-review/settings", {
          method: "POST",
          body: JSON.stringify({
            provider: $("#review-provider").value,
            model: $("#review-model").value.trim(),
            allow_cloud: $("#review-cloud").checked,
            ignored_words: $("#review-words")
              .value.split(/\r?\n/)
              .map((x) => x.trim())
              .filter(Boolean),
            api_key: $("#review-key").value,
            key_action: $("#review-key-action").value,
          }),
        });
        this.cloud = $("#review-provider").value === "openai";
        this.reset();
        this.toast("Configuração do revisor salva.");
        $("#modal").close();
      });
    $("#review-test").onclick = () =>
      this.guard(async () => {
        const result = await runOperation("text.review", {
          text: "Voce nao configurou a aplicacao,confira a conexao",
        });
        this.toast(
          result.suggestions.length +
            " sugestão(ões) na frase de exemplo, usando a configuração salva.",
        );
      });
  }
}
