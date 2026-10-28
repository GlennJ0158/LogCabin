"""Load sample fabric into the inventory: python sample_data.py"""
from database import Inventory, ValidationError

SAMPLES = [
    ("F0001", "Bella Solid White", "Cotton", "White", 36, 44, "Lengthwise"),
    ("F0002", "Kona Navy", "Cotton", "Navy", 54, 44, "Lengthwise"),
    ("F0003", "Dupioni Gold", "Silk", "Gold", 24, 45, "Crosswise"),
    ("F0004", "Linen Blend Sage", "Blend", "Green", 18, 22, "Bias"),
]


def load(inv):
    for row in SAMPLES:
        try:
            inv.add(dict(zip(["ID", "NAME", "TYPE", "COLOR", "LENGTH", "WIDTH", "GRAIN"], row)))
        except ValidationError:
            pass


if __name__ == "__main__":
    load(Inventory())
