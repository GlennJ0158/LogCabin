"""QuiltBack: fabric inventory and panel builder (Tkinter + SQLite). Run: python app.py"""
import tkinter as tk
from tkinter import ttk, messagebox

from db import DB, FIELDS
from planner import plan_panel, cut_list

BOOL = {"Use", "Def"}
# dropdown sources: (screen, field) -> (record, field) in DROPDOWN, or fixed callable
STATIC = {("Fabric", "Type"): ("Fabric", "Type"), ("Fabric", "Grain"): ("Fabric", "Grain"),
          ("Dropdown", "RecordName"): ("Dropdown", "RecordName"),
          ("Dropdown", "FieldName"): ("Dropdown", "FieldName"),
          ("Helptext", "RecordName"): ("Helptext", "RecordName"),
          ("Helptext", "FieldName"): ("Helptext", "FieldName")}
RETAIN = {("Dropdown", "RecordName"), ("Dropdown", "FieldName"),
          ("Helptext", "RecordName"), ("Helptext", "FieldName")}


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


class TextVar:
    """StringVar-like adapter so a tk.Text can be read/written via get()/set()."""
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text.get("1.0", "end-1c")

    def set(self, value):
        self.text.delete("1.0", "end"); self.text.insert("1.0", value)


def binding_errors(label, pairs):
    """pairs: {field: (widget, var)}. Return a message per field whose widget is not bound to its variable."""
    errs = []
    for f, (w, v) in pairs.items():
        if v is None or w is None:
            errs.append(f"{label}.{f}: no variable/widget defined")
        elif isinstance(v, TextVar):
            if v.text is not w:
                errs.append(f"{label}.{f}: text widget is not bound to its variable")
        else:
            opt = "variable" if isinstance(w, (ttk.Checkbutton, tk.Checkbutton)) else "textvariable"
            try:
                bound = str(w.cget(opt))
            except tk.TclError:
                bound = ""
            if bound != str(v):
                errs.append(f"{label}.{f}: widget is not bound to its variable")
    return errs


