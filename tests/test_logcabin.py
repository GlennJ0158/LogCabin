import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logcabin  # noqa: E402
from db import DB, LOG_FIELDS, helptext_pairs  # noqa: E402
from utilfuncs.validation import ValidationError  # noqa: E402

CLASSIC_HEADER = {"PatternName": "Classic Log Cabin", "Variation": "Classic", "CentreSize": 2.5,
                  "CentreColor": "Red", "SeamAllowance": 0.25}


def classic_strips():
    return logcabin.generate_strips("Classic", 1.25, 4)


class GeometryTests(unittest.TestCase):
    def test_classic_ring_order(self):
        self.assertEqual(logcabin.ring_sides("Classic", 1),
                         [("Right", "Dark"), ("Bottom", "Dark"), ("Left", "Light"), ("Top", "Light")])

    def test_classic_block_is_square_and_grows_by_two_widths_per_ring(self):
        plan = logcabin.cut_list(CLASSIC_HEADER, classic_strips())
        self.assertEqual(plan["block"], 12.5)   # 2.5 + 4 rings x 2 x 1.25
        self.assertEqual(len(plan["strips"]), 16)

    def test_first_strip_length_matches_centre_height(self):
        placed, bw, bh = logcabin.place(2.5, classic_strips())
        self.assertEqual((placed[0]["Length"], placed[1]["Length"]), (2.5, 3.75))
        self.assertEqual((bw, bh), (12.5, 12.5))

    def test_cut_sizes_add_seam_on_every_edge(self):
        plan = logcabin.cut_list(CLASSIC_HEADER, classic_strips())
        self.assertEqual(plan["centre_cut"], 3.0)
        self.assertEqual(plan["strips"][0]["CutWidth"], 1.75)
        self.assertEqual(plan["strips"][0]["CutLength"], 3.0)

    def test_quilt_totals(self):
        q = logcabin.quilt(logcabin.cut_list(CLASSIC_HEADER, classic_strips()), 4, 4)
        self.assertEqual((q["blocks"], q["width"], q["height"]), (16, 50.0, 50.0))
        self.assertEqual(q["centre_squares"], 16)

    def test_quilt_rejects_bad_counts(self):
        plan = logcabin.cut_list(CLASSIC_HEADER, classic_strips())
        with self.assertRaises(ValidationError):
            logcabin.quilt(plan, 0, 4)
        with self.assertRaises(ValidationError):
            logcabin.quilt(plan, 2.5, 4)

    def test_other_variation_has_no_generated_rings(self):
        with self.assertRaises(ValidationError):
            logcabin.generate_strips("Other", 1, 2)


class ValidationTests(unittest.TestCase):
    def test_non_square_block_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "not a square"):
            logcabin.validate(CLASSIC_HEADER, classic_strips()[:3])

    def test_bad_side_and_zero_width_are_named(self):
        with self.assertRaisesRegex(ValidationError, "Strip 1 Side"):
            logcabin.validate(CLASSIC_HEADER, [{"Side": "Up", "Color": "Dark", "Width": 1}])
        with self.assertRaisesRegex(ValidationError, "Strip 1 Width"):
            logcabin.validate(CLASSIC_HEADER, [{"Side": "Right", "Color": "Dark", "Width": 0}])

    def test_valid_classic_passes(self):
        header, strips = logcabin.validate(CLASSIC_HEADER, classic_strips())
        self.assertEqual(len(strips), 16)


class LogDBTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = DB(os.path.join(self.dir.name, "t.db"))

    def tearDown(self):
        self.db.c.close()
        self.dir.cleanup()

    def test_classic_round_trip(self):
        pid = self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())
        header, strips = self.db.log_pattern(pid)
        self.assertEqual(header["PatternName"], "Classic Log Cabin")
        self.assertEqual(len(strips), 16)
        self.assertEqual(strips[0], {"Side": "Right", "Color": "Dark", "Width": 1.25})
        self.assertEqual(self.db.log_patterns()[0]["Strips"], 16)

    def test_update_replaces_strips(self):
        pid = self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())
        self.db.save_log_pattern(pid, CLASSIC_HEADER, classic_strips()[:4])
        self.assertEqual(len(self.db.log_pattern(pid)[1]), 4)

    def test_duplicate_name_is_rejected(self):
        self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())
        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())

    def test_delete_removes_strips(self):
        pid = self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())
        self.db.delete_log_pattern(pid)
        self.assertEqual(self.db.c.execute("SELECT COUNT(*) FROM LogStrip").fetchone()[0], 0)

    def test_invalid_pattern_saves_nothing(self):
        with self.assertRaises(ValidationError):
            self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips()[:3])
        self.assertEqual(self.db.log_patterns(), [])

    def test_dropdown_lists_seeded(self):
        self.assertIn("Reverse Classic", self.db.log_choices("LogPattern", "Variation"))
        self.assertEqual(self.db.log_default("LogPattern", "Variation"), "Classic")

    def test_every_log_field_has_helptext_pair(self):
        pairs = set(helptext_pairs())
        for f in LOG_FIELDS:
            self.assertIn(("LogCabin", f), pairs)


if __name__ == "__main__":
    unittest.main()
