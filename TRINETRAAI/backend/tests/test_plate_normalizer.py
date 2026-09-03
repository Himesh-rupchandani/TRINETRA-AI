"""
Tests: Plate Normalizer Utility
================================
Validates the normalize_plate() function handles all real-world OCR input patterns.
"""
import sys
from pathlib import Path

# Ensure backend root is importable
for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from app.utils.plate_normalizer import normalize_plate


class TestPlateNormalizer:
    def test_standard_indian_plate_with_spaces(self):
        assert normalize_plate("GJ 01 AB 1234") == "GJ01AB1234"

    def test_plate_with_hyphens(self):
        assert normalize_plate("GJ 01 AB-1234") == "GJ01AB1234"

    def test_plate_all_hyphens(self):
        assert normalize_plate("GJ-01-AB-1234") == "GJ01AB1234"

    def test_plate_with_dots(self):
        assert normalize_plate("DL.08-EF_9012") == "DL08EF9012"

    def test_plate_lowercase(self):
        assert normalize_plate("mh-02 cd 5678") == "MH02CD5678"

    def test_plate_mixed_whitespace(self):
        assert normalize_plate("  ka 05   xy 9999 ") == "KA05XY9999"

    def test_plate_already_normalized(self):
        assert normalize_plate("GJ01AB1234") == "GJ01AB1234"

    def test_plate_empty_string(self):
        assert normalize_plate("") == ""

    def test_plate_none(self):
        assert normalize_plate(None) == ""

    def test_plate_all_special_chars(self):
        assert normalize_plate("---   ---") == ""

    def test_plate_with_underscores(self):
        assert normalize_plate("GJ_01_AB_1234") == "GJ01AB1234"

    def test_plate_confidence_simulation(self):
        """Simulate slightly corrupted OCR output."""
        assert normalize_plate("GJ-01.AB 1234") == "GJ01AB1234"

    def test_demo_plate(self):
        """Core demo plate must normalize correctly."""
        assert normalize_plate("GJ 01 AB-1234") == "GJ01AB1234"

    def test_mh_plate(self):
        assert normalize_plate("MH 02 CD-5678") == "MH02CD5678"

    def test_dl_plate(self):
        assert normalize_plate("DL 08 EF 9012") == "DL08EF9012"