class RecordForm(ttk.Frame):
    """Generic maintenance form for FABRIC, DROPDOWN or HELPTEXT."""
    def __init__(self, app, name):
        super().__init__(app.body)
        self.app, self.name, self.db = app, name, app.db
        self.fields = FIELDS[name][1:]
        self.vars, self.widgets, self.sel = {}, {}, None
        form = ttk.Frame(self); form.pack(fill="x", padx=8, pady=8)
        for i, f in enumerate(self.fields):
            ttk.Label(form, text=f.upper()).grid(row=i, column=0, sticky="e", padx=4, pady=2)
            if f in BOOL:
                v = tk.BooleanVar(value=True); w = ttk.Checkbutton(form, variable=v)
            elif (name, f) in STATIC:
                v = tk.StringVar(); w = ttk.Combobox(form, textvariable=v, width=28)
            elif (name, f) == ("Helptext", "FullHelp"):
                box = ttk.Frame(form)
                w = tk.Text(box, height=6, width=60, wrap="word"); v = TextVar(w)
                sb = ttk.Scrollbar(box, orient="vertical", command=w.yview)
                w.configure(yscrollcommand=sb.set)
                w.grid(row=0, column=0); sb.grid(row=0, column=1, sticky="ns")
                box.grid(row=i, column=1, sticky="w")
            else:
                v = tk.StringVar(); w = ttk.Entry(form, textvariable=v, width=60 if (name, f) == ("Helptext", "HoverText") else 30)
            if not isinstance(v, TextVar):
                w.grid(row=i, column=1, sticky="w")
            self.vars[f], self.widgets[f] = v, w
            self.attach_help(w, name, f)
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8)
        for label, cmd in (("Add", self.add), ("Update", self.update), ("Delete", self.delete), ("Clear", self.clear)):
            b = ttk.Button(bar, text=label, command=cmd); b.pack(side="left", padx=2)
            self.attach_help(b, name, label)
        holder = ttk.Frame(self); holder.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree = ttk.Treeview(holder, columns=FIELDS[name], show="headings", height=12)
        for c in FIELDS[name]:
            wide = name == "Helptext" and c in ("HoverText", "FullHelp")
            self.tree.heading(c, text=c.upper()); self.tree.column(c, width=250 if wide else 90, stretch=not wide)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1); holder.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.bind_errors = binding_errors(name, {f: (self.widgets.get(f), self.vars.get(f)) for f in self.fields})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))

    def attach_help(self, w, screen, field):
        hover, full = self.db.helptext(screen, field)
        Tip(w, hover)
        w.bind("<F1>", lambda e: self.show_full(screen, field))

    def show_full(self, screen, field):
        hover, full = self.db.helptext(screen, field)
        messagebox.showinfo(f"{screen}.{field}", full or hover or "No help available.")

    def refresh(self):
        for f in self.fields:
            if (self.name, f) in STATIC:
                vals, _, err = self.db.dropdown(*STATIC[(self.name, f)])
                self.widgets[f]["values"] = vals
                if err:
                    messagebox.showerror("Dropdown default", err)
        self.tree.delete(*self.tree.get_children())
        for r in self.db.list(self.name):
            self.tree.insert("", "end", iid=str(r["ID"]), values=[r[c.upper()] for c in FIELDS[self.name]])
        for f in self.fields:   # first-show defaults
            if not self.vars[f].get() and f not in BOOL and (self.name, f) in STATIC:
                self.apply_default(f)

    def apply_default(self, f):
        _, d, err = self.db.dropdown(*STATIC[(self.name, f)])
        if err:
            messagebox.showerror("Dropdown default", err)
        self.vars[f].set(d or "")

    def clear(self):
        self.sel = None
        for f in self.fields:
            if f in BOOL:
                self.vars[f].set(True)
            elif (self.name, f) in STATIC:
                self.apply_default(f)
            else:
                self.vars[f].set("")

    def select(self, _):
        s = self.tree.selection()
        if not s:
            return
        self.sel = int(s[0])
        row = [r for r in self.db.list(self.name) if r["ID"] == self.sel][0]
        for f in self.fields:
            v = row[f.upper()]
            self.vars[f].set(bool(v) if f in BOOL else ("" if v is None else v))

    def values(self):
        out = {}
        for f in self.fields:
            v = self.vars[f].get()
            if f in BOOL:
                v = 1 if v else 0
            elif f in ("Length", "Width"):
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{f} must be a number")
                if v <= 0:
                    raise ValueError(f"{f} must be positive")
            elif f in ("Name", "RecordName", "FieldName", "Value") and not str(v).strip():
                raise ValueError(f"{f} is required")
            out[f.upper()] = v
        return out

    def after_save(self):
        """Retain last-used values: dropdown-linked fields stay as entered; others reset."""
        for f in self.fields:
            if f in BOOL:
                self.vars[f].set(True)
            elif (self.name, f) not in STATIC and (self.name, f) not in RETAIN and f != "Grain":
                self.vars[f].set("")
        self.sel = None
        self.refresh()

    def add(self):
        try:
            self.db.add(self.name, **self.values())
        except (ValueError, Exception) as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def update(self):
        if self.sel is None:
            return messagebox.showinfo("Update", "Select a row first.")
        try:
            self.db.update(self.name, self.sel, **self.values())
        except Exception as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def delete(self):
        if self.sel is not None and messagebox.askyesno("Delete", "Delete selected record?"):
            self.db.delete(self.name, self.sel); self.after_save()


