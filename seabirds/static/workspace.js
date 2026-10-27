const $ = (selector) => document.querySelector(selector);
export const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
export function openSettings(focus = "template-path") {
  const drawer = $("#settings-drawer");
  if (!drawer.open) drawer.showModal();
  const target = $("#" + focus);
  if (target) {
    target.scrollIntoView({ block: "center" });
    target.focus({ preventScroll: true });
  }
}
export function updateWorkspace(dirty = false) {
  document.body.dataset.dirty = String(dirty);
  for (const [field, target, fallback] of [
    ["template-path", "meta-template", "Selecionar template"],
    ["output-path", "meta-output", "Definir destino do HTML"],
    ["images-dir", "meta-images", "Selecionar pasta"],
  ]) {
    const path = $("#" + field).value.trim();
    const label = $("#" + target);
    label.textContent = path
      ? path.replace(/\\/g, "/").split("/").filter(Boolean).at(-1)
      : fallback;
    label.parentElement.parentElement.title = path || fallback;
  }
}
export function setupWorkspace() {
  for (const button of document.querySelectorAll(".app-sidebar button")) {
    button.setAttribute("aria-label", button.textContent.trim());
    button.title = button.textContent.trim();
  }
  document.querySelectorAll("[data-workspace-action]").forEach((button) => {
    button.onclick = () => {
      button.closest("details").open = false;
      document.getElementById(button.dataset.workspaceAction).click();
    };
  });
  document
    .querySelectorAll("[data-open-settings]")
    .forEach((button) =>
      button.addEventListener("click", () =>
        openSettings(button.dataset.openSettings),
      ),
    );
  for (const id of ["close-settings", "done-settings"])
    $("#" + id).onclick = () => $("#settings-drawer").close();
  $("#settings-drawer").addEventListener("click", (event) => {
    if (event.target !== $("#settings-drawer")) return;
    const b = event.target.getBoundingClientRect();
    if (event.clientX < b.left || event.clientX > b.right) event.target.close();
  });
  document.querySelectorAll("[data-editor-view]").forEach(
    (button) =>
      (button.onclick = () => {
        $(".editor-layout").dataset.view = button.dataset.editorView;
        document.querySelectorAll("[data-editor-view]").forEach((item) => {
          item.classList.toggle("active", item === button);
          item.setAttribute("aria-pressed", String(item === button));
        });
      }),
  );
  $("#focus-mode").onclick = () => {
    const expanded = document.body.classList.toggle("focus-mode");
    $("#focus-mode").setAttribute("aria-pressed", String(expanded));
    $("#focus-mode").title = expanded
      ? "Restaurar área de trabalho"
      : "Expandir área de trabalho";
  };
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) {
      document.body.classList.remove("focus-mode");
      $("#focus-mode").setAttribute("aria-pressed", "false");
    }
  });
  document.querySelectorAll("[data-tab]").forEach((button) =>
    button.addEventListener("click", () => {
      $("#active-screen").textContent = button.textContent.trim();
    }),
  );
  document.querySelectorAll("[data-command]").forEach((button) =>
    button.addEventListener("click", () => {
      const menu = button.closest("details");
      if (menu) menu.open = false;
    }),
  );
}
