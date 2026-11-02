import os
import tempfile
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import DB, FIELDS, COLUMNS, sort_rows, helptext_pairs  # noqa: E402
from planner import plan_cases, cut_list, part_label  # noqa: E402


def panel(**kw):
    base = {"PANELNAME": "Panel", "SEAMALLOWANCE": 0.25, "LENGTH": 10, "WIDTH": 8, "MAXPARTS": 4}
    base.update(kw)
    return base


class DBTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.db = DB(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def add_fabric(self, name="Red", length=40, width=20, color="Red", use=1, pattern=""):
        return self.db.add("Fabric", {"FabricName": name, "Length": length, "Width": width,
                                      "Color": color, "Shade": "", "Pattern": pattern, "Type": "",
                                      "Grain": "", "Use": use})

    def test_schema_has_utilfuncs_tables(self):
        con = sqlite3.connect(self.path)
        names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        con.close()
        self.assertTrue({"Fabric", "DropDown", "HelpText", "Selection", "SelectedRows"} <= names)

    def test_add_list_update_delete(self):
        fid = self.add_fabric()
        self.assertEqual(len(self.db.list("Fabric")), 1)
        self.db.update_many("Fabric", [fid], {"Length": 50})
        self.assertEqual(self.db.list("Fabric")[0]["Length"], 50)
        self.db.delete_many("Fabric", [fid])
        self.assertEqual(self.db.list("Fabric"), [])

    def test_filter_by_name_length_and_use(self):
        a = self.add_fabric("Red cotton", 40, 20, use=1)
        self.add_fabric("Blue silk", 10, 5, color="Blue", use=0)
        self.assertEqual([r["ID"] for r in self.db.filter_fabric(name="cotton")], [a])
        self.assertEqual(len(self.db.filter_fabric(length=(None, 20))), 1)
        self.assertEqual(len(self.db.filter_fabric(use=0)), 1)

    def test_selection_save_change_and_activate(self):
        a = self.add_fabric("A")
        b = self.add_fabric("B")
        self.db.save_selection("Reds", {a})
        self.assertIn("Reds", self.db.selection_names())
        self.assertEqual(set(self.db.selection_ids("Reds")), {a})
        self.db.change_selection("Reds", {b}, add=True)
        self.assertEqual(set(self.db.selection_ids("Reds")), {a, b})
        self.db.change_selection("Reds", {a}, add=False)
        self.assertEqual(set(self.db.selection_ids("Reds")), {b})

    def test_duplicate_selection_title_rejected(self):
        a = self.add_fabric()
        self.db.save_selection("Dup", {a})
        with self.assertRaises((ValueError, sqlite3.Error)):
            self.db.save_selection("Dup", {a})

    def test_plan_save_and_approve_reduces_inventory(self):
        self.add_fabric("Big", length=40, width=40)
        plan = plan_cases(panel(), self.db.list("Fabric"))["symmetric"]
        self.assertIsNotNone(plan)
        pid = self.db.add_panel(plan["panel"], plan["seam_allowance"], plan["length"], plan["width"])
        plan_id = self.db.save_plan(pid, plan)
        self.db.approve_plan(plan_id)
        left = self.db.list("Fabric")
        self.assertEqual(len(left), 1)
        self.assertLess(left[0]["Length"], 40)

    def test_csv_round_trip_keeps_commas_and_quotes(self):
        fid = self.add_fabric('Red, cotton; "dotted"')
        self.db.update_many("Fabric", [fid], {"Pattern": "Floral"})
        csv_path = os.path.join(self.dir.name, "all.csv")
        counts = self.db.export_csv(csv_path)
        self.assertGreaterEqual(counts["Fabric"], 1)
        fresh = DB(os.path.join(self.dir.name, "fresh.db"))
        fresh.import_csv(csv_path)
        row = fresh.list("Fabric")[0]
        self.assertEqual(row["FabricName"], 'Red, cotton; "dotted"')
        self.assertEqual(row["Pattern"], "Floral")
        fresh.import_csv(csv_path)   # re-import is an upsert by ID
        self.assertEqual(len(fresh.list("Fabric")), 1)

    def test_helptext_lookup_for_every_key(self):
        for record, field in helptext_pairs():
            hover, full = self.db.helptext(record, field)
            self.assertTrue(hover, f"no hover text for {record}.{field}")


class PlannerTests(unittest.TestCase):
    def test_symmetric_plan_fits_panel(self):
        fabrics = [{"ID": 1, "FabricName": "A", "Length": 40, "Width": 40, "Color": "Red", "Shade": "",
                    "Pattern": "", "Type": "", "Grain": "", "Use": 1}]
        plan = plan_cases(panel(), fabrics)["symmetric"]
        self.assertIsNotNone(plan)
        self.assertTrue(cut_list(plan))
        for part in plan["parts"]:
            self.assertTrue(part_label(part))

    def test_no_inventory_gives_no_plan(self):
        self.assertFalse(any(plan_cases(panel(), []).values()))


class GuiTests(unittest.TestCase):
    """Constructs the Tk app. Needs a display; on Linux run with xvfb-run."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.destroy()

    def test_app_builds_and_every_form_is_bound(self):
        import app as qb
        from tkinter import messagebox
        cwd = os.getcwd()
        shown = []
        orig = messagebox.showerror
        messagebox.showerror = lambda *a, **k: shown.append(a)
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                win = qb.App()
                win.update()
                for name, form in win.forms.items():
                    self.assertEqual(getattr(form, "bind_errors", []), [], name)
                fabric = win.forms["Fabric"]
                fabric.vars["FabricName"].set("Test")
                fabric.vars["Length"].set("10")
                fabric.vars["Width"].set("5")
                fabric.add()
                self.assertEqual(fabric.shown_count, 1)
                win.destroy()
            finally:
                messagebox.showerror = orig
                os.chdir(cwd)
        self.assertEqual(shown, [])

    def test_sort_rows_orders_by_id(self):
        base = {"FabricName": "x", "Color": None, "Shade": None, "Pattern": None, "Type": None,
                "Grain": None, "SqIn": 0, "Use": 1, "Length": 1, "Width": 1}
        rows = sort_rows("Fabric", [dict(base, ID=2), dict(base, ID=1)])
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
