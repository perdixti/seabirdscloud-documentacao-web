import os
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import sys
from pathlib import Path
from PIL import ImageGrab, Image, ImageTk
from html import escape
import markdown
import re
import webbrowser
from bs4 import BeautifulSoup
import datetime

if hasattr(sys, '_MEIPASS'):
    BASE_PATH = Path(sys._MEIPASS)
else:
    BASE_PATH = Path(__file__).parent

TEMPLATE_PATH = BASE_PATH / "templates" / "templete.html"

EXTENSOES_TEXTO = {'.txt', '.html', '.htm', '.md', '.csv', '.json', '.xml'}

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("🐦 SeaBirdsCloud - Gerador de Documentação")
        self.root.geometry(f"1366x768")
        self.output_path = None
        self.atualizar_menu()

        self.root.resizable(True, True)

        self.img_path = None
        self.img_refs = []
        self.imagem_index = 0
        self.pasta_selecionada = None

        if not TEMPLATE_PATH.exists():
            messagebox.showerror("Erro", f"Template não encontrado: {TEMPLATE_PATH}")
            root.destroy()
            return

        self.setup_style()
        self.historico_base = BASE_PATH / "historico"
        self.historico_base.mkdir(parents=True, exist_ok=True)
        self.iniciar_auto_save()
        self.build_ui()

    def setup_style(self):
        # Customization for cleaner, modern design
        self.style = tb.Style("flatly")  # Choose a clean dark/light theme (e.g., flatly, morph, litera)
        self.style.configure("TButton", font=("Segoe UI", 10), padding=5)
        self.style.configure("TLabel", font=("Segoe UI", 11))
        self.style.configure("TEntry", font=("Segoe UI", 11))

    def build_ui(self):
        self.notebook = tb.Notebook(self.root, bootstyle="info")
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Aba Editor de Documentação
        self.frame_editor = tb.Frame(self.notebook)
        self.notebook.add(self.frame_editor, text="📄 Editor de Documentação")
        self.build_editor_ui()

        # Aba Substituidor de Texto
        self.frame_substituidor = tb.Frame(self.notebook)
        self.notebook.add(self.frame_substituidor, text="🔄 Substituidor de Texto")
        self.build_substituidor_ui()

        # Aba Formatador de HTML
        self.frame_formatador = tb.Frame(self.notebook)
        self.notebook.add(self.frame_formatador, text="🧹 Formatador de HTML")
        self.build_formatador_ui()

        # Aba Manual de Uso
        self.frame_manual = tb.Frame(self.notebook)
        self.notebook.add(self.frame_manual, text="📖 Manual")
        self.build_manual_ui()
    
    def atualizar_menu(self):
        """Atualiza o estado do menu com base no estado atual do projeto."""
        menu_bar = tk.Menu(self.root)

        # Menu "Configurações"
        menu_config = tk.Menu(menu_bar, tearoff=0)
        menu_config.add_command(label="Alternar Tema 🌓", command=self.alternar_tema)

        # Estado do botão "Abrir Histórico do Projeto Atual"
        estado_atual = "normal" if self.output_path else "disabled"
        menu_config.add_command(
            label="Abrir Histórico do Projeto Atual 📜",
            command=self.abrir_historico_projeto_atual,
            state=estado_atual
        )

        # Botão "Abrir Histórico de Projetos Antigos"
        menu_config.add_command(label="Abrir Histórico de Projetos Antigos 📂", command=self.abrir_historico_projetos_antigos)

        # Opção de configurações
        menu_config.add_command(label="Configurações de Histórico ⚙️", command=self.configuracoes_historico)

        menu_bar.add_cascade(label="⚙️ Configurações", menu=menu_config)
        self.root.config(menu=menu_bar)


    def build_editor_ui(self):
        container = tb.Labelframe(self.frame_editor, text="Informações do Documento", padding=10)
        container.pack(fill=X, padx=10, pady=10)

        self.title_entry = tb.Entry(container, width=40, foreground='grey')
        self.title_entry.insert(0, "Título da Página")
        self.title_entry.bind("<FocusIn>", lambda e: self.clear_placeholder(self.title_entry, "Título da Página"))
        self.title_entry.bind("<FocusOut>", lambda e: self.set_placeholder(self.title_entry, "Título da Página"))
        self.title_entry.grid(row=0, column=0, padx=5, pady=5)

        self.img_html_path_entry = tb.Entry(container, width=40, foreground='grey')
        self.img_html_path_entry.insert(0, "imagens")
        self.img_html_path_entry.bind("<FocusIn>", lambda e: self.clear_placeholder(self.img_html_path_entry, "imagens"))
        self.img_html_path_entry.bind("<FocusOut>", lambda e: self.set_placeholder(self.img_html_path_entry, "imagens"))
        self.img_html_path_entry.grid(row=0, column=1, padx=5, pady=5)

        options = tb.Labelframe(self.frame_editor, text="Opções de Geração", padding=10)
        options.pack(fill=X, padx=10, pady=10)

        self.processar_links = tk.BooleanVar(value=True)
        self.processar_tables = tk.BooleanVar(value=True)
        self.processar_tables_std = tk.BooleanVar(value=True)
        self.exibir_botao_copiar = tk.BooleanVar(value=True)
        self.processar_code_card = tk.BooleanVar(value=True)

        tb.Checkbutton(options, text="Ativar {{link: }}", variable=self.processar_links, bootstyle="success-round-toggle").pack(side=LEFT, padx=5)
        tb.Checkbutton(options, text="Ativar TableCard", variable=self.processar_tables, bootstyle="success-round-toggle").pack(side=LEFT, padx=5)
        tb.Checkbutton(options, text="Ativar Table", variable=self.processar_tables_std, bootstyle="success-round-toggle").pack(side=LEFT, padx=5)
        tb.Checkbutton(options, text="Mostrar botão copiar", variable=self.exibir_botao_copiar, bootstyle="success-round-toggle").pack(side=LEFT, padx=5)
        tb.Checkbutton(options, text="Ativar Code Card", variable=self.processar_code_card, bootstyle="success-round-toggle").pack(side=LEFT, padx=5)

        controls = tb.Frame(self.frame_editor)
        controls.pack(fill=X, padx=10, pady=10)

        tb.Button(self.root, text="🌓 Alternar Tema", command=self.alternar_tema, bootstyle="secondary").pack(side="top", anchor="ne", padx=10, pady=5)

        tb.Button(controls, text="📄 Selecionar Template", command=self.selecionar_template).pack(side=LEFT, padx=5)
        tb.Button(controls, text="📁 Pasta de Imagens", bootstyle="success", command=self.selecionar_imagens).pack(side=LEFT, padx=5)
        self.img_index_entry = tb.Entry(controls, width=6)
        self.img_index_entry.insert(0, str(self.imagem_index))
        self.img_index_entry.pack(side=LEFT, padx=5)

        tb.Button(controls, text="💾 Local de Saída", bootstyle="info", command=self.selecionar_saida).pack(side=LEFT, padx=5)
        tb.Button(controls, text="⚙️ Gerar HTML", bootstyle="danger", command=self.gerar_html).pack(side=LEFT, padx=5)
        tb.Button(controls, text="🔍 Visualizar", bootstyle="primary", command=self.abrir_visualizacao).pack(side=LEFT, padx=5) 

        self.label_template_path = tb.Label(self.frame_editor, text="📄 Template: Padrão (Projetos - SeaBirdsCloud)", bootstyle="secondary", anchor="w", justify="left", font=("Segoe UI", 10))
        self.label_template_path.pack(fill=tk.X, padx=10, pady=2)

        self.label_img_path = tb.Label(self.frame_editor, text="📁 Imagens: Nenhuma pasta selecionada", bootstyle="secondary", anchor="w", justify="left", font=("Segoe UI", 10))
        self.label_img_path.pack(fill=tk.X, padx=10, pady=2)

        self.label_saida_path = tb.Label(self.frame_editor, text="📄 Saída: Nenhum arquivo selecionado", bootstyle="secondary", anchor="w", justify="left", font=("Segoe UI", 10))
        self.label_saida_path.pack(fill=tk.X, padx=10, pady=2)

        editor_box = tb.Labelframe(self.frame_editor, text="Editor Markdown", padding=10)
        editor_box.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Dentro do editor_box, acima do text_editor
        toolbar = tb.Frame(editor_box)
        toolbar.pack(fill="x", pady=(0, 5))

        tb.Button(toolbar, text="📊 Inserir Tabela", bootstyle="info", command=lambda: self.abrir_janela_tabela("table")).pack(side="left", padx=5)
        tb.Button(toolbar, text="💳 Inserir Tabela Card", bootstyle="success", command=lambda: self.abrir_janela_tabela("tablecard")).pack(side="left", padx=5)

        self.text_editor = scrolledtext.ScrolledText(editor_box, wrap=tk.WORD, font=("Consolas", 12), undo=True)
        self.text_editor.pack(fill=BOTH, expand=True)
        self.text_editor.bind("<Control-v>", self.ctrl_v_handler)
        self.text_editor.bind("<<SelectAll>>", lambda e: "break")
        self.text_editor.bind("<Control-s>", self.gerar_html_evento)
        self.text_editor.bind("<Control-t>", lambda e: self.abrir_janela_tabela(modo="table"))
        self.text_editor.bind("<Control-r>", lambda e: self.abrir_janela_tabela(modo="tablecard"))
        self.text_editor.bind("<Control-z>", lambda e: self.text_editor.edit_undo())
        self.text_editor.bind("<Control-y>", lambda e: self.text_editor.edit_redo())
        self.text_editor.bind("<Control-f>", self.abrir_janela_pesquisa)
        self.text_editor.bind("<Control-b>", self.bold_selection)
        self.text_editor.bind("<Control-n>", self.distaque_selection)
        self.text_editor.bind("<Control-i>", self.italic_selection)
        self.text_editor.bind("<Control-p>", self.code_selection)
        self.text_editor.bind("<Control-h>", lambda e: self.add_heading(1))
        self.text_editor.bind("<Control-j>", lambda e: self.add_heading(2))
        self.text_editor.bind("<Control-k>", lambda e: self.add_heading(3))
        self.text_editor.bind("<Control-l>", lambda e: self.add_heading(4))
        self.text_editor.bind("<Control-d>", self.add_dash_prefix)
        self.text_editor.bind("<Control-e>", self.add_numbered_prefix)
        self.text_editor.bind("<Control-a>", lambda e: (self.text_editor.tag_add("sel", "1.0", "end"), "break"))

    def build_substituidor_ui(self):
        container = tb.Labelframe(self.frame_substituidor, text="Substituição de Texto", padding=10)
        container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.texto_antigo_entry = scrolledtext.ScrolledText(container, height=10, font=("Consolas", 11))
        self.texto_antigo_entry.insert(tk.END, "Texto antigo (multilinha)")
        self.texto_antigo_entry.bind("<FocusIn>", lambda e: self.clear_placeholder(self.texto_antigo_entry, "Texto antigo (multilinha)"))
        self.texto_antigo_entry.bind("<FocusOut>", lambda e: self.set_placeholder(self.texto_antigo_entry, "Texto antigo (multilinha)"))
        self.texto_antigo_entry.pack(fill=X, pady=5)

        self.texto_novo_entry = scrolledtext.ScrolledText(container, height=10, font=("Consolas", 11))
        self.texto_novo_entry.insert(tk.END, "Texto novo (multilinha)")
        self.texto_novo_entry.bind("<FocusIn>", lambda e: self.clear_placeholder(self.texto_novo_entry, "Texto novo (multilinha)"))
        self.texto_novo_entry.bind("<FocusOut>", lambda e: self.set_placeholder(self.texto_novo_entry, "Texto novo (multilinha)"))
        self.texto_novo_entry.pack(fill=X, pady=5)

        controls = tb.Frame(container)
        controls.pack(fill=X, pady=10)

        tb.Button(controls, text="📂 Selecionar Pasta", bootstyle="success", command=self.selecionar_pasta).pack(side=LEFT, padx=5)
        tb.Button(controls, text="🚀 Substituir", bootstyle="danger", command=self.substituir_texto).pack(side=LEFT, padx=5)

        self.log_text = scrolledtext.ScrolledText(container, height=10, font=("Consolas", 10), foreground="grey")
        self.log_text.pack(fill=BOTH, expand=True)
        self.log_text.bind("<<SelectAll>>", lambda e: "break")

        self.texto_antigo_entry.bind("<Control-a>", lambda e: (self.texto_antigo_entry.tag_add("sel", "1.0", "end"), "break"))
        self.texto_novo_entry.bind("<Control-a>", lambda e: (self.texto_novo_entry.tag_add("sel", "1.0", "end"), "break"))
        self.log_text.bind("<Control-a>", lambda e: (self.log_text.tag_add("sel", "1.0", "end"), "break"))

    def build_formatador_ui(self):
        container = tb.Labelframe(self.frame_formatador, text="Formatador com Identação (HTML)", padding=10)
        container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        tb.Button(container, text="📂 Selecionar Pasta", bootstyle="info", command=self.selecionar_pasta_formatacao).pack(pady=10)

        self.log_formatacao = scrolledtext.ScrolledText(container, height=10, font=("Consolas", 10), foreground="grey")
        self.log_formatacao.pack(fill=BOTH, expand=True)


    def build_manual_ui(self):
        container = tb.Labelframe(self.frame_manual, text="Manual de Utilização", padding=10)
        container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        manual_text = """
🐦 SeaBirdsCloud - Manual de Utilização

📄 Editor de Documentação:
- Edite seu texto no campo Markdown com suporte a:
    - Títulos, listas, tabelas, links, imagens e blocos de código.
    - Blocos especiais: 
        ```tablecard
        ```table
    - Variáveis personalizadas como {{link: url | texto}}.

🖱️ Funcionalidades do Editor:
- 📄 Selecionar Template → Escolha um arquivo HTML como base para o conteúdo.
- 📁 Pasta de Imagens → Define onde as imagens coladas serão salvas.
- 💾 Local de Saída → Define onde salvar o HTML final gerado.
- ⚙️ Gerar HTML → Processa o Markdown e gera o HTML.
- 🔍 Visualizar → Abre o HTML gerado no navegador.
- Campo “Título da Página” → Define o título exibido na aba HTML.
- Campo “imagens” → Define o caminho relativo das imagens no HTML.
- Controle de índice de imagem → Gerencia a numeração de arquivos colados.

🧩 Opções de Geração:
- [✔] Ativar {{link: }} → Converte links personalizados em botões.
- [✔] TableCard → Tabelas dentro de cards estilizados.
- [✔] Table → Tabelas HTML simples.
- [✔] Mostrar botão copiar → Adiciona botão de copiar nos blocos de código.
- [✔] Code Card → Blocos de código estilizados em cards.

🖼️ Colar Imagens:
- Ao usar Ctrl+V com uma imagem na área de transferência:
    - Salva automaticamente na pasta definida.
    - Insere o link Markdown correspondente no texto.
    - Exibe miniatura da imagem dentro do editor.

🎹 Atalhos de Teclado:
    Ctrl+B → Negrito  
    Ctrl+I → Itálico  
    Ctrl+P → Código inline (```...```)  
    Ctrl+H → Cabeçalho H1  
    Ctrl+J → Cabeçalho H2  
    Ctrl+K → Cabeçalho H3  
    Ctrl+L → Cabeçalho H4
    Ctrl+E → Lista ordenada (1., 2., ...)  
    Ctrl+D → Lista não ordenada (-)
    Ctrl+A → Selecionar tudo  
    Ctrl+S → Gerar HTML  
    Ctrl+V → Cola imagem do clipboard  
    Ctrl+Z / Ctrl+Y → Desfazer / Refazer
    Ctrl+F → Pesquisar por texto  

⚙️ Menu de Configurações:
- 🌓 Alternar Tema → Alterna entre tema claro e escuro
- ⚙️ Configurações de Histórico → Define frequência e limite de versões salvas.
- 📜 Abrir Histórico do Projeto Atual → Restaura versões anteriores (autosave).
- 📂 Abrir Histórico de Projetos Antigos → Acessa históricos salvos de outros projetos.

💾 Auto Salvamento de Histórico:
- Salva automaticamente a cada X segundos (configurável).
- Guarda múltiplas versões com limite configurável.
- Cada versão é marcada com data, hora e número incremental.

🔄 Substituidor de Texto:
- Campo “Texto Antigo” e “Texto Novo” (ambos multiline).
- 📂 Selecionar Pasta → Define onde buscar arquivos de texto.
- Sistema de filtragem e seleção de arquivos.
- Visualização dos arquivos que contêm o texto alvo.
- 🚀 Substituir → Aplica as substituições apenas nos arquivos marcados.

🧹 Formatador de HTML:
- 📂 Selecionar Pasta → Escolhe onde procurar arquivos HTML válidos.
- Permite filtrar e escolher arquivos individualmente.
    - Identação HTML (<div>, <table>, etc.).
    - Compactação de conteúdo textual (<p>, <h1>, <a>, etc.).
    - Preserva blocos de código (<pre><code>) sem alterações.
    - Limpeza de espaços desnecessários.

📁 Tipos de Arquivos Suportados:
- Arquivos de texto: `.txt`, `.html`, `.htm`, `.md`, `.csv`, `.json`, `.xml`
- Todos tratados como UTF-8.

🧠 Observações Finais:
- O botão “Copiar” em blocos de código depende de JavaScript no template.
- Imagens só são coladas se a pasta estiver definida.
- Logs e mensagens de erros aparecem nas áreas de log do app.
- As versões de histórico são separadas por projeto para organização.

Versão atual: v1.0 - Desenvolvido por SeaBirdsCloud
"""


        text_manual = scrolledtext.ScrolledText(container, wrap=tk.WORD, font=("Segoe UI", 11))
        text_manual.pack(fill=BOTH, expand=True)
        text_manual.insert(tk.END, manual_text)
        text_manual.config(state="disabled")  # Deixa o texto só para leitura

    # --------------------------- Funções do Editor ---------------------------
    def clear_placeholder(self, widget, placeholder):
        if isinstance(widget, tk.Entry):
            if widget.get() == placeholder:
                widget.delete(0, tk.END)
                # Use a cor padrão de texto do tema
                widget.configure(foreground=self.style.lookup("TEntry", "foreground"))
        elif isinstance(widget, scrolledtext.ScrolledText):
            if widget.get("1.0", tk.END).strip() == placeholder:
                widget.delete("1.0", tk.END)
                widget.configure(foreground=self.style.lookup("TEntry", "foreground"))

    def set_placeholder(self, widget, placeholder):
        if isinstance(widget, tk.Entry):
            if not widget.get():
                widget.insert(0, placeholder)
                widget.configure(foreground=self.style.lookup("TEntry", "foreground", default="grey"))
        elif isinstance(widget, scrolledtext.ScrolledText):
            if not widget.get("1.0", tk.END).strip():
                widget.insert(tk.END, placeholder)
                widget.configure(foreground=self.style.lookup("TEntry", "foreground", default="grey"))


    def alternar_tema(self):
        tema_atual = self.style.theme.name
        novo_tema = "darkly" if tema_atual != "darkly" else "flatly"
        self.style.theme_use(novo_tema)

    def selecionar_template(self):
        path = filedialog.askopenfilename(filetypes=[("HTML files", "*.html")])
        if path:
            self.template_path_escolhido = Path(path)
            self.label_template_path.config(text=f"📄 Template: {self.template_path_escolhido}")

    def selecionar_imagens(self):
        self.img_path = Path(filedialog.askdirectory())
        if self.img_path:
            self.label_img_path.config(text=f"📁 Imagens: {self.img_path}")

    def selecionar_saida(self):
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML files", "*.html")])
        if path:
            self.output_path = Path(path)
            self.label_saida_path.config(text=f"📄 Saída: {self.output_path}")
            self.atualizar_menu()

    def ctrl_v_handler(self, event=None):
        image = ImageGrab.grabclipboard()
        if image:
            return self.colar_imagem()
        return None

    def colar_imagem(self):
        if not self.img_path:
            messagebox.showwarning("Atenção", "Selecione a pasta de imagens primeiro.")
            return "break"

        try:
            image = ImageGrab.grabclipboard()
            if image:
                self.img_path.mkdir(parents=True, exist_ok=True)

                try:
                    index_manual = int(self.img_index_entry.get())
                    self.imagem_index = index_manual
                except ValueError:
                    pass  # Se inválido, usa o índice atual

                filename = f"img-{self.imagem_index}.png"
                path_img = self.img_path / filename
                image.save(path_img)

                markdown_img = f"![imagem]({self.img_path.name}/{filename})\n"
                self.text_editor.insert(tk.INSERT, markdown_img)

                resized = image.resize((300, int(300 * image.height / image.width)))
                img_tk = ImageTk.PhotoImage(resized)
                self.text_editor.image_create(tk.INSERT, image=img_tk)
                self.img_refs.append(img_tk)

                self.imagem_index += 1
                self.img_index_entry.delete(0, tk.END)
                self.img_index_entry.insert(0, str(self.imagem_index))
        except Exception as e:
            messagebox.showerror("Erro ao colar imagem", str(e))
        return "break"
    
    def abrir_janela_pesquisa(self, event=None):
        if hasattr(self, 'janela_pesquisa') and self.janela_pesquisa.winfo_exists():
            self.janela_pesquisa.lift()
            return

        self.janela_pesquisa = tb.Frame(self.root, bootstyle="secondary", relief="solid", borderwidth=1)
        self.janela_pesquisa.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)  # Canto superior direito

        entry_busca = tb.Entry(self.janela_pesquisa, width=32)
        entry_busca.grid(row=0, column=0, padx=(10, 5), pady=10, ipady=2)
        entry_busca.focus()

        self.label_resultado = tb.Label(self.janela_pesquisa, text="0/0", width=6, anchor="center", font=("Segoe UI", 9, "bold"))
        self.label_resultado.grid(row=0, column=1, padx=3)

        botao_prev = tb.Button(self.janela_pesquisa, text="↑", width=3, command=lambda: navegar(-1), bootstyle="outline")
        botao_prev.grid(row=0, column=2, padx=1)
        botao_next = tb.Button(self.janela_pesquisa, text="↓", width=3, command=lambda: navegar(1), bootstyle="outline")
        botao_next.grid(row=0, column=3, padx=1)

        botao_fechar = tb.Button(self.janela_pesquisa, text="✖", width=3, command=self.janela_pesquisa.destroy, bootstyle="danger-outline")
        botao_fechar.grid(row=0, column=4, padx=(5, 10))

        self.resultados_busca = []
        self.resultado_atual = -1

        def buscar(event=None):
            termo = entry_busca.get()
            self.text_editor.tag_remove("highlight", "1.0", tk.END)
            self.text_editor.tag_remove("highlight_active", "1.0", tk.END)
            self.resultados_busca.clear()
            self.resultado_atual = -1

            if termo:
                idx = "1.0"
                while True:
                    idx = self.text_editor.search(termo, idx, nocase=True, stopindex=tk.END)
                    if not idx:
                        break
                    fim_idx = f"{idx}+{len(termo)}c"
                    self.text_editor.tag_add("highlight", idx, fim_idx)
                    self.resultados_busca.append((idx, fim_idx))
                    idx = fim_idx

                if self.resultados_busca:
                    self.resultado_atual = 0
                    aplicar_selecao_ativa()

            self.label_resultado.config(text=f"{self.resultado_atual + 1 if self.resultados_busca else 0}/{len(self.resultados_busca)}")
            self.text_editor.tag_config("highlight", background="#fff59d", foreground="black")
            self.text_editor.tag_config("highlight_active", background="#448aff", foreground="white")

        def aplicar_selecao_ativa():
            self.text_editor.tag_remove("highlight_active", "1.0", tk.END)
            if 0 <= self.resultado_atual < len(self.resultados_busca):
                ini, fim = self.resultados_busca[self.resultado_atual]
                self.text_editor.tag_add("highlight_active", ini, fim)
                self.text_editor.see(ini)

        def navegar(direcao):
            if not self.resultados_busca:
                return
            self.resultado_atual = (self.resultado_atual + direcao) % len(self.resultados_busca)
            aplicar_selecao_ativa()
            self.label_resultado.config(text=f"{self.resultado_atual + 1}/{len(self.resultados_busca)}")

        entry_busca.bind("<Return>", buscar)
        entry_busca.bind("<KeyRelease>", buscar)

    def bold_selection(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            text = self.text_editor.get(start, end)
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, f"**{text}**")
        except:
            pass
        return "break"

    def distaque_selection(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            text = self.text_editor.get(start, end)
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, f"`{text}`")
        except:
            pass
        return "break"

    def italic_selection(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            text = self.text_editor.get(start, end)
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, f"*{text}*")
        except:
            pass
        return "break"

    def code_selection(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            text = self.text_editor.get(start, end)
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, f"```{text}```")
        except:
            pass
        return "break"

    def add_heading(self, level):
        try:
            start = self.text_editor.index("insert linestart")
            line = self.text_editor.get(start, f"{start} lineend")
            new_line = f"{'#' * level} {line.lstrip('# ').strip()}"
            self.text_editor.delete(start, f"{start} lineend")
            self.text_editor.insert(start, new_line)
        except:
            pass
        return "break"
    
    def add_numbered_prefix(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            lines = self.text_editor.get(start, end).splitlines()
            count = 1
            modified_lines = []
            for line in lines:
                if line.strip():
                    modified_lines.append(f"{count}. {line}")
                    count += 1
                else:
                    modified_lines.append(line)
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, "\n".join(modified_lines))
        except:
            pass
        return "break"
    
    def add_dash_prefix(self, event=None):
        try:
            start, end = self.text_editor.index("sel.first"), self.text_editor.index("sel.last")
            lines = self.text_editor.get(start, end).splitlines()
            modified_lines = ["- " + line if line.strip() and not line.startswith("- ") else line for line in lines]
            self.text_editor.delete(start, end)
            self.text_editor.insert(start, "\n".join(modified_lines))
        except:
            pass
        return "break"

    def gerar_html_evento(self, event=None):
        self.gerar_html()
        return "break"

    def gerar_html(self):
        if not self.output_path:
            messagebox.showerror("Erro", "Selecione um local para salvar o HTML.")
            return

        try:
            md_text = self.text_editor.get("1.0", tk.END)
            titulo = self.title_entry.get().strip() if self.title_entry.get() != "Título da Página" else "Documentação"
            caminho_imagens = self.img_html_path_entry.get().strip() if self.img_html_path_entry.get() != "imagens" else "."
            template_path = getattr(self, 'template_path_escolhido', TEMPLATE_PATH)

            gerar_html_final(
                md_text,
                self.img_path,
                template_path,
                self.output_path,
                titulo,
                caminho_imagens,
                self.processar_links.get(),
                self.processar_tables.get(),
                self.processar_tables_std.get(),
                self.processar_code_card.get(),
                self.exibir_botao_copiar.get()
            )
            messagebox.showinfo("Sucesso", f"HTML gerado com sucesso em {self.output_path}")
        except Exception as e:
            messagebox.showerror("Erro ao gerar HTML", str(e))


    def abrir_visualizacao(self):
        if self.output_path and self.output_path.exists():
            webbrowser.open(self.output_path.as_uri())
        else:
            messagebox.showwarning("Atenção", "Gere o HTML antes de visualizar.")

    def abrir_janela_tabela(self, modo="table"):
        import tkinter as tk
        from tkinter import messagebox
        import ttkbootstrap as tb

        # ---------------------------
        # JANELA BASE
        # ---------------------------
        titulo = "✨ Criar Tabela Markdown" if modo == "table" else "✨ Criar Tabela Card Markdown"
        janela = tb.Toplevel(self.root)
        janela.title(titulo)
        janela.geometry("900x600")
        janela.grab_set()
        janela.configure(padx=15, pady=15)

        fonte_padrao = ("Segoe UI", 10)

        header_frame = tb.Labelframe(janela, text="🧩 Configurações da Tabela", padding=15, bootstyle="info")
        header_frame.pack(fill="x", padx=5, pady=10)

        tb.Label(header_frame, text="Número de colunas:", font=fonte_padrao).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        colunas_var = tk.IntVar(value=3)
        tb.Entry(header_frame, textvariable=colunas_var, width=8).grid(row=0, column=1, padx=5, pady=5)

        tb.Label(header_frame, text="Número de linhas (sem cabeçalho):", font=fonte_padrao).grid(row=0, column=2, padx=5, pady=5, sticky="e")
        linhas_var = tk.IntVar(value=3)
        tb.Entry(header_frame, textvariable=linhas_var, width=8).grid(row=0, column=3, padx=5, pady=5)

        container = tb.Labelframe(janela, text="📋 Estrutura da Tabela", padding=5)
        container.pack(fill="both", expand=True, padx=5, pady=10)

        canvas = tk.Canvas(container)
        canvas.pack(side="left", fill="both", expand=True)

        scroll_y = tb.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_y.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll_y.set)

        frame_interno = tb.Frame(canvas)
        canvas.create_window((0, 0), window=frame_interno, anchor="nw")

        def atualizar_scroll(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        frame_interno.bind("<Configure>", atualizar_scroll)

        # ---------------------------
        # ESTADO
        # ---------------------------
        self.campos_cabecalhos = []  # list[Entry]
        self.campos_tabela = []       # list[{"frame": Frame, "widgets": list[Text]}]
        larguras_colunas = {}         # {col_idx: width}
        alturas_linhas = {}           # {row_frame: height}
        celula_selecionada = {"linha": None, "coluna": None}

        # ---------------------------
        # HELPERS DE SELEÇÃO E ESTILO
        # ---------------------------
        def pintar_selecao():
            l_sel, c_sel = celula_selecionada["linha"], celula_selecionada["coluna"]
            for l_idx, linha in enumerate(self.campos_tabela):
                for c_idx, cell in enumerate(linha["widgets"]):
                    bg = "#dbeafe" if (l_idx == l_sel and c_idx == c_sel) else "SystemWindow"
                    try:
                        cell.config(background=bg)
                    except tk.TclError:
                        pass

        def selecionar_celula(widget, linha_idx, col_idx):
            celula_selecionada["linha"] = linha_idx
            celula_selecionada["coluna"] = col_idx
            pintar_selecao()

        # ---------------------------
        # AJUSTES AUTOMÁTICOS
        # ---------------------------
        def ajustar_largura(entry, min_width=5, max_width=50):
            texto = entry.get()
            nova_largura = min(max(len(texto) + 1, min_width), max_width)
            entry.config(width=nova_largura)

        def ajustar_texto(text_widget, col_index):
            conteudo = text_widget.get("1.0", "end-1c")
            num_linhas_visuais = int(text_widget.count("1.0", "end", "displaylines")[0])
            altura_min, altura_max = 1, 10
            nova_altura = max(altura_min, min(num_linhas_visuais, altura_max))
            text_widget.config(height=nova_altura)

            linhas = conteudo.split("\n")
            maior_linha = max((len(l) for l in linhas), default=1)
            largura_min, largura_max = 8, 50
            nova_largura = max(largura_min, min(maior_linha + 2, largura_max))

            # Sincroniza alturas por linha (frame)
            altura_atual = alturas_linhas.get(text_widget.master, 1)
            if nova_altura > altura_atual:
                alturas_linhas[text_widget.master] = nova_altura
                for widget in text_widget.master.winfo_children():
                    if isinstance(widget, tk.Text):
                        widget.config(height=nova_altura)

            # Sincroniza larguras por coluna
            largura_atual = larguras_colunas.get(col_index, largura_min)
            if nova_largura > largura_atual:
                larguras_colunas[col_index] = nova_largura
                for linha in self.campos_tabela:
                    if col_index < len(linha["widgets"]):
                        linha["widgets"][col_index].config(width=nova_largura)
                if col_index < len(self.campos_cabecalhos):
                    self.campos_cabecalhos[col_index].config(width=nova_largura)

        # ---------------------------
        # SHIFT MAPS AO INSERIR/REMOVER COLUNAS
        # ---------------------------
        def shift_larguras_on_insert(col_idx):
            # Move chaves >= col_idx para +1
            new_map = {}
            for k, v in larguras_colunas.items():
                new_map[k + 1 if k >= col_idx else k] = v
            larguras_colunas.clear()
            larguras_colunas.update(new_map)

        def shift_larguras_on_remove(col_idx):
            # Elimina col_idx e move > col_idx para -1
            new_map = {}
            for k, v in larguras_colunas.items():
                if k == col_idx:
                    continue
                new_map[k - 1 if k > col_idx else k] = v
            larguras_colunas.clear()
            larguras_colunas.update(new_map)

        # ---------------------------
        # BINDINGS
        # ---------------------------
        def bind_celula(entry, l_idx, c_idx):
            # Clique esquerdo: seleciona
            entry.bind("<Button-1>", lambda e, l=l_idx, c=c_idx, w=entry: selecionar_celula(w, l, c))
            # Clique direito: menu de contexto (Windows/Linux)
            entry.bind("<Button-3>", lambda e, l=l_idx, c=c_idx, w=entry: mostrar_menu_contexto(e, l, c))
            # Ctrl+Clique esquerdo: menu de contexto (macOS fallback)
            entry.bind("<Control-Button-1>", lambda e, l=l_idx, c=c_idx, w=entry: mostrar_menu_contexto(e, l, c))
            entry.bind("<KeyRelease>", lambda e, ent=entry, c=c_idx: ajustar_texto(ent, c))

        def atualizar_bindings():
            for l_idx, linha in enumerate(self.campos_tabela):
                for c_idx, entry in enumerate(linha["widgets"]):
                    entry.unbind("<Button-1>")
                    entry.unbind("<Button-3>")
                    entry.unbind("<Control-Button-1>")
                    entry.unbind("<KeyRelease>")
                    bind_celula(entry, l_idx, c_idx)

        # ---------------------------
        # (RE)GRID DA LINHA AO MEXER COLUNAS
        # ---------------------------
        def regrid_linha(linha_dict):
            for j, w in enumerate(linha_dict["widgets"]):
                w.grid_forget()
                w.grid(row=0, column=j, padx=5, pady=5)
                # Aplicar largura conhecida da coluna (se existir)
                if j in larguras_colunas:
                    try:
                        w.config(width=larguras_colunas[j])
                    except tk.TclError:
                        pass

        def regrid_header():
            parent = self.campos_cabecalhos[0].master if self.campos_cabecalhos else None
            if not parent: 
                return
            for j, ent in enumerate(self.campos_cabecalhos):
                ent.grid_forget()
                ent.grid(row=0, column=j, padx=5, pady=5)
                if j in larguras_colunas:
                    ent.config(width=larguras_colunas[j])

        # ---------------------------
        # CRIAÇÃO INICIAL
        # ---------------------------
        def gerar_campos():
            for widget in frame_interno.winfo_children():
                widget.destroy()
            self.campos_cabecalhos.clear()
            self.campos_tabela.clear()
            larguras_colunas.clear()
            alturas_linhas.clear()
            celula_selecionada["linha"] = None
            celula_selecionada["coluna"] = None

            cols = max(1, int(colunas_var.get()))
            rows = max(0, int(linhas_var.get()))

            tb.Label(frame_interno, text="🏷️ Cabeçalhos das Colunas", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 10))
            linha_header = tb.Frame(frame_interno)
            linha_header.pack(anchor="w", pady=5)

            for j in range(cols):
                entry = tb.Entry(linha_header, width=10, bootstyle="info")
                entry.grid(row=0, column=j, padx=5, pady=5)
                entry.insert(0, f"Coluna {j + 1}")
                entry.bind("<KeyRelease>", lambda e, ent=entry: ajustar_largura(ent))
                self.campos_cabecalhos.append(entry)

            tb.Label(frame_interno, text="📄 Linhas da Tabela", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(15, 10))

            for i in range(rows):
                linha_frame = tb.Frame(frame_interno)
                linha_frame.pack(anchor="w", pady=3)
                linha_widgets = []
                for j in range(cols):
                    entry = tk.Text(linha_frame, width=10, height=1, wrap="word")
                    entry.grid(row=0, column=j, padx=5, pady=5)
                    linha_widgets.append(entry)
                self.campos_tabela.append({"frame": linha_frame, "widgets": linha_widgets})

            atualizar_bindings()
            atualizar_scroll()

        # ---------------------------
        # AÇÕES DE LINHA
        # ---------------------------
        def adicionar_linha_abaixo():
            linha_idx = celula_selecionada["linha"]
            if linha_idx is None:
                linha_idx = len(self.campos_tabela) - 1

            cols = len(self.campos_cabecalhos)
            nova_frame = tb.Frame(frame_interno)
            nova_widgets = []
            for j in range(cols):
                entry = tk.Text(nova_frame, width=larguras_colunas.get(j, 10), height=1, wrap="word")
                entry.grid(row=0, column=j, padx=5, pady=5)
                nova_widgets.append(entry)
            if 0 <= linha_idx < len(self.campos_tabela):
                nova_frame.pack(after=self.campos_tabela[linha_idx]["frame"], anchor="w", pady=3)
                self.campos_tabela.insert(linha_idx + 1, {"frame": nova_frame, "widgets": nova_widgets})
                celula_selecionada["linha"] = linha_idx + 1
            else:
                nova_frame.pack(anchor="w", pady=3)
                self.campos_tabela.append({"frame": nova_frame, "widgets": nova_widgets})
                celula_selecionada["linha"] = len(self.campos_tabela) - 1
            atualizar_bindings()
            pintar_selecao()
            atualizar_scroll()

        def adicionar_linha_acima():
            linha_idx = celula_selecionada["linha"]
            if linha_idx is None or not (0 <= linha_idx < len(self.campos_tabela)):
                # Sem seleção: adiciona no topo
                linha_idx = -1

            cols = len(self.campos_cabecalhos)
            nova_frame = tb.Frame(frame_interno)
            nova_widgets = []
            for j in range(cols):
                entry = tk.Text(nova_frame, width=larguras_colunas.get(j, 10), height=1, wrap="word")
                entry.grid(row=0, column=j, padx=5, pady=5)
                nova_widgets.append(entry)
            if linha_idx == -1:
                nova_frame.pack(anchor="w", pady=3)
                self.campos_tabela.insert(0, {"frame": nova_frame, "widgets": nova_widgets})
                celula_selecionada["linha"] = 0
            else:
                ref_frame = self.campos_tabela[linha_idx]["frame"]
                nova_frame.pack(before=ref_frame, anchor="w", pady=3)
                self.campos_tabela.insert(linha_idx, {"frame": nova_frame, "widgets": nova_widgets})
                celula_selecionada["linha"] = linha_idx
            atualizar_bindings()
            pintar_selecao()
            atualizar_scroll()

        def remover_linha():
            linha_idx = celula_selecionada["linha"]
            if linha_idx is None or not (0 <= linha_idx < len(self.campos_tabela)):
                messagebox.showinfo("Remover Linha", "Selecione uma linha para remover.")
                return
            info = self.campos_tabela.pop(linha_idx)
            info["frame"].destroy()
            # Ajusta seleção
            if self.campos_tabela:
                novo_idx = min(linha_idx, len(self.campos_tabela) - 1)
                celula_selecionada["linha"] = novo_idx
            else:
                celula_selecionada["linha"] = None
            pintar_selecao()
            atualizar_bindings()
            atualizar_scroll()

        # ---------------------------
        # AÇÕES DE COLUNA
        # ---------------------------
        def inserir_coluna(idx):
            # Insere à esquerda de idx (se quiser à direita, passe idx+1)
            if not self.campos_cabecalhos:
                return
            shift_larguras_on_insert(idx)

            # Cabeçalho
            parent = self.campos_cabecalhos[0].master
            novo_header = tb.Entry(parent, width=larguras_colunas.get(idx, 10), bootstyle="info")
            novo_header.insert(0, f"Coluna {idx + 1}")
            self.campos_cabecalhos.insert(idx, novo_header)
            regrid_header()

            # Linhas
            for linha in self.campos_tabela:
                parent = linha["frame"]
                novo = tk.Text(parent, width=larguras_colunas.get(idx, 10), height=1, wrap="word")
                linha["widgets"].insert(idx, novo)
                regrid_linha(linha)

            # Ajusta seleção para refletir coluna movida
            c_sel = celula_selecionada["coluna"]
            if c_sel is not None and c_sel >= idx:
                celula_selecionada["coluna"] = c_sel + 1

            atualizar_bindings()
            pintar_selecao()
            atualizar_scroll()

        def remover_coluna_idx(idx):
            if not self.campos_cabecalhos or not (0 <= idx < len(self.campos_cabecalhos)):
                messagebox.showinfo("Remover Coluna", "Selecione uma coluna válida para remover.")
                return

            # Cabeçalho
            h = self.campos_cabecalhos.pop(idx)
            h.destroy()

            # Linhas
            for linha in self.campos_tabela:
                w = linha["widgets"].pop(idx)
                w.destroy()
                regrid_linha(linha)

            shift_larguras_on_remove(idx)

            # Seleção
            c_sel = celula_selecionada["coluna"]
            if c_sel is not None:
                if c_sel == idx:
                    celula_selecionada["coluna"] = None
                elif c_sel > idx:
                    celula_selecionada["coluna"] = c_sel - 1

            regrid_header()
            atualizar_bindings()
            pintar_selecao()
            atualizar_scroll()

        def adicionar_coluna_esquerda():
            col_idx = celula_selecionada["coluna"]
            if col_idx is None:
                col_idx = 0
            inserir_coluna(col_idx)

        def adicionar_coluna_direita():
            col_idx = celula_selecionada["coluna"]
            if col_idx is None:
                col_idx = len(self.campos_cabecalhos) - 1
            inserir_coluna(col_idx + 1)

        def remover_coluna():
            col_idx = celula_selecionada["coluna"]
            if col_idx is None:
                messagebox.showinfo("Remover Coluna", "Selecione uma coluna para remover.")
                return
            remover_coluna_idx(col_idx)

        # ---------------------------
        # MENU DE CONTEXTO (BOTÃO DIREITO)
        # ---------------------------
        menu_popup = tk.Menu(janela, tearoff=0)
        # Linhas
        menu_popup.add_command(label="➕ Adicionar linha acima", command=lambda: (adicionar_linha_acima()))
        menu_popup.add_command(label="➕ Adicionar linha abaixo", command=lambda: (adicionar_linha_abaixo()))
        menu_popup.add_command(label="➖ Remover linha", command=lambda: (remover_linha()))
        menu_popup.add_separator()
        # Colunas
        menu_popup.add_command(label="⬅️ Adicionar coluna à esquerda", command=lambda: (adicionar_coluna_esquerda()))
        menu_popup.add_command(label="➡️ Adicionar coluna à direita", command=lambda: (adicionar_coluna_direita()))
        menu_popup.add_command(label="🗑️ Remover coluna", command=lambda: (remover_coluna()))

        def mostrar_menu_contexto(event, l_idx, c_idx):
            selecionar_celula(event.widget, l_idx, c_idx)
            try:
                menu_popup.tk_popup(event.x_root, event.y_root)
            finally:
                menu_popup.grab_release()

        # ---------------------------
        # BOTÕES / SCROLL / INSERÇÃO NO EDITOR
        # ---------------------------
        tb.Button(header_frame, text="Criar Estrutura", bootstyle="primary", command=gerar_campos).grid(row=0, column=4, padx=15, pady=5)

        scroll_x = tb.Scrollbar(janela, orient="horizontal", command=canvas.xview)
        scroll_x.pack(fill="x", padx=5, pady=(0, 2))
        canvas.configure(xscrollcommand=scroll_x.set)

        tb.Separator(janela, orient="horizontal").pack(fill="x", padx=10, pady=(8, 5))

        botoes_frame = tb.Frame(janela)
        botoes_frame.pack(pady=(5, 15))

        def inserir_tabela():
            if not self.campos_cabecalhos:
                messagebox.showwarning("Atenção", "Gere os campos primeiro.")
                return

            headers = [entry.get() for entry in self.campos_cabecalhos]
            header_line = "| " + " | ".join(headers) + " |"
            separator_line = "|" + "|".join(["---" for _ in headers]) + "|"

            linhas = []
            for linha in self.campos_tabela:
                valores = [entry.get("1.0", "end-1c").strip() for entry in linha["widgets"]]
                linhas.append("| " + " | ".join(valores) + " |")

            markdown_table = f"```{modo}\n{header_line}\n{separator_line}\n" + "\n".join(linhas) + "\n```"
            self.text_editor.insert(tk.INSERT, markdown_table + "\n")
            janela.destroy()

        tb.Button(botoes_frame, text="✅ Inserir no Editor", bootstyle="success", command=inserir_tabela).pack(side="left", padx=10)
        tb.Button(botoes_frame, text="❌ Fechar", bootstyle="danger-outline", command=janela.destroy).pack(side="left", padx=10)


    def iniciar_auto_save(self):
        """Inicia ou reinicia o salvamento automático de históricos."""
        # Verifica se auto_save_id existe e é válido antes de cancelar
        if hasattr(self, "auto_save_id") and self.auto_save_id is not None:
            try:
                self.root.after_cancel(self.auto_save_id)
            except Exception:
                pass  # Evita erros se o ID não for válido

        # Obtém a frequência e quantidade máxima (com valores padrão caso não tenham sido definidos)
        frequencia = int(getattr(self, "historico_frequencia", 60)) * 1000  # Convertido para milissegundos
        quantidade_max = int(getattr(self, "historico_quantidade_max", 10))

        # Salva o histórico
        self.salvar_historico_markdown(quantidade_max)

        # Reagenda a próxima execução
        self.auto_save_id = self.root.after(frequencia, self.iniciar_auto_save)
    
    def salvar_historico_markdown(self, quantidade_max):
        """Salva o histórico do projeto atual e remove excedentes."""
        try:
            if not self.output_path:
                return

            texto = self.text_editor.get("1.0", tk.END).strip()
            if not texto:
                return

            nome_projeto = self.output_path.stem
            pasta_projeto = self.historico_base / nome_projeto
            pasta_projeto.mkdir(parents=True, exist_ok=True)

            # Salva o histórico com timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Obter número sequencial considerando apenas o padrão de nome base
            arquivos_existentes = sorted(pasta_projeto.glob("autosave_*.md"))

            # Identificar o maior número já existente
            ultimo_numero = max(
                (int(re.search(r'_v(\d{3})\.md$', arq.name).group(1))
                for arq in arquivos_existentes
                if re.search(r'_v(\d{3})\.md$', arq.name)),
                default=0
            )
            numero = ultimo_numero + 1

            nome_arquivo = f"autosave_v{numero:03d}_{timestamp}.md"
            caminho_arquivo = pasta_projeto / nome_arquivo

            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write(texto)

            # Remove históricos excedentes
            arquivos = sorted(pasta_projeto.glob("autosave_*.md"), reverse=True)
            for arquivo in arquivos[quantidade_max:]:
                arquivo.unlink()

        except Exception as e:
            print(f"[Histórico] Erro ao salvar: {e}")


    def abrir_historico_projeto_atual(self):
        """Exibe as versões do histórico do projeto atual e permite selecionar uma para carregar."""
        if not self.output_path:
            return

        projeto_atual = self.output_path.stem
        pasta_projeto_atual = self.historico_base / projeto_atual

        if not pasta_projeto_atual.exists():
            messagebox.showinfo("Histórico", "Nenhum histórico encontrado para o projeto atual.")
            return

        # Obter todos os arquivos de histórico
        arquivos_historico = sorted(pasta_projeto_atual.glob("autosave_*.md"), reverse=True)

        if not arquivos_historico:
            messagebox.showinfo("Histórico", "Nenhum histórico encontrado para o projeto atual.")
            return

        # Janela de seleção de versões
        janela_historico = tk.Toplevel(self.root)
        janela_historico.title(f"Histórico - {projeto_atual}")
        janela_historico.geometry("400x300")
        janela_historico.grab_set()

        tb.Label(janela_historico, text="Selecione a versão do histórico:", font=("Segoe UI", 11)).pack(pady=10)

        versao_var = tk.StringVar()
        versao_dropdown = tb.Combobox(janela_historico, textvariable=versao_var, values=[a.stem for a in arquivos_historico])
        versao_dropdown.pack(pady=5)
        versao_dropdown.current(0)

        def carregar_historico():
            versao_selecionada = versao_var.get()

            if not versao_selecionada:
                messagebox.showwarning("Atenção", "Selecione uma versão para carregar.")
                return

            caminho_arquivo = pasta_projeto_atual / f"{versao_selecionada}.md"

            if not caminho_arquivo.exists():
                messagebox.showerror("Erro", "Arquivo de histórico não encontrado.")
                return

            # Confirmação antes de sobrescrever
            resposta = messagebox.askyesno(
                "Confirmação",
                "O conteúdo atual será sobrescrito pelo histórico selecionado. Deseja continuar?"
            )

            if not resposta:
                return

            # Carregar o conteúdo da versão selecionada
            try:
                with open(caminho_arquivo, "r", encoding="utf-8") as f:
                    conteudo = f.read()

                self.text_editor.delete("1.0", tk.END)
                self.text_editor.insert("1.0", conteudo)
                messagebox.showinfo("Sucesso", "Histórico carregado com sucesso!")
                janela_historico.destroy()

            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar o histórico: {e}")

        # Botão para carregar a versão selecionada
        btn_carregar = tb.Button(janela_historico, text="Carregar Histórico", bootstyle="success", command=carregar_historico)
        btn_carregar.pack(pady=10)


    def abrir_historico_projetos_antigos(self):
        """Exibe a lista de projetos antigos e carrega o histórico no editor de Markdown."""
        projetos_antigos = [p for p in self.historico_base.glob("*") if p.is_dir()]

        if not projetos_antigos:
            messagebox.showinfo("Histórico", "Nenhum projeto antigo encontrado.")
            return

        # Janela de seleção de projetos antigos
        janela_projetos = tk.Toplevel(self.root)
        janela_projetos.title("Selecionar Projeto Antigo")
        janela_projetos.geometry("400x300")
        janela_projetos.grab_set()

        tb.Label(janela_projetos, text="Selecione um projeto:", font=("Segoe UI", 11)).pack(pady=10)

        projeto_var = tk.StringVar()
        projeto_dropdown = tb.Combobox(janela_projetos, textvariable=projeto_var, values=[p.stem for p in projetos_antigos])
        projeto_dropdown.pack(pady=5)
        projeto_dropdown.bind("<<ComboboxSelected>>", lambda e: listar_versoes(projeto_var.get()))

        versao_var = tk.StringVar()
        versao_dropdown = tb.Combobox(janela_projetos, textvariable=versao_var)
        versao_dropdown.pack(pady=5)

        def listar_versoes(projeto_nome):
            pasta_projeto = self.historico_base / projeto_nome

            if pasta_projeto.exists():
                versoes = sorted(pasta_projeto.glob("autosave_*.md"), reverse=True)
                versao_dropdown["values"] = [v.stem for v in versoes]
                versao_dropdown.current(0)

        def carregar_selecionado():
            projeto_nome = projeto_var.get()
            versao_nome = versao_var.get()

            if not projeto_nome or not versao_nome:
                messagebox.showwarning("Atenção", "Selecione um projeto e uma versão para carregar.")
                return

            caminho_arquivo = self.historico_base / projeto_nome / f"{versao_nome}.md"

            if not caminho_arquivo.exists():
                messagebox.showerror("Erro", "Arquivo não encontrado.")
                return

            # Pergunta de confirmação
            resposta = messagebox.askyesno(
                "Confirmação",
                "O conteúdo atual será sobrescrito pelo histórico selecionado. Deseja continuar?"
            )

            if not resposta:
                return

            try:
                with open(caminho_arquivo, "r", encoding="utf-8") as f:
                    conteudo = f.read()
                self.text_editor.delete("1.0", tk.END)
                self.text_editor.insert("1.0", conteudo)
                messagebox.showinfo("Sucesso", "Histórico carregado com sucesso!")
                janela_projetos.destroy()
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar o histórico: {e}")

        # Botão de Carregar
        btn_carregar = tb.Button(janela_projetos, text="Carregar Histórico", bootstyle="success", command=carregar_selecionado)
        btn_carregar.pack(pady=10)

    def configuracoes_historico(self):
        """Janela para configurar a frequência e quantidade de históricos salvos."""
        # Verifica se a janela já está aberta
        if hasattr(self, "janela_config") and self.janela_config.winfo_exists():
            self.janela_config.lift()
            return

        # Define a janela antes de utilizá-la
        self.janela_config = tk.Toplevel(self.root)
        self.janela_config.title("Configurações de Histórico")
        self.janela_config.geometry("400x250")
        self.janela_config.grab_set()

        # Frame para frequência
        frame_freq = tb.Labelframe(self.janela_config, text="Frequência de Geração do Histórico (segundos)", padding=10)
        frame_freq.pack(fill="x", padx=10, pady=10)

        self.freq_var = tk.StringVar(value=str(getattr(self, "historico_frequencia", 60)))
        freq_entry = tb.Entry(frame_freq, textvariable=self.freq_var, width=10)
        freq_entry.pack()

        # Frame para quantidade máxima
        frame_qtd = tb.Labelframe(self.janela_config, text="Quantidade Máxima de Históricos", padding=10)
        frame_qtd.pack(fill="x", padx=10, pady=10)

        self.qtd_var = tk.StringVar(value=str(getattr(self, "historico_quantidade_max", 10)))
        qtd_entry = tb.Entry(frame_qtd, textvariable=self.qtd_var, width=10)
        qtd_entry.pack()

        # Botão de salvar configurações
        tb.Button(self.janela_config, text="Salvar Configurações", bootstyle="success", command=self.salvar_config_historico).pack(pady=15)


    def salvar_config_historico(self):
        """Salva as configurações de frequência e quantidade máxima de históricos."""
        try:
            self.historico_frequencia = int(self.freq_var.get())
            self.historico_quantidade_max = int(self.qtd_var.get())
            messagebox.showinfo("Configurações", "Configurações salvas com sucesso!")
            self.iniciar_auto_save()  # Reinicia a função com a nova frequência

            # Verifica se a janela existe antes de tentar destruí-la
            if hasattr(self, "janela_config"):
                self.janela_config.destroy()

        except ValueError:
            messagebox.showerror("Erro", "Valores inválidos. Insira apenas números inteiros.")


    # --------------------------- Funções do Substituidor ---------------------------
    def selecionar_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.pasta_selecionada = pasta
            self.log(f"📁 Pasta selecionada: {pasta}")

    def substituir_texto(self):
        if not self.pasta_selecionada:
            messagebox.showwarning("Atenção", "Selecione uma pasta primeiro.")
            return

        texto_antigo = self.texto_antigo_entry.get("1.0", tk.END).strip()
        texto_novo = self.texto_novo_entry.get("1.0", tk.END).strip()

        if not texto_antigo:
            messagebox.showerror("Erro", "Digite o texto antigo para substituir.")
            return

        arquivos_encontrados = []

        for root, dirs, files in os.walk(self.pasta_selecionada):
            for file in files:
                _, extensao = os.path.splitext(file)
                if extensao.lower() in EXTENSOES_TEXTO:
                    caminho_arquivo = os.path.join(root, file)
                    try:
                        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                            conteudo = f.read()
                        if texto_antigo in conteudo:
                            arquivos_encontrados.append(caminho_arquivo)
                    except Exception as e:
                        self.log(f"⚠️ Erro ao ler {caminho_arquivo}: {e}")

        if arquivos_encontrados:
            self.mostrar_arquivos_para_confirmacao(arquivos_encontrados, texto_antigo, texto_novo)
        else:
            messagebox.showinfo("Nenhum arquivo encontrado", "Não foram encontrados arquivos contendo o texto informado.")

    def log(self, mensagem):
        self.log_text.insert(tk.END, mensagem + "\n")
        self.log_text.see(tk.END)

    def mostrar_arquivos_para_confirmacao(self, arquivos_encontrados, texto_antigo, texto_novo):
        janela = tk.Toplevel(self.root)
        janela.title("Selecionar Arquivos para Substituição")
        janela.geometry("600x400")
        janela.grab_set()

        tb.Label(janela, text="Selecione os arquivos NÃO que deseja substituir:", font=("Segoe UI", 12, "bold")).pack(pady=10)

        self.filtro_var = tk.StringVar()
        entry_filtro = tb.Entry(janela, textvariable=self.filtro_var)
        entry_filtro.pack(fill=X, padx=10, pady=5)

        frame_lista = tb.Frame(janela)
        frame_lista.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(frame_lista)
        scrollbar = tb.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        scroll_frame = tb.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.checkbox_vars = {}

        for arquivo in arquivos_encontrados:
            var = tk.BooleanVar(value=True)
            chk = tb.Checkbutton(scroll_frame, text=arquivo, variable=var, bootstyle="round-toggle")
            chk.pack(anchor="w")
            self.checkbox_vars[arquivo] = var

        def atualizar_lista(*args):
            filtro = self.filtro_var.get().lower()
            for widget in scroll_frame.winfo_children():
                widget.destroy()

            for arquivo in arquivos_encontrados:
                if filtro in arquivo.lower():
                    var = self.checkbox_vars.get(arquivo, tk.BooleanVar(value=True))
                    chk = tb.Checkbutton(scroll_frame, text=arquivo, variable=var, bootstyle="round-toggle")
                    chk.pack(anchor="w")
                    self.checkbox_vars[arquivo] = var

        self.filtro_var.trace_add("write", atualizar_lista)

        botoes_frame = tb.Frame(janela)
        botoes_frame.pack(pady=10)

        tb.Button(botoes_frame, text="✅ Confirmar", bootstyle="success", command=lambda: self.confirmar_substituicao(janela, texto_antigo, texto_novo)).pack(side="left", padx=10)
        tb.Button(botoes_frame, text="❌ Cancelar", bootstyle="danger", command=janela.destroy).pack(side="left", padx=10)

    def confirmar_substituicao(self, janela, texto_antigo, texto_novo):
        arquivos_selecionados = [arquivo for arquivo, var in self.checkbox_vars.items() if var.get()]

        if not arquivos_selecionados:
            messagebox.showwarning("Atenção", "Nenhum arquivo selecionado para substituição.")
            return

        for caminho_arquivo in arquivos_selecionados:
            try:
                with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                    conteudo = f.read()

                conteudo = conteudo.replace(texto_antigo, texto_novo)

                with open(caminho_arquivo, 'w', encoding='utf-8') as f:
                    f.write(conteudo)

                self.log(f"✅ Alterado: {caminho_arquivo}")
            except Exception as e:
                self.log(f"⚠️ Erro em {caminho_arquivo}: {e}")

        self.log("\n🏁 Substituição concluída.")
        janela.destroy()

    def selecionar_pasta_formatacao(self):
        pasta = filedialog.askdirectory()
        if pasta:
            arquivos = []
            for root, dirs, files in os.walk(pasta):
                for file in files:
                    _, ext = os.path.splitext(file)
                    if ext.lower() in EXTENSOES_TEXTO:
                        arquivos.append(os.path.join(root, file))

            if arquivos:
                self.mostrar_arquivos_para_formatacao(arquivos)
            else:
                messagebox.showinfo("Nenhum arquivo encontrado", "Não foram encontrados arquivos válidos na pasta.")
    
    def mostrar_arquivos_para_formatacao(self, arquivos_encontrados):
        janela = tk.Toplevel(self.root)
        janela.title("Selecionar Arquivos para Formatar")
        janela.geometry("600x400")
        janela.grab_set()

        tb.Label(janela, text="Selecione os arquivos que deseja formatar:", font=("Segoe UI", 12, "bold")).pack(pady=10)

        self.filtro_format_var = tk.StringVar()
        entry_filtro = tb.Entry(janela, textvariable=self.filtro_format_var)
        entry_filtro.pack(fill=X, padx=10, pady=5)

        frame_lista = tb.Frame(janela)
        frame_lista.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(frame_lista)
        scrollbar = tb.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        scroll_frame = tb.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.checkbox_format_vars = {}

        def popular_checkboxes():
            for widget in scroll_frame.winfo_children():
                widget.destroy()
            filtro = self.filtro_format_var.get().lower()
            for arquivo in arquivos_encontrados:
                if filtro in arquivo.lower():
                    var = self.checkbox_format_vars.get(arquivo, tk.BooleanVar(value=True))
                    chk = tb.Checkbutton(scroll_frame, text=arquivo, variable=var, bootstyle="round-toggle")
                    chk.pack(anchor="w")
                    self.checkbox_format_vars[arquivo] = var

        self.filtro_format_var.trace_add("write", lambda *args: popular_checkboxes())
        popular_checkboxes()

        botoes_frame = tb.Frame(janela)
        botoes_frame.pack(pady=10)

        tb.Button(botoes_frame, text="✅ Confirmar", bootstyle="success",
                command=lambda: self.aplicar_formatacao_arquivos(janela)).pack(side="left", padx=10)
        tb.Button(botoes_frame, text="❌ Cancelar", bootstyle="danger", command=janela.destroy).pack(side="left", padx=10)


    def aplicar_formatacao_arquivos(self, janela):
        selecionados = [arq for arq, var in self.checkbox_format_vars.items() if var.get()]
        if not selecionados:
            messagebox.showwarning("Atenção", "Nenhum arquivo selecionado.")
            return

        for path in selecionados:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    conteudo = f.read()

                # 1. Preservar blocos <pre><code>...</code></pre>
                pre_blocks = []
                def preservar_pre(m):
                    pre_blocks.append(m.group(0))
                    return f"__PRE_BLOCK_{len(pre_blocks)-1}__"

                conteudo_preservado = re.sub(r'<pre><code>.*?</code></pre>', preservar_pre, conteudo, flags=re.DOTALL)

                # 2. Prettify o conteúdo SEM os <pre><code>
                soup = BeautifulSoup(conteudo_preservado, 'html.parser')
                formatado = soup.prettify()

                # 3. Corrigir indentação (somente fora dos blocos preservados)
                formatado = re.sub(
                    r'^( +)',
                    lambda m: '    ' * (len(m.group(1)) // 2),
                    formatado,
                    flags=re.MULTILINE
                )

                # 4. Restaurar os blocos <pre><code>
                def restaurar_pre(m):
                    index = int(m.group(1))
                    return pre_blocks[index]

                formatado = re.sub(r'__PRE_BLOCK_(\d+)__', restaurar_pre, formatado)


                # Compacta blocos textuais simples
                tags_blocos_simples = ['p', 'h1', 'h2', 'h3', 'h4', 'a', 'title']
                for tag in tags_blocos_simples:
                    formatado = re.sub(
                        rf'<{tag}>\s*(.*?)\s*</{tag}>',
                        lambda m: "<{}>{}</{}>".format(tag, re.sub(r'\s+', ' ', m.group(1)).strip(), tag),
                        formatado,
                        flags=re.DOTALL
                    )

                # Recompacta tags inline comuns
                for tag in ['strong', 'em', 'b', 'i', 'a', 'span']:
                    formatado = re.sub(
                        rf'<{tag}>\s*(.*?)\s*</{tag}>',
                        lambda m: f"<{tag}>{m.group(1).strip()}</{tag}>",
                        formatado,
                        flags=re.DOTALL
                    )

                # Remove espaço entre </inline> e pontuação
                formatado = re.sub(
                    r'(</(?:strong|em|a|span|b|i)>)\s+([,.;!?:])',
                    r'\1\2',
                    formatado
                )

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(formatado)

                self.log_formatacao.insert(tk.END, f"✅ Formatado: {path}\n")
            except Exception as e:
                self.log_formatacao.insert(tk.END, f"⚠️ Erro em {path}: {e}\n")

        self.log_formatacao.see(tk.END)
        janela.destroy()

def markdown_inline(texto):
    return markdown.markdown(texto, extensions=[]).replace('<p>', '').replace('</p>', '')

def converter_listas_markdown(md_text):
    linhas = md_text.splitlines()
    resultado = []

    stack = []  # pilha: (tipo_lista, indentacao)

    for linha in linhas:
        match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)", linha)

        if match:
            indentacao = len(match.group(1))
            marcador = match.group(2)
            conteudo = match.group(3)

            tipo = "ol" if marcador.endswith(".") else "ul"

            # Fecha listas se o nível diminuiu
            while stack and indentacao < stack[-1][1]:
                tipo_fechado, _ = stack.pop()
                resultado.append(f"</{tipo_fechado}>")

            # Abre nova lista se necessário
            if not stack or indentacao > stack[-1][1] or tipo != stack[-1][0]:
                resultado.append(f"<{tipo}>")
                stack.append((tipo, indentacao))

            # Processa markdown dentro do item
            conteudo_html = markdown_inline(conteudo)

            resultado.append(f"<li>{conteudo_html}</li>")
        else:
            # Fecha listas abertas antes de texto normal
            while stack:
                tipo_fechado, _ = stack.pop()
                resultado.append(f"</{tipo_fechado}>")

            resultado.append(linha)

    # Fecha o que sobrou
    while stack:
        tipo_fechado, _ = stack.pop()
        resultado.append(f"</{tipo_fechado}>")

    return "\n".join(resultado)

