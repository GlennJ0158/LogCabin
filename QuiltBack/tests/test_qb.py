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
        f.vars["FullHelp"].set("line1\nline2")
        self.assertEqual(f.values()["FULLHELP"], "line1\nline2")
        root.destroy()


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
