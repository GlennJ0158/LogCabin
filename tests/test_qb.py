import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import DB
from planner import plan_panel


class RecordFormText(unittest.TestCase):
    def test_fullhelp_multiline_roundtrip(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("tkinter unavailable")
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        from app import RecordForm
        class A: pass
        a = A(); a.db = DB(":memory:"); a.body = root
        f = RecordForm(a, "Helptext")
        self.assertIsInstance(f.widgets["FullHelp"], tk.Text)
        f.vars["RecordName"].set("Fabric"); f.vars["FieldName"].set("Name")
        f.vars["FullHelp"].set("line1\nline2")
        self.assertEqual(f.values()["FULLHELP"], "line1\nline2")
        root.destroy()


class BindingTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
        except Exception:
            self.skipTest("tkinter/display unavailable")
        self.tk = tk
        self.errors = []
        import app
        self.app_mod = app
        self._orig = app.messagebox.showerror
        app.messagebox.showerror = lambda t, m, **k: self.errors.append((t, m))

    def tearDown(self):
        self.app_mod.messagebox.showerror = self._orig
        self.root.destroy()

    def make(self, name):
        class A: pass
        a = A(); a.db = DB(":memory:"); a.body = self.root
        return self.app_mod.RecordForm(a, name)

    def test_every_record_field_is_bound_to_typed_input(self):
        from tkinter import ttk
        for name in ("Fabric", "Dropdown", "Helptext"):
            f = self.make(name)
            self.assertEqual(f.bind_errors, [], name)
            for fld, w in f.widgets.items():
                if isinstance(w, ttk.Checkbutton):
                    w.invoke()
                    self.assertFalse(f.vars[fld].get(), f"{name}.{fld}")
                elif isinstance(w, self.tk.Text):
                    w.insert("1.0", "typed?")
                    self.assertEqual(f.vars[fld].get(), "typed?", f"{name}.{fld}")
                else:
                    w.delete(0, "end"); w.insert(0, "5" if fld in ("Length", "Width") else "typed?")
                    self.assertEqual(f.vars[fld].get(), w.get(), f"{name}.{fld}")
                    self.assertEqual(f.vars[fld].get(), "5" if fld in ("Length", "Width") else "typed?")
        self.assertEqual(self.errors, [])

    def test_fabric_name_and_hover_text_reach_values(self):
        f = self.make("Fabric")
        f.widgets["Name"].insert(0, "Rose?"); f.widgets["Length"].insert(0, "3"); f.widgets["Width"].insert(0, "2")
        self.assertEqual(f.values()["NAME"], "Rose?")
        h = self.make("Helptext")
        h.widgets["RecordName"].set("Fabric"); h.widgets["FieldName"].set("Name")
        h.widgets["HoverText"].insert(0, "Hover?")
        self.assertEqual(h.values()["HOVERTEXT"], "Hover?")

    def test_unbound_widget_is_reported(self):
        from tkinter import ttk
        v = self.tk.StringVar(); w = ttk.Entry(self.root)
        errs = self.app_mod.binding_errors("X", {"F": (w, v)})
        self.assertEqual(len(errs), 1)
        self.assertTrue(self.app_mod.binding_errors("X", {"F": (None, v)}))

    def test_bad_number_gives_error_message(self):
        f = self.make("Fabric")
        f.widgets["Name"].insert(0, "a"); f.widgets["Length"].insert(0, "abc"); f.widgets["Width"].insert(0, "2")
        with self.assertRaisesRegex(ValueError, "Length must be a number"):
            f.values()

    def test_panel_fields_bound(self):
        a = type("A", (), {})(); a.db = DB(":memory:"); a.body = self.root
        p = self.app_mod.PanelForm(a)
        self.assertEqual(p.bind_errors, [])
        for k, e in p.entries.items():
            e.delete(0, "end"); e.insert(0, "7")
            self.assertEqual(p.v[k].get(), "7", k)
        self.assertEqual(self.errors, [])


class GroupTests(BindingTests):
    def setUp(self):
        super().setUp()
        self.form = self.make("Fabric")
        for n, t, l, w in (("Red", "Cotton", 5, 10), ("Blue", "Linen", 8, 10), ("Redwood", "Cotton", 12, 20)):
            self.form.db.add("FABRIC", NAME=n, TYPE=t, LENGTH=l, WIDTH=w)
        self.form.refresh()

    def test_length_width_retained_after_add(self):
        self.form.vars["Name"].set("New"); self.form.vars["Length"].set("7"); self.form.vars["Width"].set("9")
        self.form.add()
        self.assertEqual(self.form.vars["Length"].get(), "7")
        self.assertEqual(self.form.vars["Width"].get(), "9")
        self.assertEqual(self.form.vars["Name"].get(), "")

    def test_filter_and_select_all_shown(self):
        self.form.fvars["Name"].set("red")
        self.form.refresh()
        self.assertEqual(len(self.form.tree.get_children()), 2)
        self.form.select_all()
        self.root.update()
        self.assertEqual(len(self.form.sels), 2)

    def test_noncontiguous_selection_group_update_and_delete(self):
        self.form.tree.selection_set(("1", "3"))
        self.form.tree.update()
        self.form.select(None)
        self.assertEqual(self.form.vars["Type"].get(), "Cotton")
        self.assertEqual(self.form.vars["Name"].get(), "")
        self.form.vars["Grain"].set("Bias")
        orig = self.app_mod.messagebox.askyesno
        self.app_mod.messagebox.askyesno = lambda *a, **k: True
        try:
            self.form.update()
            rows = {r["ID"]: r for r in self.form.db.list("FABRIC")}
            self.assertEqual([rows[i]["GRAIN"] for i in (1, 2, 3)], ["Bias", None, "Bias"])
            self.assertEqual(rows[1]["NAME"], "Red")
            self.form.tree.selection_set(("1", "3"))
            self.form.select(None)
            self.form.delete()
        finally:
            self.app_mod.messagebox.askyesno = orig
        self.assertEqual([r["ID"] for r in self.form.db.list("FABRIC")], [2])


class FilterTests(unittest.TestCase):
    def test_filter_fabric(self):
        from db import filter_fabric
        db = DB(":memory:")
        db.add("FABRIC", NAME="Red", TYPE="Cotton", LENGTH=5, WIDTH=10)
        db.add("FABRIC", NAME="Blue", TYPE="Linen", LENGTH=8, WIDTH=10, USE=0)
        rows = db.list("FABRIC")
        self.assertEqual(len(filter_fabric(rows, type_="cotton")), 1)
        self.assertEqual(len(filter_fabric(rows, length_min=6)), 1)
        self.assertEqual(len(filter_fabric(rows, use=False)), 1)
        self.assertEqual(len(filter_fabric(rows)), 2)


class T(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def test_dropdown_defaults(self):
        vals, d, e = self.db.dropdown("Fabric", "Type")
        self.assertIn("Cotton", vals); self.assertIsNone(d); self.assertIsNone(e)
        self.db.add("DROPDOWN", RECORDNAME="Fabric", FIELDNAME="Type", VALUE="X", DEF=1)
        self.db.add("DROPDOWN", RECORDNAME="Fabric", FIELDNAME="Type", VALUE="Y", DEF=1)
        _, d, e = self.db.dropdown("Fabric", "Type")
        self.assertEqual(d, "Y"); self.assertTrue(e)

    def test_fabric_name_and_hover_text_keep_question_marks(self):
        name = "What's this?"
        hover = "Is this fabric right?"
        self.db.add("FABRIC", NAME=name, LENGTH=5, WIDTH=4)
        self.db.add("HELPTEXT", RECORDNAME="Fabric", FIELDNAME="Name", HOVERTEXT=hover)

        self.assertEqual(self.db.list("FABRIC")[-1]["NAME"], name)
        self.assertEqual(self.db.helptext("Fabric", "Name")[0], hover)

    def test_plan_and_approve(self):
        a = self.db.add("FABRIC", NAME="a", LENGTH=20, WIDTH=20)
        self.db.add("FABRIC", NAME="b", LENGTH=3, WIDTH=3)
        panel = dict(PANELNAME="p", SEAMALLOWANCE=.25, LENGTH=10, WIDTH=10)
        plan = plan_panel(panel, self.db.list("FABRIC"))
        self.assertEqual(plan["seams"], 0)
        pid = self.db.save_plan(1, plan)
        self.db.approve_plan(pid)
        f = [x for x in self.db.list("FABRIC") if x["ID"] == a][0]
        self.assertEqual(f["LENGTH"], 9.5)
        with self.assertRaises(ValueError):
            self.db.approve_plan(pid)

    def test_seams(self):
        self.db.add("FABRIC", NAME="a", LENGTH=6, WIDTH=12)
        self.db.add("FABRIC", NAME="b", LENGTH=6, WIDTH=12)
        plan = plan_panel(dict(PANELNAME="p", SEAMALLOWANCE=.25, LENGTH=10, WIDTH=10), self.db.list("FABRIC"))
        self.assertEqual(plan["seams"], 1)
        self.assertEqual(len(plan["cuts"]), 2)

    def test_impossible(self):
        with self.assertRaises(ValueError):
            plan_panel(dict(PANELNAME="p", SEAMALLOWANCE=.25, LENGTH=10, WIDTH=10), [])

if __name__ == "__main__":
    unittest.main()
