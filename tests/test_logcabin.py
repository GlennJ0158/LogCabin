import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logcabin  # noqa: E402
from db import DB, LOG_FIELDS, helptext_pairs  # noqa: E402
from utilfuncs.validation import ValidationError  # noqa: E402

CLASSIC_HEADER = {"PatternName": "Classic Log Cabin", "Variation": "Classic", "CentreSize": 2.5,
                  "CentreColor": "Red", "SeamAllowance": 0.25, "BlockWidth": 12.5, "BlockLength": 12.5}


def classic_strips():
    return logcabin.generate_strips("Classic", 1.25, 4)


class GeometryTests(unittest.TestCase):
    def test_classic_ring_order(self):
        self.assertEqual(logcabin.ring_sides("Classic", 1),
                         [("Right", "Dark"), ("Bottom", "Dark"), ("Left", "Light"), ("Top", "Light")])

    def test_classic_block_is_square_and_grows_by_two_widths_per_ring(self):
        plan = logcabin.cut_list(CLASSIC_HEADER, classic_strips())
        self.assertEqual((plan["block_width"], plan["block_length"]), (12.5, 12.5))   # 2.5 + 4 x 2 x 1.25
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

    def test_quilt_uses_block_width_and_length(self):
        strips = logcabin.generate_strips("Classic", 1.25, 4)[:3]
        q = logcabin.quilt(logcabin.cut_list(dict(CLASSIC_HEADER, BlockWidth=5, BlockLength=3.75), strips), 3, 2)
        self.assertEqual((q["width"], q["height"]), (15.0, 7.5))

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
    def test_non_square_block_is_accepted_when_size_matches(self):
        header = dict(CLASSIC_HEADER, BlockWidth=5, BlockLength=3.75)
        clean_header, strips = logcabin.validate(header, classic_strips()[:3])
        self.assertEqual((clean_header["BlockWidth"], clean_header["BlockLength"]), (5, 3.75))

    def test_strips_must_match_block_size(self):
        with self.assertRaisesRegex(ValidationError, "make a 5.0 x 3.75 in block"):
            logcabin.validate(CLASSIC_HEADER, classic_strips()[:3])

    def test_block_size_is_required_and_positive(self):
        with self.assertRaisesRegex(ValidationError, "BlockWidth"):
            logcabin.validate(dict(CLASSIC_HEADER, BlockWidth=""), classic_strips())
        with self.assertRaisesRegex(ValidationError, "BlockLength"):
            logcabin.validate(dict(CLASSIC_HEADER, BlockLength=0), classic_strips())

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
        self.assertEqual((header["BlockWidth"], header["BlockLength"]), (12.5, 12.5))
        self.assertEqual(len(strips), 16)
        self.assertEqual(strips[0], {"Side": "Right", "Color": "Dark", "Width": 1.25})
        self.assertEqual(self.db.log_patterns()[0]["Strips"], 16)

    def test_non_square_round_trip(self):
        header = dict(CLASSIC_HEADER, PatternName="Wide", BlockWidth=5, BlockLength=3.75)
        pid = self.db.save_log_pattern(None, header, classic_strips()[:3])
        saved = self.db.log_pattern(pid)[0]
        self.assertEqual((saved["BlockWidth"], saved["BlockLength"]), (5, 3.75))

    def test_non_square_choice_is_stored_per_pattern(self):
        header = dict(CLASSIC_HEADER, BlockWidth=5, BlockLength=3.75)
        a = self.db.save_log_pattern(None, dict(header, PatternName="A"), classic_strips()[:3], non_square_ok=True)
        b = self.db.save_log_pattern(None, dict(header, PatternName="B"), classic_strips()[:3])
        self.assertEqual(self.db.log_pattern(a)[0]["NonSquareOK"], 1)
        self.assertEqual(self.db.log_pattern(b)[0]["NonSquareOK"], 0)
        self.db.save_log_pattern(a, dict(header, PatternName="A"), classic_strips()[:3], non_square_ok=False)
        self.assertEqual(self.db.log_pattern(a)[0]["NonSquareOK"], 0)

    def test_old_database_gets_block_size_from_strips(self):
        path = os.path.join(self.dir.name, "old.db")
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE LogPattern(ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, PatternName TEXT NOT NULL UNIQUE,
              Variation TEXT NOT NULL DEFAULT 'Other', CentreSize REAL NOT NULL CHECK (CentreSize > 0),
              CentreColor TEXT NOT NULL DEFAULT '', SeamAllowance REAL NOT NULL DEFAULT 0.25);
            CREATE TABLE LogStrip(ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
              PatternID INTEGER NOT NULL REFERENCES LogPattern(ID) ON DELETE CASCADE,
              StripNo INTEGER NOT NULL, Side TEXT NOT NULL, Color TEXT NOT NULL, Width REAL NOT NULL);
            INSERT INTO LogPattern(PatternName, Variation, CentreSize) VALUES ('Old', 'Classic', 2.5);
            INSERT INTO LogStrip(PatternID, StripNo, Side, Color, Width) VALUES (1, 1, 'Right', 'Dark', 1.25);
            INSERT INTO LogStrip(PatternID, StripNo, Side, Color, Width) VALUES (1, 2, 'Bottom', 'Dark', 1.25);
            INSERT INTO LogStrip(PatternID, StripNo, Side, Color, Width) VALUES (1, 3, 'Left', 'Light', 1.25);
            """)
        old.commit()
        old.close()
        db = DB(path)
        header = db.log_pattern(1)[0]
        self.assertEqual((header["BlockWidth"], header["BlockLength"]), (5, 3.75))
        db.c.close()

    def test_update_replaces_strips(self):
        pid = self.db.save_log_pattern(None, CLASSIC_HEADER, classic_strips())
        small = dict(CLASSIC_HEADER, BlockWidth=5, BlockLength=5)   # first ring only: 2.5 + 2 x 1.25
        self.db.save_log_pattern(pid, small, classic_strips()[:4])
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
