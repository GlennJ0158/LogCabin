"""QuiltBack: fabric inventory and panel builder (Tkinter + SQLite). Run: python app.py"""
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from db import (COLUMNS, DB, FIELDS, FILE_BUTTONS, FILTER_FIELDS, NAV_RECORD, PANEL_CASE_FIELD, PANEL_CASES,
                PANEL_SELECTION_FIELD, RETAIN, sort_rows)
from patternwin import LogCabinWindow
from planner import plan_cases, cut_list, part_label
from tooltip import Tip
from printing import print_plan, render_manual_html, open_for_print, manual_blocks
from version import LABEL, VERSION

ALL_FABRICS = "All fabric records"
BOOL = {"Use", "Def", "RT"}
BOOL_DEFAULT = {"Use": True}   # new/cleared records: Use on, Def and RT off
CHOICE_FIELDS = {   # fields chosen from a list (Combobox)
    "Fabric": ("Color", "Shade", "Pattern", "Type", "Grain"),
    "Dropdown": ("TableName", "FieldName"),
    "Helptext": ("TableName", "FieldName"),
}
FILTER_KEYS = ("Name", "Color", "Shade", "Pattern", "Type", "Grain", "LengthMin", "LengthMax",
               "WidthMin", "WidthMax", "Use")
FILTER_LAYOUT = (   # Fabric filter widgets: (key, label, width) per row
    (("Name", "Name contains", 20), ("Color", "Color", 9), ("Shade", "Shade", 9), ("Pattern", "Pattern", 9)),
    (("Type", "Type", 9), ("Grain", "Grain", 9), ("Use", "Use", 5)),
    (("LengthMin", "Length min", 7), ("LengthMax", "max", 7), ("WidthMin", "Width min", 7), ("WidthMax", "max", 7)),
)
WIDE = {("Helptext", "HoverText"), ("Helptext", "FullText")}


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
    """Generic maintenance form for Fabric, Dropdown (DropDown table) or Helptext (HelpText table)."""
    def __init__(self, app, name):
        super().__init__(app.body)
        ttk.Label(self, text=f"v{VERSION}  {name}", foreground="gray").pack(anchor="nw", padx=8, pady=(4, 0))
        self.app, self.name, self.db = app, name, app.db
        self.fields = FIELDS[name]
        self.vars, self.widgets, self.sels, self.initial = {}, {}, [], {}
        self.selected = set()   # persistent selection (Fabric); grid highlight stays in self.sels
        self.active_name = None  # saved selection whose records the Fabric grid shows (None = all)
        self.shown_count = 0
        form = ttk.Frame(self); form.pack(fill="x", padx=8, pady=8)
        for i, f in enumerate(self.fields):
            ttk.Label(form, text=f).grid(row=i, column=0, sticky="e", padx=4, pady=2)
            if f in BOOL:
                v = tk.BooleanVar(value=BOOL_DEFAULT.get(f, False)); w = ttk.Checkbutton(form, variable=v)
            elif f in CHOICE_FIELDS.get(name, ()):
                v = tk.StringVar(); w = ttk.Combobox(form, textvariable=v, width=28)
            elif (name, f) == ("Helptext", "FullText"):
                box = ttk.Frame(form)
                w = tk.Text(box, height=6, width=60, wrap="word"); v = TextVar(w)
                sb = ttk.Scrollbar(box, orient="vertical", command=w.yview)
                w.configure(yscrollcommand=sb.set)
                w.grid(row=0, column=0); sb.grid(row=0, column=1, sticky="ns")
                box.grid(row=i, column=1, sticky="w")
            else:
                v = tk.StringVar(); w = ttk.Entry(form, textvariable=v, width=60 if (name, f) in WIDE else 30)
            if not isinstance(v, TextVar):
                w.grid(row=i, column=1, sticky="w")
            self.vars[f], self.widgets[f] = v, w
            self.attach_help(w, name, f)
        if name == "Dropdown":
            self.vars["TableName"].trace_add("write", lambda *_: self.update_field_choices())
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8)
        for label, cmd in (("Add", self.add), ("Update", self.update), ("Delete", self.delete), ("Clear", self.clear)):
            b = ttk.Button(bar, text=label, command=cmd); b.pack(side="left", padx=2)
            self.attach_help(b, name, label)
        if name == "Fabric":
            self.build_filter()
            self.build_selections()
        holder = ttk.Frame(self); holder.pack(fill="both", expand=True, padx=8, pady=8)
        cols = COLUMNS[name]
        self.tree = ttk.Treeview(holder, columns=cols, show="headings", height=12, selectmode="extended")
        for c in cols:
            wide = (name, c) in WIDE
            self.tree.heading(c, text=c); self.tree.column(c, width=250 if wide else 90, stretch=not wide)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1); holder.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.tag_configure("chosen", background="#fff3b0")
        self.tree.bind("<Control-a>", lambda e: self.select_all() or "break")
        self.bind_errors = binding_errors(name, {f: (self.widgets.get(f), self.vars.get(f)) for f in self.fields})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))

    # Fabric filter and saved selections
    def build_filter(self):
        box = ttk.LabelFrame(self, text="Filter")
        box.pack(fill="x", padx=8, pady=4)
        self.fvars = {k: tk.StringVar() for k in FILTER_KEYS}
        self.fvars["Use"].set("Any")
        self.fcombos = {}
        for r, row in enumerate(FILTER_LAYOUT):
            for c, (k, label, width) in enumerate(row):
                ttk.Label(box, text=label).grid(row=r, column=2 * c, padx=(6, 2), pady=2, sticky="e")
                if k in CHOICE_FIELDS["Fabric"]:
                    w = ttk.Combobox(box, textvariable=self.fvars[k], width=width)
                    self.fcombos[k] = w
                elif k == "Use":
                    w = ttk.Combobox(box, textvariable=self.fvars[k], width=width, values=["Any", "Yes", "No"],
                                     state="readonly")
                else:
                    w = ttk.Entry(box, textvariable=self.fvars[k], width=width)
                w.grid(row=r, column=2 * c + 1, sticky="w", pady=2)
                w.bind("<Return>", lambda e: self.refresh())
                self.attach_help(w, self.name, "Filter" + k)
        btns = ttk.Frame(box)
        btns.grid(row=len(FILTER_LAYOUT), column=0, columnspan=8, sticky="w", pady=4)
        for label, cmd in (("Apply Filter", self.refresh), ("Clear Filter", self.clear_filter),
                           ("Select All Shown", self.select_all), ("Select Highlighted", self.select_highlighted),
                           ("Invert Selection", self.invert_selection)):
            b = ttk.Button(btns, text=label, command=cmd); b.pack(side="left", padx=2)
            self.attach_help(b, self.name, label)
        self.shown = ttk.Label(btns, text="")
        self.shown.pack(side="left", padx=8)

    def build_selections(self):
        box = ttk.LabelFrame(self, text="Save Selection")
        box.pack(fill="x", padx=8, pady=4)
        ttk.Label(box, text="Title").grid(row=0, column=0, padx=(6, 2), pady=4)
        self.set_title = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.set_title, width=40)
        entry.grid(row=0, column=1, padx=2, sticky="w")
        self.attach_help(entry, self.name, "Title")
        b = ttk.Button(box, text="Save Selection", command=self.save_selection)
        b.grid(row=0, column=2, padx=6)
        self.attach_help(b, self.name, "Save Selection")
        named = ttk.LabelFrame(self, text="Named Selection")
        named.pack(fill="x", padx=8, pady=4)
        ttk.Label(named, text="Named selection").grid(row=0, column=0, padx=(6, 2), pady=4)
        self.set_combo = ttk.Combobox(named, width=40, state="readonly")
        self.set_combo.grid(row=0, column=1, padx=2, sticky="w")
        self.attach_help(self.set_combo, self.name, "NamedSelection")
        for col, (label, cmd) in enumerate((("Add to Selection", self.add_to_named),
                                            ("Remove From Selection", self.remove_from_named),
                                            ("Activate Selection", self.activate_selection)), start=2):
            b = ttk.Button(named, text=label, command=cmd)
            b.grid(row=0, column=col, padx=6)
            self.attach_help(b, self.name, label)

    def refresh_selection_names(self):
        self.set_combo["values"] = self.db.selection_names()

    def chosen_selection(self):
        name = self.set_combo.get().strip()
        if not name:
            raise ValueError("Choose a named selection first")
        return name

    def add_to_named(self):
        self._change_named(add=True, title="Add to Selection")

    def remove_from_named(self):
        self._change_named(add=False, title="Remove From Selection")

    def _change_named(self, add, title):
        try:
            name = self.chosen_selection()
            if not self.selected:
                raise ValueError("Select at least one fabric record")
            self.db.change_selection(name, self.selected, add=add)
        except (ValueError, sqlite3.Error) as e:
            return messagebox.showerror(title, str(e))
        messagebox.showinfo(title, f"{'Added' if add else 'Removed'} {len(self.selected)} fabric record(s).")

    def save_selection(self):
        try:
            self.db.save_selection(self.set_title.get(), self.selected)
        except (ValueError, sqlite3.Error) as e:
            return messagebox.showerror("Save Selection", str(e))
        self.set_title.set("")
        self.refresh_selection_names()
        messagebox.showinfo("Save Selection", f"Saved {len(self.selected)} fabric record(s).")

    def activate_selection(self):
        try:
            self.chosen_selection()
        except ValueError as e:
            return messagebox.showerror("Activate Selection", str(e))
        self.active_name = self.set_combo.get().strip()
        self.refresh()

    def clear_filter(self):
        for k, v in self.fvars.items():
            v.set("Any" if k == "Use" else "")
        self.active_name = None
        self.refresh()

    def filter_criteria(self):
        def num(k):
            t = self.fvars[k].get().strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                raise ValueError(f"Filter {k} must be a number")
        use = {"Any": None, "Yes": 1, "No": 0}[self.fvars["Use"].get()]
        g = lambda k: self.fvars[k].get().strip()  # noqa: E731
        return dict(name=g("Name"), color=g("Color"), shade=g("Shade"), pattern=g("Pattern"),
                    type_=g("Type"), grain=g("Grain"), length=(num("LengthMin"), num("LengthMax")),
                    width=(num("WidthMin"), num("WidthMax")), use=use)

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def select_highlighted(self):
        if not self.sels:
            return
        self.selected = set(self.sels)
        self.paint()

    def invert_selection(self):
        self.selected = {int(i) for i in self.tree.get_children()} - self.selected
        self.paint()

    def paint(self):
        """Mark selected rows in the grid and show the selection count."""
        self.tree.selection_set(())   # clear the blue highlight; chosen rows show yellow
        for iid in self.tree.get_children():
            self.tree.item(iid, tags=("chosen",) if int(iid) in self.selected else ())
        self.shown.config(text=f"{self.shown_count} shown, {len(self.selected)} selected")

    # shared help, choices and rows
    def attach_help(self, w, screen, field):
        hover, _ = self.db.helptext(screen, field)
        Tip(w, hover)
        w.bind("<F1>", lambda e: self.show_full(screen, field))

    def show_full(self, screen, field):
        hover, full = self.db.helptext(screen, field)
        messagebox.showinfo(f"{screen}.{field}", full or hover or "No help available.")

    def refresh_choices(self):
        for f in CHOICE_FIELDS.get(self.name, ()):
            if (self.name, f) == ("Dropdown", "FieldName"):
                self.update_field_choices()
            else:
                self.widgets[f]["values"] = self.db.choices(self.name, f)
        if self.name == "Fabric":
            for k, w in self.fcombos.items():
                w["values"] = [""] + self.db.choices("Fabric", k)

    def update_field_choices(self):
        """Dropdown.FieldName lists only the fields of the chosen TableName."""
        if self.name != "Dropdown" or "FieldName" not in self.widgets:
            return
        vals = self.db.choices("Dropdown", "FieldName", table=self.vars["TableName"].get())
        self.widgets["FieldName"]["values"] = vals
        if self.vars["FieldName"].get() not in vals:
            self.vars["FieldName"].set("")

    def apply_defaults(self):
        for f, v in self.db.defaults(self.name).items():
            if v and not self.vars[f].get():
                self.vars[f].set(v)

    def show_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for r in sort_rows(self.name, rows):
            self.tree.insert("", "end", iid=str(r["ID"]), values=[r[c] for c in COLUMNS[self.name]],
                             tags=("chosen",) if r["ID"] in self.selected else ())
        self.shown_count = len(rows)

    def refresh(self):
        self.refresh_choices()
        self.apply_defaults()
        if self.name == "Fabric":
            self.refresh_fabric()
        else:
            self.show_rows(self.db.list(self.name))
        self.sels = []

    def refresh_fabric(self):
        self.selected &= {r["ID"] for r in self.db.list("Fabric")}   # drop deleted records from the selection
        self.refresh_selection_names()
        try:
            criteria = self.filter_criteria()
        except ValueError as e:
            messagebox.showerror("Filter", str(e))
            criteria = {}
        rows = self.db.filter_fabric(**criteria)
        if self.active_name is not None:
            if self.active_name in self.db.selection_names():
                keep = self.db.selection_ids(self.active_name)
                rows = [r for r in rows if r["ID"] in keep]
            else:
                self.active_name = None
        self.show_rows(rows)
        self.paint()

    def clear(self):
        self.sels = []
        self.tree.selection_set(())
        self.reset()

    def reset(self, keep=()):
        """Blank every field not in keep; choice fields take their defaults and BOOL fields their defaults."""
        d = self.db.defaults(self.name)
        for f in self.fields:
            if f in keep:
                continue
            if f in BOOL:
                self.vars[f].set(BOOL_DEFAULT.get(f, False))
            else:
                self.vars[f].set(d.get(f, ""))

    def select(self, _):
        self.sels = [int(i) for i in self.tree.selection()]
        if not self.sels:
            return
        rows = {r["ID"]: r for r in self.db.list(self.name)}
        chosen = [rows[i] for i in self.sels if i in rows]
        for f in self.fields:
            vals = {r[f] for r in chosen}
            v = vals.pop() if len(vals) == 1 else None   # differing values show blank in a group
            if f in BOOL:
                self.vars[f].set(bool(v) if v is not None else BOOL_DEFAULT.get(f, False))
            else:
                self.vars[f].set("" if v is None else v)
        self.initial = {f: self.vars[f].get() for f in self.fields}

    def values(self, only=None):
        return {f: (1 if self.vars[f].get() else 0) if f in BOOL else self.vars[f].get()
                for f in self.fields if only is None or f in only}

    def after_save(self):
        """Keep the fields listed in RETAIN for the next entry; blank or default the rest."""
        self.reset(keep=RETAIN.get(self.name, ()))
        self.sels = []
        self.refresh()

    def add(self):
        try:
            self.db.add(self.name, self.values())
        except (ValueError, sqlite3.Error) as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def update(self):
        if not self.sels:
            return messagebox.showinfo("Update", "Select a row first.")
        try:
            if len(self.sels) > 1:
                changed = [f for f in self.fields if self.vars[f].get() != self.initial.get(f)]
                if not changed:
                    return messagebox.showinfo("Update", "No fields were changed.")
                if not messagebox.askyesno("Update group", f"Change {', '.join(changed)} on "
                                           f"{len(self.sels)} records?"):
                    return
                self.db.update_many(self.name, self.sels, self.values(only=changed))
            else:
                self.db.update_many(self.name, self.sels, self.values())
        except (ValueError, sqlite3.Error) as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def delete(self):
        n = len(self.sels)
        if n and messagebox.askyesno("Delete", "Delete selected record?" if n == 1 else f"Delete {n} selected records?"):
            self.db.delete_many(self.name, self.sels)
            self.after_save()


