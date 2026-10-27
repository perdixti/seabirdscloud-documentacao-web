import { icon } from "./workspace.js";
const $ = (selector) => document.querySelector(selector);
function refs(text) {
  const result = [];
  const protectedRanges = [];
  let fence = null,
    offset = 0;
  for (const line of text.split(/(?<=\n)/)) {
    const marker = line.match(/^\s{0,3}(?:>\s*)?(`{3,}|~{3,})/);
    if (marker) {
      if (!fence)
        fence = {
          symbol: marker[1][0],
          length: marker[1].length,
          start: offset,
        };
      else if (
        marker[1][0] === fence.symbol &&
        marker[1].length >= fence.length
      ) {
        protectedRanges.push([fence.start, offset + line.length]);
        fence = null;
      }
    }
    offset += line.length;
  }
  if (fence) protectedRanges.push([fence.start, text.length]);
  for (const match of text.matchAll(/(`+)[\s\S]*?\1(?!`)/g))
    protectedRanges.push([match.index, match.index + match[0].length]);
  const pattern =
    /!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)/g;
  for (const match of text.matchAll(pattern)) {
    if (
      protectedRanges.some(
        ([start, end]) => match.index >= start && match.index < end,
      )
    )
      continue;
    const destination = match[1] ? "<" + match[1] + ">" : match[2];
    const tokenStart =
      match.index + match[0].indexOf(destination, match[0].indexOf("](") + 2);
    result.push({
      url: match[1] || match[2],
      start: match.index,
      end: match.index + match[0].length,
      tokenStart,
      tokenEnd: tokenStart + destination.length,
    });
  }
  return result;
}
const fields = (record) => ({
  id: record.id,
  path: record.path,
  filename: record.filename,
  web_path: record.web_path,
});
export class ImageManager {
  constructor(options) {
    Object.assign(this, options);
    this.records = [];
    this.epoch = 0;
    for (const id of ["manage-images", "manage-images-bottom"])
      $("#" + id).onclick = () => this.guard(() => this.openManager());
    $("#unused-images").onclick = () =>
      this.guard(() => this.openManager("unused"));
  }
  async guard(action) {
    try {
      await action();
    } catch (error) {
      this.toast(error.message, true);
    }
  }
  publish(dirty = false) {
    this.setImages(this.records.map(fields));
    this.render();
    if (dirty) this.changed();
  }
  async load(records = []) {
    const epoch = ++this.epoch;
    const initial = new Set(records.map((record) => record.id));
    this.records = records.map((record) => ({
      ...record,
      thumbnail: "/api/generator/image/" + record.id,
    }));
    this.publish();
    try {
      const result = await this.api("/api/generator/images/sync", {
        method: "POST",
        body: JSON.stringify(this.data()),
      });
      if (epoch !== this.epoch) return;
      const loaded = new Set(result.map((record) => record.id));
      this.records = [
        ...result,
        ...this.records.filter(
          (record) => !initial.has(record.id) && !loaded.has(record.id),
        ),
      ];
      this.publish();
    } catch (error) {
      if (records.length) this.toast(error.message, true);
    }
  }
  add(record) {
    this.records = this.records.filter((item) => item.id !== record.id);
    this.records.push(record);
    this.publish();
  }
  active(record) {
    return (
      !record.trashed &&
      refs($("#editor").value).some(
        (reference) => reference.url === record.web_path,
      )
    );
  }
  render() {
    const active = this.records.filter((record) => this.active(record));
    const unused = this.records.filter((record) => !this.active(record));
    const list = $("#image-thumbnails");
    list.replaceChildren();
    $("#attachments").hidden = !this.records.length;
    $("#image-count").textContent = active.length;
    $("#unused-images").hidden = !unused.length;
    $("#unused-images").textContent = `${unused.length} fora do documento`;
    for (const record of active) {
      const card = document.createElement("article");
      card.className = "image-card";
      card.dataset.imageId = record.id;
      const open = document.createElement("button");
      open.className = "image-open";
      open.title = "Ampliar " + record.filename;
      const image = document.createElement("img");
      image.src = record.thumbnail;
      image.alt = record.filename;
      open.append(image);
      open.onclick = () => this.view(record);
      const remove = document.createElement("button");
      remove.className = "image-remove";
      remove.title = "Remover do documento";
      remove.setAttribute(
        "aria-label",
        "Remover " + record.filename + " do documento",
      );
      remove.innerHTML = icon("close");
      remove.onclick = () => {
        this.removeReferences([record]);
        this.toast("Imagem removida do documento. Ctrl+Z desfaz.");
      };
      const caption = document.createElement("div");
      caption.className = "image-caption";
      const text = document.createElement("span"),
        name = document.createElement("strong"),
        folder = document.createElement("small");
      name.textContent = record.filename;
      folder.textContent = record.missing
        ? "Arquivo não encontrado"
        : record.path.replace(/\\/g, "/").split("/").slice(-2, -1)[0];
      text.title = record.path;
      text.append(name, folder);
      const manage = document.createElement("button");
      manage.innerHTML = icon("settings");
      manage.title = "Mover ou excluir esta imagem";
      manage.setAttribute("aria-label", "Gerenciar " + record.filename);
      manage.onclick = () => this.openManager();
      caption.append(text, manage);
      card.append(open, remove, caption);
      list.append(card);
    }
  }
  removeReferences(records) {
    const urls = new Set(records.map((record) => record.web_path));
    const original = $("#editor").value;
    let updated = original;
    for (const reference of refs(original).reverse())
      if (urls.has(reference.url))
        updated =
          updated.slice(0, reference.start) + updated.slice(reference.end);
    if (updated !== original) this.editor.replace(updated, 0, original.length);
    else this.publish(true);
  }
  replaceReference(before, after) {
    const original = $("#editor").value;
    let updated = original;
    for (const reference of refs(original).reverse())
      if (reference.url === before)
        updated =
          updated.slice(0, reference.tokenStart) +
          (/[\s()]/.test(after.web_path)
            ? "<" + after.web_path + ">"
            : after.web_path) +
          updated.slice(reference.tokenEnd);
    if (updated !== original) this.editor.replace(updated, 0, original.length);
    else this.publish(true);
  }
  markdown(record) {
    const url = /[\s()]/.test(record.web_path)
      ? "<" + record.web_path + ">"
      : record.web_path;
    return "![imagem](" + url + ")";
  }
  view(record) {
    this.modal(
      record.filename,
      '<img class="image-large" id="asset-large" alt="Imagem do documento"><p class="image-path" id="asset-path"></p>',
    );
    $("#asset-large").src = record.thumbnail;
    $("#asset-path").textContent = record.path;
  }
  patch(record) {
    this.records = this.records.map((item) =>
      item.id === record.id ? record : item,
    );
    this.publish();
  }
  async insert(record) {
    if (record.trashed) {
      record = await this.api(
        "/api/generator/images/" + record.id + "/restore",
        { method: "POST" },
      );
      this.patch(record);
    }
    if (!this.active(record))
      this.editor.replace("\n" + this.markdown(record) + "\n");
    this.openManager();
  }
  async openManager(filter = "all") {
    this.modal(
      "Imagens do documento",
      `<p>Remova referências do texto, corrija a pasta de uma imagem ou envie arquivos para uma lixeira recuperável.</p><div class="asset-toolbar"><button id="asset-import">${icon("folder")}Ler imagens de uma pasta</button><select id="asset-filter" aria-label="Filtrar imagens"><option value="all">Todas as imagens</option><option value="active">No documento</option><option value="unused">Sem uso no texto</option><option value="trash">Na lixeira</option></select><span id="asset-total"></span></div><div id="asset-list" class="asset-list"></div><div class="modal-actions"><button id="assets-remove">Remover referências</button><button id="assets-move">${icon("move")}Mover selecionadas</button><button id="assets-trash" class="danger-button">${icon("trash")}Enviar à lixeira</button><button id="assets-delete" class="danger-button" hidden>${icon("trash")}Excluir selecionadas definitivamente</button></div>`,
    );
    $("#asset-filter").value = filter;
    const checked = new Set();
    const selected = () =>
      this.records.filter((record) => checked.has(record.id));
    const draw = () => {
      const list = $("#asset-list");
      list.replaceChildren();
      const mode = $("#asset-filter").value;
      for (const id of ["assets-remove", "assets-move", "assets-trash"])
        $("#" + id).hidden = mode === "trash";
      $("#assets-delete").hidden = mode !== "trash";
      const records = this.records.filter(
        (record) =>
          mode === "all" ||
          (mode === "trash" && record.trashed) ||
          (mode === "active" && this.active(record)) ||
          (mode === "unused" && !this.active(record) && !record.trashed),
      );
      $("#asset-total").textContent = records.length + " imagem(ns)";
      for (const record of records) {
        const row = document.createElement("article");
        row.className = "asset-row";
        row.dataset.assetId = record.id;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = checked.has(record.id);
        checkbox.setAttribute("aria-label", "Selecionar " + record.filename);
        checkbox.onchange = () => {
          if (checkbox.checked) checked.add(record.id);
          else checked.delete(record.id);
        };
        const image = document.createElement("img");
        image.src = record.thumbnail;
        image.alt = "";
        const info = document.createElement("div");
        info.className = "asset-info";
        const name = document.createElement("strong"),
          path = document.createElement("small"),
          status = document.createElement("span");
        name.textContent = record.filename;
        path.textContent = record.path;
        status.className = "asset-status";
        status.textContent = record.trashed
          ? "Na lixeira"
          : record.missing
            ? "Arquivo não encontrado"
            : this.active(record)
              ? "No documento"
              : "Sem referência no texto";
        info.append(name, path, status);
        const actions = document.createElement("div");
        actions.className = "asset-actions";
        const action = (name, title, callback, css = "") => {
          const button = document.createElement("button");
          button.innerHTML = icon(name);
          button.title = title;
          button.setAttribute("aria-label", title);
          button.className = css;
          button.onclick = () => this.guard(callback);
          actions.append(button);
        };
        action(
          record.trashed ? "undo" : "plus",
          record.trashed
            ? "Restaurar e inserir " + record.filename
            : "Inserir " + record.filename,
          () => this.insert(record),
        );
        if (!record.trashed) {
          action("move", "Mover " + record.filename, () => this.move([record]));
          action(
            "trash",
            "Enviar " + record.filename + " à lixeira",
            () => this.confirmTrash([record]),
            "danger",
          );
        } else {
          action(
            "trash",
            "Excluir definitivamente " + record.filename,
            () => this.confirmDelete([record]),
            "danger",
          );
        }
        row.append(checkbox, image, info, actions);
        list.append(row);
      }
      if (!records.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent =
          "Nenhuma imagem nesta categoria. Você pode ler as imagens da pasta selecionada.";
        list.append(empty);
      }
    };
    $("#asset-filter").onchange = () => {
      checked.clear();
      draw();
    };
    $("#assets-remove").onclick = () => {
      if (!selected().length) return this.toast("Selecione as imagens.", true);
      this.removeReferences(selected());
      this.openManager("unused");
    };
    $("#assets-move").onclick = () => this.guard(() => this.move(selected()));
    $("#assets-trash").onclick = () =>
      this.guard(() => this.confirmTrash(selected()));
    $("#assets-delete").onclick = () =>
      this.guard(() => this.confirmDelete(selected()));
    $("#asset-import").onclick = () =>
      this.guard(async () => {
        const target = document.createElement("input");
        target.value = $("#images-dir").value;
        if (!(await this.pickFolder(target))) {
          this.openManager();
          return;
        }
        const records = await this.api("/api/generator/images/import-folder", {
          method: "POST",
          body: JSON.stringify({
            directory: target.value,
            web_path: $("#image-web-path").value || "imagens",
          }),
        });
        for (const record of records)
          if (!this.records.some((item) => item.id === record.id))
            this.records.push(record);
        this.publish(true);
        this.openManager("unused");
      });
    draw();
  }
  confirmDelete(records) {
    if (!records.length) throw Error("Selecione as imagens da lixeira.");
    if (records.some((record) => !record.trashed))
      throw Error(
        "Apenas imagens na lixeira podem ser excluídas definitivamente.",
      );
    this.modal(
      "Excluir imagens definitivamente",
      '<p>Esta ação apaga os arquivos da lixeira e não pode ser desfeita.</p><ul id="delete-image-list" class="image-path"></ul><div class="modal-actions"><button id="confirm-image-delete" class="primary danger-button">Excluir definitivamente</button><button id="cancel-image-delete">Cancelar</button></div>',
    );
    for (const record of records) {
      const item = document.createElement("li");
      item.textContent = record.filename + " — " + record.path;
      $("#delete-image-list").append(item);
    }
    $("#cancel-image-delete").onclick = () => this.openManager("trash");
    $("#cancel-image-delete").focus();
    $("#confirm-image-delete").onclick = () =>
      this.guard(async () => {
        const button = $("#confirm-image-delete");
        const cancel = $("#cancel-image-delete");
        if (button.disabled) return;
        button.disabled = true;
        cancel.disabled = true;
        try {
          for (const record of records) {
            await this.api("/api/generator/images/" + record.id, {
              method: "DELETE",
              body: JSON.stringify({ confirm: true }),
            });
            this.removeReferences([record]);
            this.records = this.records.filter((item) => item.id !== record.id);
            this.publish(true);
          }
        } catch (error) {
          this.openManager("trash");
          throw error;
        } finally {
          button.disabled = false;
          cancel.disabled = false;
        }
        this.openManager("trash");
        this.toast(
          records.length === 1
            ? "Imagem excluída definitivamente."
            : "Imagens excluídas definitivamente.",
        );
      });
  }
  confirmTrash(records) {
    if (!records.length) throw Error("Selecione as imagens.");
    this.modal(
      "Enviar imagens para a lixeira",
      '<p id="trash-description"></p><p>As referências serão removidas do documento e os arquivos sairão da pasta atual. Você poderá restaurá-los em Gerenciar imagens → Na lixeira.</p><div class="modal-actions"><button id="confirm-image-trash" class="primary danger-button">Enviar à lixeira</button><button id="cancel-image-trash">Cancelar</button></div>',
    );
    $("#trash-description").textContent =
      records.length === 1
        ? records[0].path
        : `${records.length} arquivos selecionados.`;
    $("#cancel-image-trash").onclick = () => this.openManager();
    $("#confirm-image-trash").onclick = () =>
      this.guard(async () => {
        for (const record of records) {
          const result = await this.api(
            "/api/generator/images/" + record.id + "/trash",
            { method: "POST" },
          );
          this.patch(result);
          this.removeReferences([record]);
        }
        this.publish(true);
        this.openManager("trash");
        this.toast("Arquivos enviados à lixeira. Eles podem ser restaurados.");
      });
  }
  async move(records) {
    if (!records.length) throw Error("Selecione as imagens.");
    const target = document.createElement("input");
    target.value =
      $("#images-dir").value || records[0].path.replace(/[\\/][^\\/]+$/, "");
    if (!(await this.pickFolder(target))) {
      this.openManager();
      return;
    }
    this.modal(
      "Mover imagens",
      '<div class="stack"><label>Pasta de destino<input id="image-move-dir"></label><label>Caminho das imagens no HTML<input id="image-move-web"></label><label class="inline-check"><input id="image-move-default" type="checkbox" checked>Usar esta pasta nas próximas colagens</label></div><p>As referências no Markdown serão atualizadas. Arquivos existentes no destino serão preservados.</p><div class="modal-actions"><button id="confirm-image-move" class="primary">Mover imagens</button></div>',
    );
    $("#image-move-dir").value = target.value;
    $("#image-move-web").value = $("#image-web-path").value || "imagens";
    $("#confirm-image-move").onclick = () =>
      this.guard(async () => {
        const directory = $("#image-move-dir").value,
          web_path = $("#image-move-web").value,
          setDefault = $("#image-move-default").checked;
        for (const record of records) {
          const result = await this.api(
            "/api/generator/images/" + record.id + "/move",
            { method: "POST", body: JSON.stringify({ directory, web_path }) },
          );
          this.patch(result);
          this.replaceReference(record.web_path, result);
        }
        if (setDefault) {
          $("#images-dir").value = directory;
          $("#image-web-path").value = web_path;
        }
        this.publish(true);
        this.openManager();
        this.toast("Imagens movidas e referências atualizadas.");
      });
  }
}
