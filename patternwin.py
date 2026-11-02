"""Separate window to define, save and load Log Cabin patterns. All dimensions are in inches."""
import tkinter as tk
from tkinter import messagebox, ttk

import logcabin
from db import LOG_RECORD
from tooltip import Tip

HEADER_FIELDS = ["PatternName", "Variation", "CentreSize", "CentreColor", "SeamAllowance", "BlockWidth", "BlockLength"]
GEN_FIELDS = ["Rings", "StripWidth", "StripSide", "StripColor"]
QUILT_FIELDS = ["BlocksAcross", "BlocksDown"]


class LogCabinWindow(tk.Toplevel):
    def __init__(self, master, db):
        super().__init__(master)
        self.db = db
        self.title("Log Cabin Patterns")
        self.geometry("780x720")
        self.pattern_id = None
        self.strips = []
        self.vars = {f: tk.StringVar() for f in HEADER_FIELDS + GEN_FIELDS + QUILT_FIELDS}
        self.vars["SeamAllowance"].set(str(logcabin.DEFAULT_SEAM))
        self.vars["BlocksAcross"].set("4")
        self.vars["BlocksDown"].set("4")
        self.vars["StripSide"].set("Right")
        self.vars["StripColor"].set("Dark")
        self.vars["Variation"].set(self.db.log_default("LogPattern", "Variation") or "Classic")

        self._build_header()
        self._build_strips()
        self._build_saved()
        self._build_output()
        self.refresh_saved()

    # ----- layout -----
    def _tip(self, widget, label):
        hover, _ = self.db.helptext(LOG_RECORD, label)
        Tip(widget, hover)

    def _entry(self, parent, label, row, col, values=None, width=14):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="e", padx=4, pady=2)
        if values is None:
            w = ttk.Entry(parent, textvariable=self.vars[label], width=width)
        else:
            w = ttk.Combobox(parent, textvariable=self.vars[label], values=values, width=width, state="readonly")
        w.grid(row=row, column=col + 1, sticky="w", padx=4, pady=2)
        self._tip(w, label)
        return w

    def _button(self, parent, label, command, col):
        b = ttk.Button(parent, text=label, command=command)
        b.grid(row=0, column=col, padx=3, pady=3)
        self._tip(b, label)
        return b

    def _build_header(self):
        frm = ttk.LabelFrame(self, text="Pattern")
        frm.pack(fill="x", padx=6, pady=4)
        self._entry(frm, "PatternName", 0, 0, width=24)
        self._entry(frm, "Variation", 0, 2, values=self.db.log_choices("LogPattern", "Variation"), width=18)
        self._entry(frm, "CentreSize", 1, 0)
        self._entry(frm, "CentreColor", 1, 2)
        self._entry(frm, "SeamAllowance", 2, 0)
        self._entry(frm, "BlockWidth", 2, 2)
        self._entry(frm, "BlockLength", 3, 0)
        gen = ttk.LabelFrame(self, text="Generate rings (Classic, Reverse Classic, Courthouse Steps)")
        gen.pack(fill="x", padx=6, pady=4)
        self._entry(gen, "Rings", 0, 0)
        self._entry(gen, "StripWidth", 0, 2)
        self._button(gen, "Fill Strips", self.fill_strips, 4)

    def _build_strips(self):
        frm = ttk.LabelFrame(self, text="Strips (sewn in order around the centre square)")
        frm.pack(fill="both", expand=True, padx=6, pady=4)
        entry = ttk.Frame(frm)
        entry.pack(fill="x")
        self._entry(entry, "StripSide", 0, 0, values=self.db.log_choices("LogStrip", "Side"), width=10)
        self._entry(entry, "StripColor", 0, 2, values=self.db.log_choices("LogStrip", "Color"), width=10)
        self._entry(entry, "StripWidth", 0, 4, width=8)
        self._button(entry, "Add Strip", self.add_strip, 6)
        self._button(entry, "Remove Strip", self.remove_strip, 7)
        self._button(entry, "Move Up", lambda: self.move_strip(-1), 8)
        self._button(entry, "Move Down", lambda: self.move_strip(1), 9)
        self.strip_tree = ttk.Treeview(frm, columns=("No", "Side", "Color", "Width"), show="headings", height=7)
        for col, text in (("No", "Strip"), ("Side", "Side"), ("Color", "Color"), ("Width", "Width (in)")):
            self.strip_tree.heading(col, text=text)
            self.strip_tree.column(col, width=120, anchor="center")
        self.strip_tree.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_saved(self):
        frm = ttk.LabelFrame(self, text="Saved patterns")
        frm.pack(fill="x", padx=6, pady=4)
        buttons = ttk.Frame(frm)
        buttons.pack(fill="x")
        self._button(buttons, "Save Pattern", self.save, 0)
        self._button(buttons, "New Pattern", self.new, 1)
        self._button(buttons, "Load Pattern", self.load, 2)
        self._button(buttons, "Delete Pattern", self.delete, 3)
        self._button(buttons, "Show Cut List", self.show_cut_list, 4)
        self._button(buttons, "Quilt Summary", self.quilt_summary, 5)
        ttk.Label(buttons, text="Blocks across").grid(row=1, column=0, sticky="e")
        ttk.Entry(buttons, textvariable=self.vars["BlocksAcross"], width=6).grid(row=1, column=1, sticky="w")
        self._tip(buttons.grid_slaves(row=1, column=1)[0], "BlocksAcross")
        ttk.Label(buttons, text="Blocks down").grid(row=1, column=2, sticky="e")
        ttk.Entry(buttons, textvariable=self.vars["BlocksDown"], width=6).grid(row=1, column=3, sticky="w")
        self._tip(buttons.grid_slaves(row=1, column=3)[0], "BlocksDown")
        self.saved_tree = ttk.Treeview(frm, columns=("Name", "Variation", "Strips"), show="headings", height=5)
        for col, text in (("Name", "Pattern"), ("Variation", "Variation"), ("Strips", "Strips")):
            self.saved_tree.heading(col, text=text)
            self.saved_tree.column(col, width=200, anchor="w")
        self.saved_tree.pack(fill="x", padx=4, pady=4)

    def _build_output(self):
        frm = ttk.LabelFrame(self, text="Output (inches)")
        frm.pack(fill="both", expand=True, padx=6, pady=4)
        self.out = tk.Text(frm, height=10, state="disabled", wrap="word")
        self.out.pack(fill="both", expand=True, padx=4, pady=4)

    # ----- helpers -----
    def _write(self, text):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.configure(state="disabled")

    def _header(self):
        return {f: self.vars[f].get() for f in HEADER_FIELDS}

    def _checked(self):
        """Validated (header, strips); shows the error and returns None if the pattern is not valid."""
        try:
            return self.db.log_clean(self._header(), self.strips)
        except ValueError as e:
            messagebox.showerror("Log Cabin", str(e), parent=self)
            return None

    def _refresh_strips(self):
        self.strip_tree.delete(*self.strip_tree.get_children())
        for n, s in enumerate(self.strips, start=1):
            self.strip_tree.insert("", "end", iid=str(n - 1), values=(n, s["Side"], s["Color"], s["Width"]))

    def refresh_saved(self):
        self.saved_tree.delete(*self.saved_tree.get_children())
        for p in self.db.log_patterns():
            self.saved_tree.insert("", "end", iid=str(p["ID"]),
                                   values=(p["PatternName"], p["Variation"], p["Strips"]))

    def _selected_strip(self):
        sel = self.strip_tree.selection()
        return int(sel[0]) if sel else None

    # ----- strip editing -----
    def add_strip(self):
        try:
            row = logcabin.clean_strip({"Side": self.vars["StripSide"].get(),
                                        "Color": self.vars["StripColor"].get(),
                                        "Width": self.vars["StripWidth"].get()},
                                       self.db.log_choices("LogStrip", "Side"),
                                       self.db.log_choices("LogStrip", "Color"), label=f"Strip {len(self.strips) + 1}")
        except ValueError as e:
            messagebox.showerror("Log Cabin", str(e), parent=self)
            return
        self.strips.append(row)
        self._refresh_strips()

    def remove_strip(self):
        i = self._selected_strip()
        if i is None:
            return
        del self.strips[i]
        self._refresh_strips()

    def move_strip(self, delta):
        i = self._selected_strip()
        if i is None or not 0 <= i + delta < len(self.strips):
            return
        self.strips[i], self.strips[i + delta] = self.strips[i + delta], self.strips[i]
        self._refresh_strips()
        self.strip_tree.selection_set(str(i + delta))

    def fill_strips(self):
        try:
            self.strips = logcabin.generate_strips(self.vars["Variation"].get(), self.vars["StripWidth"].get(),
                                                   self.vars["Rings"].get())
        except ValueError as e:
            messagebox.showerror("Log Cabin", str(e), parent=self)
            return
        self._refresh_strips()

    # ----- saved patterns -----
    def _confirm_non_square(self, width, length):
        """Ask before saving a block that is not square. Returns (save, don't ask again)."""
        top = tk.Toplevel(self)
        top.title("Log Cabin")
        top.transient(self)
        ttk.Label(top, text=f"The block is {width} x {length} in, which is not square.\nSave it anyway?",
                  justify="left").pack(padx=12, pady=10)
        again = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Don't ask me again", variable=again).pack(padx=12)
        result = {"save": False, "again": False}

        def answer(save):
            result.update(save=save, again=again.get())
            top.destroy()

        buttons = ttk.Frame(top)
        buttons.pack(pady=10)
        ttk.Button(buttons, text="Save", command=lambda: answer(True)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=lambda: answer(False)).pack(side="left", padx=4)
        top.grab_set()
        top.wait_window()
        return result["save"], result["again"]

    def save(self):
        checked = self._checked()
        if checked is None:
            return
        header, _ = checked
        # Each save of a new or edited pattern asks about a non-square block; the choice is stored on that pattern.
        non_square_ok = False
        if header["BlockWidth"] != header["BlockLength"]:
            save, non_square_ok = self._confirm_non_square(header["BlockWidth"], header["BlockLength"])
            if not save:
                return
        try:
            self.pattern_id = self.db.save_log_pattern(self.pattern_id, *checked, non_square_ok=non_square_ok)
        except ValueError as e:
            messagebox.showerror("Log Cabin", str(e), parent=self)
            return
        self.refresh_saved()
        self.saved_tree.selection_set(str(self.pattern_id))
        messagebox.showinfo("Log Cabin", f"Saved '{header['PatternName']}'.", parent=self)

    def new(self):
        self.pattern_id = None
        self.strips = []
        self.vars["PatternName"].set("")
        self.vars["CentreSize"].set("")
        self.vars["CentreColor"].set("")
        self.vars["BlockWidth"].set("")
        self.vars["BlockLength"].set("")
        self._refresh_strips()
        self.saved_tree.selection_remove(self.saved_tree.selection())
        self._write("")

    def load(self):
        sel = self.saved_tree.selection()
        if not sel:
            messagebox.showinfo("Log Cabin", "Select a saved pattern to load.", parent=self)
            return
        header, strips = self.db.log_pattern(int(sel[0]))
        self.pattern_id = header["ID"]
        for f in HEADER_FIELDS:
            self.vars[f].set(str(header[f]) if header[f] is not None else "")
        self.strips = strips
        self._refresh_strips()
        self._write("")

    def delete(self):
        sel = self.saved_tree.selection()
        target = int(sel[0]) if sel else self.pattern_id
        if target is None:
            messagebox.showinfo("Log Cabin", "Select a saved pattern to delete.", parent=self)
            return
        if not messagebox.askyesno("Log Cabin", "Delete this pattern and its strips?", parent=self):
            return
        self.db.delete_log_pattern(target)
        if target == self.pattern_id:
            self.new()
        self.refresh_saved()

    # ----- output -----
    def show_cut_list(self):
        checked = self._checked()
        if checked is None:
            return
        header, strips = checked
        plan = logcabin.cut_list(header, strips)
        lines = [f"Block finished size: {plan['block_width']} x {plan['block_length']} in",
                 f"Centre square: {header['CentreSize']} in finished, cut {plan['centre_cut']} in ({header['CentreColor'] or 'any colour'})",
                 "", "Strip  Side    Colour  Finished (W x L)   Cut (W x L)"]
        for p in plan["strips"]:
            lines.append(f"{p['StripNo']:>5}  {p['Side']:<7} {p['Color']:<7} "
                         f"{p['Width']} x {p['Length']} in".ljust(52)
                         + f"{p['CutWidth']} x {p['CutLength']} in")
        self._write("\n".join(lines))

    def quilt_summary(self):
        checked = self._checked()
        if checked is None:
            return
        header, strips = checked
        try:
            q = logcabin.quilt(logcabin.cut_list(header, strips),
                               self.vars["BlocksAcross"].get(), self.vars["BlocksDown"].get())
        except ValueError as e:
            messagebox.showerror("Log Cabin", str(e), parent=self)
            return
        lines = [f"Quilt: {q['across']} x {q['down']} blocks ({q['blocks']} total)",
                 f"Finished size: {q['width']} x {q['height']} in",
                 f"Centre squares to cut: {q['centre_squares']} at {q['centre_cut']} in"]
        lines += [f"{colour} strips: {inches} in of fabric" for colour, inches in q["strip_inches"].items()]
        self._write("\n".join(lines))