class PanelForm(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.body)
        ttk.Label(self, text=f"v{VERSION}  Panel", foreground="gray").pack(anchor="nw", padx=8, pady=(4, 0))
        self.app, self.db, self.plan, self.plan_id = app, app.db, None, None
        self.cases = {}
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=8)
        self.entries = {}
        self.v = {k: tk.StringVar(value=d) for k, d in
                  (("PANELNAME", ""), ("SEAMALLOWANCE", "0.25"), ("LENGTH", ""), ("WIDTH", ""), ("MAXPARTS", "4"))}
        for i, (k, var) in enumerate(self.v.items()):
            ttk.Label(top, text=k).grid(row=0, column=2 * i)
            e = ttk.Entry(top, textvariable=var, width=12); e.grid(row=0, column=2 * i + 1, padx=4)
            self.entries[k] = e
            self.tip(e, "Panel", k)
        ttk.Label(top, text=PANEL_SELECTION_FIELD).grid(row=1, column=0, pady=(6, 0))
        self.sel_var = tk.StringVar(value=ALL_FABRICS)
        self.sel_box = ttk.Combobox(top, textvariable=self.sel_var, state="readonly", width=40)
        self.sel_box.grid(row=1, column=1, columnspan=8, sticky="w", padx=4, pady=(6, 0))
        self.tip(self.sel_box, "Panel", PANEL_SELECTION_FIELD)
        ttk.Label(top, text=PANEL_CASE_FIELD).grid(row=2, column=0, pady=(6, 0))
        case_row = ttk.Frame(top); case_row.grid(row=2, column=1, columnspan=8, sticky="w", padx=4, pady=(6, 0))
        self.case_var = tk.StringVar(value=PANEL_CASES[0])
        self.case_btns = {}
        for c in PANEL_CASES:
            rb = ttk.Radiobutton(case_row, text=c, value=c, variable=self.case_var, command=self.switch_case)
            rb.pack(side="left", padx=4)
            rb.state(["disabled"])
            self.tip(rb, "Panel", c)
            self.case_btns[c] = rb
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8)
        for label, cmd in (("Build Plan", self.build), ("Save Plan", self.save), ("Approve Plan", self.approve),
                           ("Print Plan", self.print)):
            b = ttk.Button(bar, text=label, command=cmd); b.pack(side="left", padx=2)
            self.tip(b, "Panel", label)
        self.bind_errors = binding_errors("Panel", {k: (self.entries.get(k), self.v.get(k)) for k in self.v})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))
        self.text = tk.Text(self, height=8); self.text.pack(fill="x", padx=8, pady=4)
        self.canvas = tk.Canvas(self, width=500, height=400, bg="white"); self.canvas.pack(padx=8, pady=4)

    def tip(self, w, record, field):
        """Tool tip on hover; F1 shows the full help text for record.field."""
        hover, full = self.db.helptext(record, field)
        Tip(w, hover)
        w.bind("<F1>", lambda ev: messagebox.showinfo(field, full or hover or "No help."))

    def refresh(self):
        self.sel_box["values"] = [ALL_FABRICS] + self.db.selection_names()
        if self.sel_var.get() not in self.sel_box["values"]:
            self.sel_var.set(ALL_FABRICS)

    def build(self):
        try:
            nums = {}
            for k in ("SEAMALLOWANCE", "LENGTH", "WIDTH"):
                try:
                    nums[k] = float(self.v[k].get())
                except ValueError:
                    raise ValueError(f"{k} must be a number")
            try:
                nums["MAXPARTS"] = int(self.v["MAXPARTS"].get())
            except ValueError:
                raise ValueError("MAXPARTS must be a whole number")
            if nums["MAXPARTS"] < 1:
                raise ValueError("MAXPARTS must be at least 1")
            panel = {"PANELNAME": self.v["PANELNAME"].get() or "Panel", **nums}
            if min(panel["LENGTH"], panel["WIDTH"]) <= 0 or panel["SEAMALLOWANCE"] < 0:
                raise ValueError("Dimensions must be positive")
            chosen = self.sel_var.get()
            fabrics = self.db.list("Fabric") if chosen == ALL_FABRICS else self.db.fabrics_in_selection(chosen)
            self.cases = plan_cases(panel, fabrics); self.plan_id = None
        except ValueError as e:
            return messagebox.showerror("Plan", str(e))
        if not any(self.cases.values()):
            return messagebox.showerror("Plan", f"Cannot build panel with {nums['MAXPARTS']} or fewer parts from available inventory")
        self.case_var.set(PANEL_CASES[0] if self.cases["symmetric"] else PANEL_CASES[1])
        for c in PANEL_CASES:
            self.case_btns[c].state(["!disabled" if self.cases[c.lower()] else "disabled"])
        self.show_case()

    def switch_case(self):
        self.plan_id = None
        self.show_case()

    def show_case(self):
        """Display the plan for the selected case; a saved plan must be saved again after switching."""
        label = self.case_var.get()
        self.plan = self.cases.get(label.lower())
        self.text.delete("1.0", "end"); self.canvas.delete("all")
        if self.plan is None:
            self.text.insert("end", f"{label} layout is not possible with the available inventory.")
            return
        self.text.insert("end", f"Case: {label}\nSeams: {self.plan['seams']}\n{cut_list(self.plan)}")
        self.draw()

    def draw(self):
        c, p = self.canvas, self.plan
        c.delete("all")
        s = min(460 / p["width"], 360 / p["length"])
        for part in p["parts"]:
            x0, y0 = 20 + part["x"] * s, 20 + part["y"] * s
            c.create_rectangle(x0, y0, x0 + part["w"] * s, y0 + part["h"] * s, fill="#cfe8ff")
            c.create_text(x0 + part["w"] * s / 2, y0 + part["h"] * s / 2, text=part_label(part),
                          width=part["w"] * s - 4, justify="center")

    def save(self):
        if not self.plan:
            return messagebox.showinfo("Save", "Build a plan first, or choose a case that is possible.")
        pid = self.db.add_panel(self.plan["panel"], self.plan["seam_allowance"], self.plan["length"],
                                self.plan["width"])
        self.plan_id = self.db.save_plan(pid, self.plan)
        messagebox.showinfo("Save", f"{self.case_var.get()} cutting plan saved.")

    def print(self):
        if not self.plan:
            return messagebox.showinfo("Print", "Build a plan first.")
        try:
            print_plan(self.plan)
        except Exception as e:
            messagebox.showerror("Print", str(e))

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
        self.title(LABEL); self.geometry("820x780")
        self.db = DB()
        nav = ttk.Frame(self); nav.pack(fill="x")
        self.body = ttk.Frame(self); self.body.pack(fill="both", expand=True)
        self.forms = {"Fabric": RecordForm(self, "Fabric"), "Panel": PanelForm(self),
                      "Dropdown": RecordForm(self, "Dropdown"), "Helptext": RecordForm(self, "Helptext")}
        for n in self.forms:
            b = ttk.Button(nav, text=n, command=lambda n=n: self.show(n)); b.pack(side="left", padx=2, pady=2)
            self.nav_tip(b, n)
        self.log_win = None
        b = ttk.Button(nav, text="Log Cabin", command=self.show_log_cabin); b.pack(side="left", padx=2, pady=2)
        self.nav_tip(b, "Log Cabin")
        file_cmds = {"Export CSV": self.export_csv, "Import CSV": self.import_csv, "User Manual": self.show_manual}
        for label in FILE_BUTTONS:
            b = ttk.Button(nav, text=label, command=file_cmds[label]); b.pack(side="right", padx=2, pady=2)
            self.nav_tip(b, label)
        self.show("Fabric")

    def nav_tip(self, b, label):
        hover, full = self.db.helptext(NAV_RECORD, label)
        from_tip = Tip(b, hover)
        b.bind("<F1>", lambda e: messagebox.showinfo(label, full or hover or "No help."))
        return from_tip

    def show_log_cabin(self):
        if self.log_win is None or not self.log_win.winfo_exists():
            self.log_win = LogCabinWindow(self, self.db)
        self.log_win.deiconify()
        self.log_win.lift()

    def show_manual(self):
        hover, full = self.db.helptext(NAV_RECORD, "User Manual")
        heading = hover or "User Manual"
        win = tk.Toplevel(self)
        win.title("User Manual")
        win.geometry("720x600")
        ttk.Label(win, text=heading, font=("TkDefaultFont", 14, "bold"), wraplength=680).pack(anchor="w", padx=12, pady=(12, 6))
        holder = ttk.Frame(win); holder.pack(fill="both", expand=True, padx=12)
        vsb = ttk.Scrollbar(holder, orient="vertical"); vsb.pack(side="right", fill="y")
        text = tk.Text(holder, wrap="word", yscrollcommand=vsb.set, padx=8, pady=6)
        text.tag_configure("h", font=("TkDefaultFont", 12, "bold"), spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=6)
        text.tag_configure("li", lmargin1=24, lmargin2=40, spacing3=3)
        text.tag_configure("b", font=("TkDefaultFont", 10, "bold"))
        for kind, runs in manual_blocks(full or "No help."):
            if kind == "li":
                text.insert("end", "\u2022  ", ("li",))
            for t, bold in runs:
                tags = (kind, "b") if bold else (kind,)
                text.insert("end", t, tags)
            text.insert("end", "\n", (kind,))
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        vsb.configure(command=text.yview)
        bar = ttk.Frame(win); bar.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar, text="Print", command=lambda: self.print_manual(heading, full)).pack(side="right")

    def print_manual(self, heading, body):
        try:
            open_for_print(render_manual_html(heading, body))
        except Exception as e:
            messagebox.showerror("Print", str(e))

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Export all records", defaultextension=".csv",
                                            initialfile="quiltback.csv",
                                            filetypes=[("CSV (~ delimited)", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            counts = self.db.export_csv(path)
        except OSError as e:
            return messagebox.showerror("Export CSV", str(e))
        lines = [f"{t}: {n} row(s)" for t, n in counts.items()]
        messagebox.showinfo("Export CSV", "\n".join(lines + ["", path]))

    def import_csv(self):
        path = filedialog.askopenfilename(title="Import records",
                                          filetypes=[("CSV (~ delimited)", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno("Import CSV", "Rows whose ID already exists will be overwritten. Continue?"):
            return
        try:
            counts = self.db.import_csv(path)
        except (OSError, ValueError, sqlite3.Error) as e:
            return messagebox.showerror("Import CSV", str(e))
        for f in self.forms.values():
            f.refresh()
        lines = [f"{t}: {n} row(s)" for t, n in counts.items()]
        messagebox.showinfo("Import CSV", "\n".join(lines) or "No rows found in file.")

    def show(self, name):
        for f in self.forms.values():
            f.pack_forget()
        self.forms[name].refresh(); self.forms[name].pack(fill="both", expand=True)


if __name__ == "__main__":
    App().mainloop()