def processar_variaveis_customizadas(
    md_text,
    processar_links=True,
    processar_tables=True,
    processar_tables_std=True,
    processar_code_card=True,
    exibir_botao_copiar=True
):
    # Captura todos os blocos de código (```...```)
    code_blocks = re.findall(r"```(.*?)```", md_text, flags=re.DOTALL)

    # Marca todos os blocos temporariamente
    for i, block in enumerate(code_blocks):
        md_text = md_text.replace(f"```{block}```", f"__CODE_BLOCK_{i}__")

    if processar_links:
        md_text = re.sub(r"\{\{link: (.*?) \| (.*?)\}\}", r'<a href="\1" class="botao-link" target="_blank">\2</a>', md_text)
    else:
        md_text = re.sub(r"\{\{link: (.*?) \| (.*?)\}\}", r'<a href="\1" target="_blank">\2</a>', md_text)

    md_text = converter_listas_markdown(md_text)

    # Destacar linhas que começam com "|"
    def destacar_linhas_pipe(texto):
        linhas = texto.splitlines()
        novas_linhas = []

        for linha in linhas:
            l = linha.lstrip()
            if l.startswith("|"):
                # Remove o "|" e espaços após
                conteudo = l[1:].lstrip()

                # Processa markdown dentro da linha
                conteudo_html = markdown.markdown(conteudo, extensions=[])

                # Remove <p> gerado automaticamente
                conteudo_html = conteudo_html.replace("<p>", "").replace("</p>", "")

                novas_linhas.append(f'<p class="distaque-pipe">{conteudo_html}</p>')
            else:
                novas_linhas.append(linha)

        return "\n".join(novas_linhas)


    md_text = destacar_linhas_pipe(md_text)
    
    for i, block in enumerate(code_blocks):
        bloco_substituido = False

        if block.startswith('tablecard\n'):
            if processar_tables:
                tabela_md = block[len('tablecard\n'):].strip()
                linhas = tabela_md.splitlines()

                html_tabela = '<table>\n'
                cabecalhos = linhas[0].split('|')[1:-1]
                html_tabela += '  <thead><tr>' + ''.join(f'<th>{escape(c.strip())}</th>' for c in cabecalhos) + '</tr></thead>\n'
                html_tabela += '  <tbody>\n'
                for linha in linhas[2:]:
                    colunas = linha.split('|')[1:-1]
                    html_tabela += '    <tr>' + ''.join(f'<td>{escape(c.strip())}</td>' for c in colunas) + '</tr>\n'
                html_tabela += '  </tbody>\n</table>'

                html_card = '<div class="code-card">'
                if exibir_botao_copiar:
                    html_card += '<button class="copy-button" onclick="copiarCodigo(this)"><i class="fa-solid fa-copy"></i></button>'
                html_card += f'{html_tabela}</div>'

                md_text = md_text.replace(f"__CODE_BLOCK_{i}__", html_card)
                bloco_substituido = True

        elif block.startswith('table\n'):
            if processar_tables_std:
                tabela_md = block[len('table\n'):].strip()
                linhas = tabela_md.splitlines()

                html_tabela = '<div class="tabela-container"><table>\n'
                cabecalhos = linhas[0].split('|')[1:-1]
                html_tabela += '  <thead><tr>' + ''.join(f'<th>{markdown_inline(c.strip())}</th>' for c in cabecalhos) + '</tr></thead>\n'
                html_tabela += '  <tbody>\n'
                for linha in linhas[2:]:
                    colunas = linha.split('|')[1:-1]
                    html_tabela += '    <tr>' + ''.join(f'<td>{markdown_inline(c.strip())}</td>' for c in colunas) + '</tr>\n'
                html_tabela += '  </tbody>\n</table></div>'

                md_text = md_text.replace(f"__CODE_BLOCK_{i}__", html_tabela)
                bloco_substituido = True

        if not bloco_substituido:
            if processar_code_card:
                html_code = '<div class="code-card">'
                if exibir_botao_copiar:
                    html_code += '<button class="copy-button" onclick="copiarCodigo(this)"><i class="fa-solid fa-copy"></i></button>'
                html_code += f'<pre><code>{escape(block)}</code></pre></div>'
            else:
                html_code = f'<pre><code>{escape(block)}</code></pre>'

            md_text = md_text.replace(f"__CODE_BLOCK_{i}__", html_code)

    return md_text

def gerar_html_final(
    md_text,
    img_path,
    template_path,
    output_path,
    title,
    img_web_path,
    processar_links=True,
    processar_tables=True,
    processar_tables_std=True,
    processar_code_card=True,
    exibir_botao_copiar=True
):
    html_md = processar_variaveis_customizadas(
        md_text,
        processar_links,
        processar_tables,
        processar_tables_std,
        processar_code_card,
        exibir_botao_copiar
    )
    conteudo_html = markdown.markdown(html_md, extensions=['markdown.extensions.extra'])

    conteudo_html = re.sub(
        r'<img [^>]*src="(?:[^\"]*/)?(img-\d+\.png)"',
        lambda m: f'<img src="{img_web_path}/{m.group(1)}" alt="{m.group(1)}"',
        conteudo_html
    )

    template = Path(template_path).read_text(encoding='utf-8')
    template = re.sub(r'<title>.*?</title>', f'<title>{title}</title>', template)
    template = template.replace("{{content}}", conteudo_html)

    output_path.write_text(template, encoding='utf-8')
