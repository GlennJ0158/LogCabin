"""Hover tool tips for Tkinter widgets (shared by the main window and the Log Cabin window)."""
import tkinter as tk


class Tip:
    def __init__(self, w, text):
        self.w, self.text, self.t = w, text, None
        w.bind("<Enter>", self.show, add="+"); w.bind("<Leave>", self.hide, add="+")

    def show(self, _):
        if not self.text or self.t:
            return
        self.t = tk.Toplevel(self.w); self.t.wm_overrideredirect(True)
        self.t.geometry(f"+{self.w.winfo_rootx() + 10}+{self.w.winfo_rooty() + self.w.winfo_height()}")
        tk.Label(self.t, text=self.text, background="#ffffe0", relief="solid", borderwidth=1).pack()

    def hide(self, _):
        if self.t:
            self.t.destroy(); self.t = None
