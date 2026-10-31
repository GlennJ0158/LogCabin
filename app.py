"""QuiltBack: fabric inventory and panel builder (Tkinter + SQLite). Run: python app.py"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3

from db import DB, FIELDS, FILTER_FIELDS, NAV_RECORD, FILE_BUTTONS, PANEL_SELECTION_FIELD, PANEL_CASE_FIELD, PANEL_CASES, filter_fabric, sort_rows
from planner import plan_cases, cut_list, part_label
from printing import print_plan, render_manual_html, open_for_print
from version import LABEL, VERSION

ALL_FABRICS = "All fabric records"
BOOL = {"Use", "Def"}
# dropdown sources: (screen, field) -> (record, field) in DROPDOWN, or fixed callable
STATIC = {("Fabric", "Type"): ("Fabric", "Type"), ("Fabric", "Grain"): ("Fabric", "Grain"),
          ("Dropdown", "RecordName"): ("Dropdown", "RecordName"),
          ("Dropdown", "FieldName"): ("Dropdown", "FieldName"),
          ("Helptext", "RecordName"): ("Helptext", "RecordName"),
          ("Helptext", "FieldName"): ("Helptext", "FieldName")}
RETAIN = {("Fabric", "Length"), ("Fabric", "Width"), ("Dropdown", "RecordName"), ("Dropdown", "FieldName"),
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
        ttk.Label(self, text=f"v{VERSION}  {name}", foreground="gray").pack(anchor="nw", padx=8, pady=(4, 0))
        self.app, self.name, self.db = app, name, app.db
        self.fields = FIELDS[name][1:]
        self.vars, self.widgets, self.sel, self.sels, self.initial = {}, {}, None, [], {}
        self.selected = set()   # persistent selection (Fabric); grid highlight stays in self.sels
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
        if name == "Fabric":
            self.build_filter()
            self.build_save_set()
        holder = ttk.Frame(self); holder.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree = ttk.Treeview(holder, columns=FIELDS[name], show="headings", height=12, selectmode="extended")
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
        self.tree.tag_configure("chosen", background="#fff3b0")
        self.tree.bind("<Control-a>", lambda e: self.select_all() or "break")
        self.bind_errors = binding_errors(name, {f: (self.widgets.get(f), self.vars.get(f)) for f in self.fields})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))

    def build_filter(self):
        box = ttk.LabelFrame(self, text="Filter")
        box.pack(fill="x", padx=8, pady=4)
        self.fvars = {k: tk.StringVar() for k in
                      ("Name", "Type", "Grain", "LengthMin", "LengthMax", "WidthMin", "WidthMax", "Use")}
        self.fvars["Use"].set("Any")
        self.fcombos = {}
        spec = (("Name", "Name contains", 14), ("Type", "Type", 10), ("Grain", "Grain", 10),
                ("LengthMin", "Length min", 6), ("LengthMax", "max", 6),
                ("WidthMin", "Width min", 6), ("WidthMax", "max", 6), ("Use", "Use", 5))
        for i, (k, label, width) in enumerate(spec):
            ttk.Label(box, text=label).grid(row=0, column=2 * i, padx=(6, 2))
            if k in ("Type", "Grain"):
                w = ttk.Combobox(box, textvariable=self.fvars[k], width=width)
                self.fcombos[k] = w
            elif k == "Use":
                w = ttk.Combobox(box, textvariable=self.fvars[k], width=width, values=["Any", "Yes", "No"],
                                 state="readonly")
            else:
                w = ttk.Entry(box, textvariable=self.fvars[k], width=width)
            w.grid(row=0, column=2 * i + 1)
            w.bind("<Return>", lambda e: self.refresh())
            self.attach_help(w, self.name, "Filter" + k)
        btns = ttk.Frame(box)
        btns.grid(row=1, column=0, columnspan=16, sticky="w", pady=4)
        for label, cmd in (("Apply Filter", self.refresh), ("Clear Filter", self.clear_filter),
                           ("Select All Shown", self.select_all), ("Select Highlighted", self.select_highlighted),
                           ("Invert Selection", self.invert_selection)):
            b = ttk.Button(btns, text=label, command=cmd); b.pack(side="left", padx=2)
            self.attach_help(b, self.name, label)
        self.shown = ttk.Label(btns, text="")
        self.shown.pack(side="left", padx=8)
        self.shown_count = 0

    def build_save_set(self):
        box = ttk.LabelFrame(self, text="Save Selection")
        box.pack(fill="x", padx=8, pady=4)
        ttk.Label(box, text="TITLE").grid(row=0, column=0, padx=(6, 2), pady=4)
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
                                            ("Remove From Selection", self.remove_from_named)), start=2):
            b = ttk.Button(named, text=label, command=cmd)
            b.grid(row=0, column=col, padx=6)
            self.attach_help(b, self.name, label)
        self.refresh_sets()

    def refresh_sets(self):
        self.named_sets = {f"{s['ID']} - {s['TITLE']}": s["ID"] for s in self.db.list("FABRICSET")}
        self.set_combo["values"] = list(self.named_sets)

    def chosen_set_id(self):
        set_id = self.named_sets.get(self.set_combo.get())
        if set_id is None:
            raise ValueError("Choose a named selection first")
        return set_id

    def add_to_named(self):
        try:
            set_id = self.chosen_set_id()
            if not self.selected:
                raise ValueError("Select at least one fabric record")
            self.db.change_fabric_set(set_id, self.selected, add=True)
        except ValueError as e:
            return messagebox.showerror("Add to Selection", str(e))
        messagebox.showinfo("Add to Selection", f"Added {len(self.selected)} fabric record(s).")

    def remove_from_named(self):
        try:
            set_id = self.chosen_set_id()
            if not self.selected:
                raise ValueError("Select at least one fabric record")
            self.db.change_fabric_set(set_id, self.selected, add=False)
        except ValueError as e:
            return messagebox.showerror("Remove From Selection", str(e))
        messagebox.showinfo("Remove From Selection", f"Removed {len(self.selected)} fabric record(s).")

    def save_selection(self):
        try:
            self.db.save_fabric_set(self.set_title.get(), self.selected)
        except ValueError as e:
            return messagebox.showerror("Save Selection", str(e))
        self.set_title.set("")
        self.refresh_sets()
        messagebox.showinfo("Save Selection", f"Saved {len(self.selected)} fabric record(s).")

    def clear_filter(self):
        for k, v in self.fvars.items():
            v.set("Any" if k == "Use" else "")
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
        use = {"Any": None, "Yes": True, "No": False}[self.fvars["Use"].get()]
        return dict(name=self.fvars["Name"].get().strip(), type_=self.fvars["Type"].get().strip(),
                    grain=self.fvars["Grain"].get().strip(), length_min=num("LengthMin"),
                    length_max=num("LengthMax"), width_min=num("WidthMin"), width_max=num("WidthMax"),
                    use=use)

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())
        self.selected = {int(i) for i in self.tree.get_children()}
        self.paint()

    def select_highlighted(self):
        if not self.sels:
            return
        self.selected &= set(self.sels)
        self.paint()

    def invert_selection(self):
        self.selected = {int(i) for i in self.tree.get_children()} - self.selected
        self.paint()

    def paint(self):
        """Mark selected rows in the grid and show the selection count."""
        for iid in self.tree.get_children():
            self.tree.item(iid, tags=("chosen",) if int(iid) in self.selected else ())
        self.shown.config(text=f"{self.shown_count} shown, {len(self.selected)} selected")

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
        rows = self.db.list(self.name)
        if self.name == "Fabric":
            self.selected &= {r["ID"] for r in rows}   # drop deleted records from the selection
            self.refresh_sets()
            for k, w in self.fcombos.items():
                w["values"] = [""] + self.db.dropdown("Fabric", k)[0]
            try:
                rows = filter_fabric(rows, **self.filter_criteria())
            except ValueError as e:
                messagebox.showerror("Filter", str(e))
            self.shown_count = len(rows)
        for r in sort_rows(self.name, rows):
            self.tree.insert("", "end", iid=str(r["ID"]), values=[r[c.upper()] for c in FIELDS[self.name]],
                             tags=("chosen",) if r["ID"] in self.selected else ())
        if self.name == "Fabric":
            self.paint()
        self.sel, self.sels = None, []
        for f in self.fields:   # first-show defaults
            if not self.vars[f].get() and f not in BOOL and (self.name, f) in STATIC:
                self.apply_default(f)

    def apply_default(self, f):
        _, d, err = self.db.dropdown(*STATIC[(self.name, f)])
        if err:
            messagebox.showerror("Dropdown default", err)
        self.vars[f].set(d or "")

    def clear(self):
        self.sel, self.sels = None, []
        self.tree.selection_set(())
        for f in self.fields:
            if f in BOOL:
                self.vars[f].set(True)
            elif (self.name, f) in STATIC:
                self.apply_default(f)
            else:
                self.vars[f].set("")

    def select(self, _):
        self.sels = [int(i) for i in self.tree.selection()]
        if not self.sels:
            self.sel = None
            return
        rows = {r["ID"]: r for r in self.db.list(self.name)}
        chosen = [rows[i] for i in self.sels if i in rows]
        self.sel = self.sels[0] if len(self.sels) == 1 else None
        for f in self.fields:
            vals = {r[f.upper()] for r in chosen}
            v = vals.pop() if len(vals) == 1 else None   # differing values show blank in a group
            if f in BOOL:
                self.vars[f].set(bool(v) if v is not None else True)
            else:
                self.vars[f].set("" if v is None else v)
        self.initial = {f: self.vars[f].get() for f in self.fields}

    def values(self, only=None):
        out = {}
        for f in self.fields:
            if only is not None and f not in only:
                continue
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
        self.sel, self.sels = None, []
        self.refresh()

    def add(self):
        try:
            self.db.add(self.name, **self.values())
        except (ValueError, Exception) as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def update(self):
        if not self.sels:
            return messagebox.showinfo("Update", "Select a row first.")
        group = len(self.sels) > 1
        try:
            if group:
                changed = [f for f in self.fields if self.vars[f].get() != self.initial.get(f)]
                if not changed:
                    return messagebox.showinfo("Update", "No fields were changed.")
                vals = self.values(only=changed)
                if not messagebox.askyesno("Update group", f"Change {', '.join(changed)} on "
                                           f"{len(self.sels)} records?"):
                    return
                self.db.update_many(self.name, self.sels, **vals)
            else:
                self.db.update(self.name, self.sels[0], **self.values())
        except Exception as e:
            return messagebox.showerror("Error", str(e))
        self.after_save()

    def delete(self):
        n = len(self.sels)
        if n and messagebox.askyesno("Delete", "Delete selected record?" if n == 1 else f"Delete {n} selected records?"):
            self.db.delete_many(self.name, self.sels); self.after_save()


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
            Tip(e, self.db.helptext("Panel", k)[0])
            e.bind("<F1>", lambda ev, k=k: messagebox.showinfo(k, self.db.helptext("Panel", k)[1] or "No help."))
        ttk.Label(top, text=PANEL_SELECTION_FIELD).grid(row=1, column=0, pady=(6, 0))
        self.set_ids = {}
        self.sel_var = tk.StringVar(value=ALL_FABRICS)
        self.sel_box = ttk.Combobox(top, textvariable=self.sel_var, state="readonly", width=40)
        self.sel_box.grid(row=1, column=1, columnspan=8, sticky="w", padx=4, pady=(6, 0))
        Tip(self.sel_box, self.db.helptext("Panel", PANEL_SELECTION_FIELD)[0])
        self.sel_box.bind("<F1>", lambda ev: messagebox.showinfo(PANEL_SELECTION_FIELD, self.db.helptext("Panel", PANEL_SELECTION_FIELD)[1] or "No help."))
        ttk.Label(top, text=PANEL_CASE_FIELD).grid(row=2, column=0, pady=(6, 0))
        case_row = ttk.Frame(top); case_row.grid(row=2, column=1, columnspan=8, sticky="w", padx=4, pady=(6, 0))
        self.case_var = tk.StringVar(value=PANEL_CASES[0])
        self.case_btns = {}
        for c in PANEL_CASES:
            rb = ttk.Radiobutton(case_row, text=c, value=c, variable=self.case_var, command=self.switch_case)
            rb.pack(side="left", padx=4)
            rb.state(["disabled"])
            Tip(rb, self.db.helptext("Panel", c)[0])
            rb.bind("<F1>", lambda ev, c=c: messagebox.showinfo(c, self.db.helptext("Panel", c)[1] or "No help."))
            self.case_btns[c] = rb
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8)
        for label, cmd in (("Build Plan", self.build), ("Save Plan", self.save), ("Approve Plan", self.approve),
                           ("Print Plan", self.print)):
            b = ttk.Button(bar, text=label, command=cmd); b.pack(side="left", padx=2)
            Tip(b, self.db.helptext("Panel", label)[0])
            b.bind("<F1>", lambda e, label=label: messagebox.showinfo(label, self.db.helptext("Panel", label)[1] or "No help."))
        self.bind_errors = binding_errors("Panel", {k: (self.entries.get(k), self.v.get(k)) for k in self.v})
        if self.bind_errors:
            messagebox.showerror("Binding error", "\n".join(self.bind_errors))
        self.text = tk.Text(self, height=8); self.text.pack(fill="x", padx=8, pady=4)
        self.canvas = tk.Canvas(self, width=500, height=400, bg="white"); self.canvas.pack(padx=8, pady=4)

    def refresh(self):
        self.set_ids = {f"{s['ID']} - {s['TITLE']}": s["ID"] for s in self.db.list("FABRICSET")}
        self.sel_box["values"] = [ALL_FABRICS] + list(self.set_ids)
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
            fabrics = self.db.fabrics_in_set(self.set_ids[chosen]) if chosen in self.set_ids else self.db.list("FABRIC")
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
            c.create_text(x0 + part["w"] * s / 2, y0 + part["h"] * s / 2, text=part_label(part), width=part["w"] * s - 4, justify="center")

    def save(self):
        if not self.plan:
            return messagebox.showinfo("Save", "Build a plan first, or choose a case that is possible.")
        pid = self.db.add("PANEL", PANELNAME=self.plan["panel"], SEAMALLOWANCE=self.plan["seam_allowance"],
                          LENGTH=self.plan["length"], WIDTH=self.plan["width"])
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
            Tip(b, self.db.helptext(NAV_RECORD, n)[0])
            b.bind("<F1>", lambda e, n=n: messagebox.showinfo(n, self.db.helptext(NAV_RECORD, n)[1] or "No help."))
        file_cmds = {"Export CSV": self.export_csv, "Import CSV": self.import_csv, "User Manual": self.show_manual}
        for label in FILE_BUTTONS:
            cmd = file_cmds[label]
            b = ttk.Button(nav, text=label, command=cmd); b.pack(side="right", padx=2, pady=2)
            Tip(b, self.db.helptext(NAV_RECORD, label)[0])
            b.bind("<F1>", lambda e, n=label: messagebox.showinfo(n, self.db.helptext(NAV_RECORD, n)[1] or "No help."))
        self.show("Fabric")

    def show_manual(self):
        hover, full = self.db.helptext(NAV_RECORD, "User Manual")
        heading = hover or "User Manual"
        win = tk.Toplevel(self)
        win.title("User Manual")
        win.geometry("720x600")
        ttk.Label(win, text=heading, font=("TkDefaultFont", 14, "bold"), wraplength=680).pack(anchor="w", padx=12, pady=(12, 6))
        holder = ttk.Frame(win); holder.pack(fill="both", expand=True, padx=12)
        vsb = ttk.Scrollbar(holder, orient="vertical"); vsb.pack(side="right", fill="y")
        text = tk.Text(holder, wrap="word", yscrollcommand=vsb.set)
        text.insert("1.0", full or "No help.")
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
        folder = filedialog.askdirectory(title="Export all records to folder")
        if not folder:
            return
        try:
            files = self.db.export_csv(folder)
        except OSError as e:
            return messagebox.showerror("Export CSV", str(e))
        messagebox.showinfo("Export CSV", f"Exported {len(files)} tables to:\n{folder}")

    def import_csv(self):
        folder = filedialog.askdirectory(title="Import records from folder")
        if not folder:
            return
        if not messagebox.askyesno("Import CSV", "Rows whose ID already exists will be overwritten. Continue?"):
            return
        try:
            summary = self.db.import_csv(folder)
        except (OSError, ValueError, sqlite3.Error) as e:
            return messagebox.showerror("Import CSV", str(e))
        for f in self.forms.values():
            f.refresh()
        lines = [f"{'Table':<10}{'Input':>8}{'Added':>8}{'Modified':>10}"]
        for t, s in summary.items():
            if s["found"]:
                lines.append(f"{t:<10}{s['input']:>8}{s['added']:>8}{s['modified']:>10}")
            else:
                lines.append(f"{t:<10}  no file, skipped")
        messagebox.showinfo("Import CSV", "\n".join(lines))

    def show(self, name):
        for f in self.forms.values():
            f.pack_forget()
        self.forms[name].refresh(); self.forms[name].pack(fill="both", expand=True)


if __name__ == "__main__":
    App().mainloop()
