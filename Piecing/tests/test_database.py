import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Inventory, ValidationError  # noqa: E402
from printing import render_html  # noqa: E402


def item(**kw):
    d = dict(ID="A1", NAME="Kona", TYPE="Cotton", COLOR="Red", LENGTH="10", WIDTH="5", GRAIN="bias")
    d.update(kw)
    return d


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.inv = Inventory(":memory:")

    def test_add_get_update_delete(self):
        self.inv.add(item())
        self.assertEqual(self.inv.get("A1")["GRAIN"], "Bias")
        self.inv.update("A1", item(ID="A2", NAME="New"))
        self.assertIsNone(self.inv.get("A1"))
        self.assertEqual(self.inv.get("A2")["NAME"], "New")
        self.inv.delete("A2")
        self.assertEqual(self.inv.list(), [])

    def test_validation(self):
        for bad in (item(NAME=""), item(LENGTH="abc"), item(WIDTH="0"), item(GRAIN="x"), item(LENGTH="nan")):
            with self.assertRaises(ValidationError):
                self.inv.add(bad)
        self.inv.add(item())
        with self.assertRaises(ValidationError):
            self.inv.add(item())

    def test_multi_sort_and_search(self):
        self.inv.add(item(ID="1", COLOR="Red", LENGTH="2"))
        self.inv.add(item(ID="2", COLOR="Blue", LENGTH="10"))
        self.inv.add(item(ID="3", COLOR="Red", LENGTH="30"))
        ids = [r["ID"] for r in self.inv.list([("COLOR", False), ("LENGTH", True)])]
        self.assertEqual(ids, ["2", "3", "1"])
        self.assertEqual(len(self.inv.list(search="blue")), 1)
        self.assertEqual(self.inv.list(search="%"), [])

    def test_next_id_and_html(self):
        self.assertEqual(self.inv.next_id(), "F0001")
        self.inv.add(item(NAME="<b>"))
        self.assertIn("&lt;b&gt;", render_html(self.inv.list()))


if __name__ == "__main__":
    unittest.main()
