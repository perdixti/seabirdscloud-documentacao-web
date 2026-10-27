export class MarkdownEditor {
  constructor(element, changed) {
    this.element = element;
    this.changed = changed;
    this.history = [];
    this.position = -1;
    this.lastTyped = 0;
    this.reset("");
    element.addEventListener("input", () => {
      this.record(true);
      this.changed();
    });
  }
  reset(value) {
    this.element.value = value;
    this.history = [{ value, start: 0, end: 0 }];
    this.position = 0;
    this.lastTyped = 0;
  }
  record(typing = false) {
    const el = this.element;
    if (this.history[this.position]?.value === el.value) return;
    this.history.splice(this.position + 1);
    const snapshot = {
      value: el.value,
      start: el.selectionStart,
      end: el.selectionEnd,
    };
    if (typing && this.position > 0 && Date.now() - this.lastTyped < 500)
      this.history[this.position] = snapshot;
    else {
      this.history.push(snapshot);
      this.position++;
    }
    if (this.history.length > 200) {
      this.history.shift();
      this.position--;
    }
    this.lastTyped = typing ? Date.now() : 0;
  }
  replace(
    text,
    start = this.element.selectionStart,
    end = this.element.selectionEnd,
    select = false,
  ) {
    this.element.focus();
    this.element.setRangeText(text, start, end, "end");
    if (select) this.element.setSelectionRange(start, start + text.length);
    this.record();
    this.changed();
  }
  wrap(before, after = before, placeholder = "texto") {
    const el = this.element,
      start = el.selectionStart;
    const selected = el.value.slice(start, el.selectionEnd) || placeholder;
    this.replace(before + selected + after);
    el.setSelectionRange(
      start + before.length,
      start + before.length + selected.length,
    );
  }
  lines(transform) {
    const el = this.element,
      start =
        el.selectionStart === 0
          ? 0
          : el.value.lastIndexOf("\n", el.selectionStart - 1) + 1;
    const found = el.value.indexOf("\n", el.selectionEnd);
    const end = found < 0 ? el.value.length : found;
    this.replace(
      transform(el.value.slice(start, end).split("\n")).join("\n"),
      start,
      end,
      true,
    );
  }
  command(name) {
    if (name.startsWith("heading")) {
      const level = Number(name.at(-1));
      this.lines((lines) =>
        lines.map(
          (line) => "#".repeat(level) + " " + line.replace(/^#+\s*/, ""),
        ),
      );
      return;
    }
    const actions = {
      bold: () => this.wrap("**"),
      italic: () => this.wrap("*"),
      inline: () => this.wrap("`"),
      code: () => this.wrap("\n```\n", "\n```\n", "código"),
      link: () =>
        this.wrap("{{link: https://exemplo.com | ", "}}", "texto do link"),
      dash: () =>
        this.lines((lines) =>
          lines.map((line) =>
            line.trim() && !line.startsWith("- ") ? "- " + line : line,
          ),
        ),
      numbered: () => {
        let number = 0;
        this.lines((lines) =>
          lines.map((line) => (line.trim() ? `${++number}. ${line}` : line)),
        );
      },
      highlight: () =>
        this.lines((lines) =>
          lines.map((line) => (line.startsWith("| ") ? line : "| " + line)),
        ),
      undo: () => this.moveHistory(-1),
      redo: () => this.moveHistory(1),
    };
    actions[name]?.();
  }
  moveHistory(delta) {
    const next = this.position + delta;
    if (next < 0 || next >= this.history.length) return;
    this.position = next;
    this.lastTyped = 0;
    const snapshot = this.history[next];
    this.element.value = snapshot.value;
    this.element.focus();
    this.element.setSelectionRange(snapshot.start, snapshot.end);
    this.changed();
  }
}
