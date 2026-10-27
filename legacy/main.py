import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox
from app_ui import App

if __name__ == '__main__':
    root = tb.Window(themename="cosmo")
    app = App(root)

    root.protocol("WM_DELETE_WINDOW", lambda: (
        root.destroy() if messagebox.askyesno("Sair", "Tem certeza que deseja sair?") else None
    ))

    root.mainloop()