class PanelForm(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.body)
        self.app, self.db, self.plan, self.plan_id = app, app.db, None, None
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=8)
        self.entries = {}
        self.v = {k: tk.StringVar(value=d) for k, d in
                  (("PANELNAME", ""), ("SEAMALLOWANCE", "0.25"), ("LENGTH", ""), ("WIDTH", ""))}
        for i, (k, var) in enumerate(self.v.items()):
            ttk.Label(top, text=k).grid(row=0, column=2 * i)
            e = ttk.Entry(top, textvariable=var, width=12); e.grid(row=0, column=2 * i + 1, padx=4)
            self.entries[k] = e
            Tip(e, self.db.helptext("Panel", k)[0])
            e.bind("<F1>", lambda ev, k=k: messagebox.showinfo(k, self.db.helptext("Panel", k)[1] or "No help."))
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8)
        for label, cmd in (("Build Plan", self.build), ("Save Plan", self.save), ("Approve Plan", self.approve)):
            b = ttk.Button(bar, text=label, command=cmd); b.pack(side="left", padx=2)
            Tip(b, self.db.helptext("Panel", label)[0])
        self.bind_errors = binding_errors("Panel", {k: (self.entries.get(k), self.v.get(k)) for k in self.v})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))
        self.text = tk.Text(self, height=8); self.text.pack(fill="x", padx=8, pady=4)
        self.canvas = tk.Canvas(self, width=500, height=400, bg="white"); self.canvas.pack(padx=8, pady=4)

    def refresh(self):
        pass

    def build(self):
        try:
            nums = {}
            for k in ("SEAMALLOWANCE", "LENGTH", "WIDTH"):
                try:
                    nums[k] = float(self.v[k].get())
                except ValueError:
                    raise ValueError(f"{k} must be a number")
            panel = {"PANELNAME": self.v["PANELNAME"].get() or "Panel", **nums}
            if min(panel["LENGTH"], panel["WIDTH"]) <= 0 or panel["SEAMALLOWANCE"] < 0:
                raise ValueError("Dimensions must be positive")
            self.plan = plan_panel(panel, self.db.list("FABRIC")); self.plan_id = None
        except ValueError as e:
            return messagebox.showerror("Plan", str(e))
        self.text.delete("1.0", "end")
        self.text.insert("end", f"Seams: {self.plan['seams']}\n{cut_list(self.plan)}")
        self.draw()

    def draw(self):
        c, p = self.canvas, self.plan
        c.delete("all")
        s = min(460 / p["width"], 360 / p["length"])
        for part in p["parts"]:
            x0, y0 = 20 + part["x"] * s, 20 + part["y"] * s
            c.create_rectangle(x0, y0, x0 + part["w"] * s, y0 + part["h"] * s, fill="#cfe8ff")
            c.create_text(x0 + part["w"] * s / 2, y0 + part["h"] * s / 2, text=f"Fabric #{part['fabric_id']}")

    def save(self):
        if not self.plan:
            return messagebox.showinfo("Save", "Build a plan first.")
        pid = self.db.add("PANEL", PANELNAME=self.plan["panel"], SEAMALLOWANCE=self.plan["seam_allowance"],
                          LENGTH=self.plan["length"], WIDTH=self.plan["width"])
        self.plan_id = self.db.save_plan(pid, self.plan)
        messagebox.showinfo("Save", "Cutting plan saved.")

    def approve(self):
        if self.plan_id is None:
            return messagebox.showinfo("Approve", "Save the plan first.")
        try:
            self.db.approve_plan(self.plan_id)
        except ValueError as e:
            return messagebox.showerror("Approve", str(e))
        messagebox.showinfo("Approve", "Plan approved; inventory reduced.")
        self.plan = self.plan_id = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("QuiltBack"); self.geometry("820x780")
        self.db = DB()
        nav = ttk.Frame(self); nav.pack(fill="x")
        self.body = ttk.Frame(self); self.body.pack(fill="both", expand=True)
        self.forms = {"Fabric": RecordForm(self, "Fabric"), "Panel": PanelForm(self),
                      "Dropdown": RecordForm(self, "Dropdown"), "Helptext": RecordForm(self, "Helptext")}
        for n in self.forms:
            b = ttk.Button(nav, text=n, command=lambda n=n: self.show(n)); b.pack(side="left", padx=2, pady=2)
        self.show("Fabric")

    def show(self, name):
        for f in self.forms.values():
            f.pack_forget()
        self.forms[name].refresh(); self.forms[name].pack(fill="both", expand=True)


if __name__ == "__main__":
    App().mainloop()
