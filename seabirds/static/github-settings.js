const $ = (selector) => document.querySelector(selector);

export async function openGitHubSettings({api, modal, directory = "", afterSave, onBack}) {
  let settings = await api("/api/generator/github/settings?directory=" + encodeURIComponent(directory));
  const target = settings.directory || "";
  modal("Configurar GitHub",
    '<p>Centralize a autenticação e o autor dos commits. As alterações valem para as próximas operações, sem reiniciar o servidor.</p><div class="stack"><label>Nome do autor<input id="github-settings-name" maxlength="200" autocomplete="name"></label><label>E-mail do autor<input id="github-settings-email" type="email" maxlength="254" autocomplete="email"></label><p id="github-settings-scope" class="field-hint"></p><label>Token do GitHub (segredo)<input id="github-settings-token" type="password" autocomplete="new-password" spellcheck="false" autocapitalize="none" placeholder="Cole um novo token; deixe vazio para manter o atual"></label><p id="github-settings-status" class="field-hint" role="status"></p><p class="field-hint">O token é criptografado no servidor e não será exibido novamente. Use acesso ao repositório com Contents: leitura e gravação; Actions: leitura para consultar a pipeline.</p><p id="github-settings-http" class="github-notice" hidden>Você está usando HTTP: o envio do segredo não tem criptografia de transporte. Prefira HTTPS para enviar credenciais.</p><p id="github-settings-error" class="github-notice" role="alert" hidden></p></div><div class="modal-actions"><button id="github-settings-save" class="primary">Salvar configurações</button><button id="github-settings-remove">Remover token</button><button id="github-settings-back" hidden>Voltar à revisão</button></div>');
  $("#github-settings-name").value = settings.author.name || settings.repository_author?.name || "";
  $("#github-settings-email").value = settings.author.email || settings.repository_author?.email || "";
  $("#github-settings-scope").textContent = target
    ? "Este autor será aplicado ao repositório " + settings.repository + " e usado como padrão nos próximos clones."
    : "Este autor será usado como padrão nos próximos clones e em publicações sem autor configurado no Git.";
  $("#github-settings-http").hidden = document.location.protocol === "https:";
  const secretField = $("#github-settings-token");
  $("#modal").addEventListener("close", () => { secretField.value = ""; }, {once: true});
  const paintStatus = () => {
    $("#github-settings-status").textContent = settings.token_error || (settings.token_configured
      ? settings.token_source === "web" ? "Token configurado pelo gerenciamento web." : "Token configurado pela variável do servidor. Cole outro para substituí-lo pela web."
      : "Nenhum token configurado na aplicação. SSH e outras credenciais Git existentes continuam disponíveis.");
    $("#github-settings-remove").disabled = !settings.token_configured;
  };
  paintStatus();
  const submit = async (action) => {
    const name = $("#github-settings-name"), email = $("#github-settings-email"), secret = $("#github-settings-token");
    if (action !== "remove" && (!name.value.trim() || !email.value.trim() || !email.reportValidity())) {
      $("#github-settings-error").hidden = false;
      $("#github-settings-error").textContent = "Preencha o nome e um e-mail válido para os commits.";
      return;
    }
    const save = $("#github-settings-save"), remove = $("#github-settings-remove"), back = $("#github-settings-back"), error = $("#github-settings-error");
    save.disabled = remove.disabled = back.disabled = true;
    error.hidden = true;
    save.textContent = "Salvando…";
    try {
      const result = await api("/api/generator/github/settings", {method: "POST", body: JSON.stringify({
        directory: action === "remove" ? "" : target,
        name: action === "remove" ? settings.author.name : name.value.trim(),
        email: action === "remove" ? settings.author.email : email.value.trim(),
        token_action: action === "remove" ? "remove" : secret.value ? "replace" : "keep",
        token: action === "remove" ? "" : secret.value,
      })});
      secret.value = "";
      settings = result;
      if ($("#github-settings-token") !== secret) return;
      if (afterSave) return await afterSave(result);
      paintStatus();
      $("#github-settings-status").textContent += " Configurações salvas.";
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      save.disabled = back.disabled = false;
      remove.disabled = !settings.token_configured;
      save.textContent = "Salvar configurações";
    }
  };
  $("#github-settings-save").onclick = () => submit("save");
  $("#github-settings-remove").onclick = () => {
    if (confirm("Remover o token da aplicação? O token da variável de ambiente também deixará de ser usado pela aplicação. Isso não revoga o token no GitHub.")) return submit("remove");
  };
  $("#github-settings-back").hidden = !onBack;
  $("#github-settings-back").onclick = onBack;
}
