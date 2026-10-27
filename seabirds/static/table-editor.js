export function openTableBuilder(mode, modal, insert) {
  modal(
    mode === "tablecard" ? "Inserir tabela card" : "Inserir tabela",
    `<div class="table-controls"><label>Linhas<input id="table-rows" type="number" min="1" max="100" value="3"></label><label>Colunas<input id="table-cols" type="number" min="1" max="30" value="3"></label><button id="table-create">Criar estrutura</button></div><p>Selecione uma célula para inserir ou remover linhas e colunas. O botão direito abre as mesmas operações.</p><div id="table-operations" class="table-operations"></div><div class="table-scroll"><table id="table-grid" class="table-builder"></table></div><div class="modal-actions"><button id="table-insert" class="primary">Inserir no editor</button></div>`,
  );
  const $ = (s) => document.querySelector(s);
  let headers = ["Coluna 1", "Coluna 2", "Coluna 3"],
    rows = Array.from({ length: 3 }, () => ["", "", ""]),
    selected = { row: 0, col: 0 };
  let context;
  const operations = {
    above: [
      "Linha acima",
      () =>
        rows.splice(
          Math.max(0, selected.row),
          0,
          headers.map(() => ""),
        ),
    ],
    below: [
      "Linha abaixo",
      () =>
        rows.splice(
          selected.row < 0 ? 0 : selected.row + 1,
          0,
          headers.map(() => ""),
        ),
    ],
    removeRow: [
      "Remover linha",
      () => {
        if (rows.length > 1) rows.splice(Math.max(0, selected.row), 1);
      },
    ],
    left: ["Coluna à esquerda", () => addColumn(selected.col)],
    right: ["Coluna à direita", () => addColumn(selected.col + 1)],
    removeCol: [
      "Remover coluna",
      () => {
        if (headers.length > 1) {
          headers.splice(selected.col, 1);
          rows.forEach((row) => row.splice(selected.col, 1));
        }
      },
    ],
  };
  function addColumn(index) {
    headers.splice(index, 0, "Nova coluna");
    rows.forEach((row) => row.splice(index, 0, ""));
  }
  function run(key) {
    if (rows.length >= 100 && ["above", "below"].includes(key)) return;
    if (headers.length >= 30 && ["left", "right"].includes(key)) return;
    operations[key][1]();
    selected.row = Math.min(selected.row, rows.length - 1);
    selected.col = Math.min(selected.col, headers.length - 1);
    context?.remove();
    render();
  }
  function select(row, col) {
    selected = { row, col };
    $("#table-grid")
      .querySelectorAll("td,th")
      .forEach((cell) =>
        cell.classList.toggle(
          "selected",
          Number(cell.dataset.row) === row && Number(cell.dataset.col) === col,
        ),
      );
  }
  function cell(value, row, col) {
    const td = document.createElement(row < 0 ? "th" : "td");
    td.dataset.row = row;
    td.dataset.col = col;
    const field = document.createElement(row < 0 ? "input" : "textarea");
    field.value = value;
    field.setAttribute(
      "aria-label",
      `${row < 0 ? "Cabeçalho" : "Linha " + (row + 1)}, coluna ${col + 1}`,
    );
    if (row >= 0) field.rows = 2;
    field.addEventListener("input", () => {
      if (row < 0) headers[col] = field.value;
      else rows[row][col] = field.value;
    });
    field.addEventListener("focus", () => select(row, col));
    field.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      select(row, col);
      context?.remove();
      context = document.createElement("div");
      context.className = "table-context";
      context.style.left =
        Math.min(event.clientX, window.innerWidth - 200) + "px";
      context.style.top =
        Math.min(event.clientY, window.innerHeight - 260) + "px";
      for (const [key, [label]] of Object.entries(operations)) {
        const button = document.createElement("button");
        button.textContent = label;
        button.onclick = () => run(key);
        context.append(button);
      }
      $("#modal").append(context);
    });
    td.append(field);
    return td;
  }
  function render() {
    const grid = $("#table-grid");
    grid.replaceChildren();
    const header = document.createElement("tr");
    headers.forEach((value, col) => header.append(cell(value, -1, col)));
    const thead = document.createElement("thead");
    thead.append(header);
    grid.append(thead);
    const body = document.createElement("tbody");
    rows.forEach((values, row) => {
      const tr = document.createElement("tr");
      values.forEach((value, col) => tr.append(cell(value, row, col)));
      body.append(tr);
    });
    grid.append(body);
    select(selected.row, selected.col);
    $("#table-rows").value = rows.length;
    $("#table-cols").value = headers.length;
  }
  for (const [key, [label]] of Object.entries(operations)) {
    const button = document.createElement("button");
    button.textContent = label;
    button.dataset.tableOperation = key;
    button.onclick = () => run(key);
    $("#table-operations").append(button);
  }
  $("#table-create").onclick = () => {
    const count = Math.max(
      1,
      Math.min(100, Number($("#table-rows").value) || 1),
    );
    const columns = Math.max(
      1,
      Math.min(30, Number($("#table-cols").value) || 1),
    );
    headers = Array.from(
      { length: columns },
      (_, i) => headers[i] ?? `Coluna ${i + 1}`,
    );
    rows = Array.from({ length: count }, (_, r) =>
      Array.from({ length: columns }, (_, c) => rows[r]?.[c] ?? ""),
    );
    selected = { row: 0, col: 0 };
    render();
  };
  $("#table-insert").onclick = () => {
    const clean = (value) =>
      value.replace(/\|/g, "\\|").replace(/\r?\n/g, "<br>");
    const line = (values) => "| " + values.map(clean).join(" | ") + " |";
    insert(
      `\n\x60\x60\x60${mode}\n${line(headers)}\n${line(headers.map(() => "---"))}\n${rows.map(line).join("\n")}\n\x60\x60\x60\n`,
    );
    $("#modal").close();
  };
  const closeContext = (event) => {
    if (context && !context.contains(event.target)) context.remove();
  };
  $("#modal").addEventListener("click", closeContext);
  $("#modal").addEventListener(
    "close",
    () => {
      context?.remove();
      $("#modal").removeEventListener("click", closeContext);
    },
    { once: true },
  );
  render();
}
