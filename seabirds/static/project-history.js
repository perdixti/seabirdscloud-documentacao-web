import { icon } from "./workspace.js";

const normalize = (text) =>
  String(text || "")
    .normalize("NFC")
    .toLocaleLowerCase("pt-BR")
    .trim();

export function renderProjectHistory({
  projects,
  autosaves,
  onProject,
  onAutosave,
}) {
  const entries = [],
    groups = [];
  function section(items, container, nameOf, select, autosave = false) {
    const byName = new Map();
    for (const item of items) {
      const name = nameOf(item) || "Sem título",
        key = normalize(name);
      if (!byName.has(key)) byName.set(key, { name, items: [] });
      byName.get(key).items.push(item);
    }
    for (const { name, items: versions } of byName.values()) {
      const grouped = autosave || versions.length > 1;
      let parent = container,
        group = null;
      if (grouped) {
        const details = document.createElement("details"),
          summary = document.createElement("summary");
        const title = document.createElement("strong"),
          count = document.createElement("span");
        const children = document.createElement("div");
        details.className = "history-project-group";
        title.textContent = name;
        count.className = "history-group-count";
        summary.innerHTML = icon("chevron");
        summary.append(title, count);
        children.className = "history-group-versions";
        details.append(summary, children);
        container.append(details);
        parent = children;
        group = {
          details,
          count,
          entries: [],
          wasOpen: false,
          unit: autosave ? ["versão", "versões"] : ["rascunho", "rascunhos"],
        };
        groups.push(group);
      }
      for (const item of versions) {
        const button = document.createElement("button");
        const label = document.createElement("span");
        if (autosave) label.textContent = item.name;
        else if (
          grouped &&
          item.updated_at &&
          !Number.isNaN(Date.parse(item.updated_at))
        ) {
          label.textContent =
            "Atualizado em " +
            new Date(item.updated_at).toLocaleString("pt-BR");
        } else label.textContent = name;
        button.append(label);
        button.title = autosave ? item.path : name;
        button.onclick = () => select(item);
        parent.append(button);
        const entry = {
          button,
          query: normalize(
            [name, item.name, item.path].filter(Boolean).join(" "),
          ),
        };
        entries.push(entry);
        if (group) group.entries.push(entry);
      }
    }
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = autosave
        ? "Nenhum autosave encontrado."
        : "Nenhum projeto recente.";
      container.append(empty);
    }
  }
  section(
    projects,
    document.querySelector("#project-list"),
    (item) => item.title,
    onProject,
  );
  section(
    autosaves,
    document.querySelector("#legacy-list"),
    (item) => item.project,
    onAutosave,
    true,
  );
  const empty = document.createElement("p");
  empty.className = "empty";
  empty.textContent = "Nenhum histórico corresponde ao filtro.";
  empty.hidden = true;
  document.querySelector("#legacy-list").after(empty);
  const filter = document.querySelector("#project-filter");
  let filtering = false;
  const applyFilter = () => {
    const query = normalize(filter.value);
    if (query && !filtering)
      for (const group of groups) group.wasOpen = group.details.open;
    for (const entry of entries)
      entry.button.hidden = !entry.query.includes(query);
    for (const group of groups) {
      const visible = group.entries.filter(
        (entry) => !entry.button.hidden,
      ).length;
      group.details.hidden = !visible;
      group.count.textContent = `${query && visible !== group.entries.length ? visible + " de " : ""}${group.entries.length} ${group.unit[group.entries.length === 1 ? 0 : 1]}`;
      if (query) group.details.open = !!visible;
      else if (filtering) group.details.open = group.wasOpen;
    }
    empty.hidden = !query || entries.some((entry) => !entry.button.hidden);
    filtering = !!query;
  };
  filter.oninput = applyFilter;
  applyFilter();
}
