"""Piecing - fabric inventory manager (Tkinter GUI)."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import printing
from database import FIELDS, GRAINS, Inventory, ValidationError
from sample_data import load as load_samples


class FabricForm(ttk.LabelFrame):
    """Form for adding and editing a fabric item."""

    def __init__(self, master, on_save, on_clear):
        super().__init__(master, text="Fabric", padding=8)
        self.vars = {f: tk.StringVar() for f in FIELDS}
        for i, f in enumerate(FIELDS):
            ttk.Label(self, text=f).grid(row=i, column=0, sticky="w", pady=2)
            if f == "GRAIN":
                w = ttk.Combobox(self, textvariable=self.vars[f], values=GRAINS, width=18)
            else:
                w = ttk.Entry(self, textvariable=self.vars[f], width=20)
            w.grid(row=i, column=1, pady=2, padx=4)
        self.save_btn = ttk.Button(self, text="Add", command=on_save)
        self.save_btn.grid(row=len(FIELDS), column=0, pady=6)
        ttk.Button(self, text="Clear", command=on_clear).grid(row=len(FIELDS), column=1, pady=6)

    def get(self):
        return {f: v.get() for f, v in self.vars.items()}

    def set(self, item):
        for f in FIELDS:
            self.vars[f].set("" if item is None else item[f])
        self.save_btn.config(text="Add" if item is None else "Update")


class TableView(ttk.Frame):
    """Scrollable table; click a heading to sort, ctrl-click to add a secondary sort."""

    def __init__(self, master, on_select, on_sort):
        super().__init__(master)
        self.tree = ttk.Treeview(self, columns=FIELDS, show="headings", selectmode="browse")
        for f in FIELDS:
            self.tree.heading(f, text=f, command=lambda f=f: on_sort(f))
            self.tree.column(f, width=90 if f != "NAME" else 160)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: on_select())

    def show(self, rows):
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", iid=r["ID"], values=[r[f] for f in FIELDS])

    def selected_id(self):
        sel = self.tree.selection()
        return sel[0] if sel else None


class PiecingApp(tk.Tk):
    def __init__(self, db_path="piecing.db"):
        super().__init__()
        self.title("Piecing - Fabric Inventory")
        self.geometry("1000x500")
        self.inv = Inventory(db_path)
        self.sort = []  # list of (field, descending)
        self.editing = None
        self.search = tk.StringVar()
        self.status = tk.StringVar()

        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        ttk.Entry(top, textvariable=self.search, width=25).pack(side="left", padx=4)
        self.search.trace_add("write", lambda *a: self.refresh())
        ttk.Button(top, text="Clear Sort", command=self.clear_sort).pack(side="left", padx=4)
        ttk.Button(top, text="Print", command=self.print_inventory).pack(side="right")
        ttk.Button(top, text="Export CSV", command=self.export).pack(side="right", padx=4)
        ttk.Button(top, text="Delete", command=self.delete).pack(side="right")
        ttk.Button(top, text="Load Samples", command=self.samples).pack(side="right", padx=4)

        body = ttk.Frame(self, padding=6)
        body.pack(fill="both", expand=True)
        self.form = FabricForm(body, self.save, self.clear_form)
        self.form.pack(side="left", fill="y", padx=(0, 8))
        self.table = TableView(body, self.on_select, self.on_sort)
        self.table.pack(side="left", fill="both", expand=True)
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x")
        self.clear_form()
        self.refresh()

    def rows(self):
        return self.inv.list(self.sort, self.search.get().strip())

    def refresh(self):
        rows = self.rows()
        self.table.show(rows)
        if self.editing and self.inv.get(self.editing):
            self.table.tree.selection_set(self.editing)
        desc = ", ".join(f"{f}{' desc' if d else ''}" for f, d in self.sort) or "none"
        self.status.set(f"{len(rows)} item(s); sort: {desc}")

    def on_sort(self, field):
        ctrl = bool(self._last_state & 0x4)
        current = dict(self.sort)
        desc = not current[field] if field in current else False
        if ctrl:
            self.sort = [(f, d) for f, d in self.sort if f != field] + [(field, desc)]
        else:
            self.sort = [(field, desc)]
        self.refresh()

    _last_state = 0

    def clear_sort(self):
        self.sort = []
        self.refresh()

    def on_select(self):
        item_id = self.table.selected_id()
        if item_id:
            self.editing = item_id
            self.form.set(self.inv.get(item_id))

    def clear_form(self):
        self.editing = None
        self.form.set(None)
        self.form.vars["ID"].set(self.inv.next_id())
        self.table.tree.selection_remove(self.table.tree.selection())

    def save(self):
        try:
            if self.editing:
                self.inv.update(self.editing, self.form.get())
                msg = "Item updated."
            else:
                self.inv.add(self.form.get())
                msg = "Item added."
        except ValidationError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        self.clear_form()
        self.refresh()
        self.status.set(msg)

    def delete(self):
        item_id = self.table.selected_id()
        if not item_id:
            messagebox.showinfo("Delete", "Select an item first.")
            return
        if messagebox.askyesno("Delete", f"Delete {item_id}?"):
            self.inv.delete(item_id)
            self.clear_form()
            self.refresh()

    def samples(self):
        load_samples(self.inv)
        self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.inv.export_csv(path, self.rows())
            self.status.set(f"Exported to {path}")

    def print_inventory(self):
        try:
            printing.print_rows(self.rows())
        except OSError as e:
            messagebox.showerror("Print failed", str(e))


def main():
    app = PiecingApp()
    app.bind_all("<Button-1>", lambda e: setattr(app, "_last_state", e.state))
    app.mainloop()


if __name__ == "__main__":
    main()
