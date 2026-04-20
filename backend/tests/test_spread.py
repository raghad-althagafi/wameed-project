import unittest # unit test libraru
from FireSpreadEstimator import _norm_deg, _dir8_ar # functions we want to test


class TestSpreadFunctions(unittest.TestCase):

    # Edge case: negative angle
    def test_norm_deg_negative(self):
        self.assertEqual(_norm_deg(-10), 350.0) # check if result equal to 350

    # Normal case: angle to direction
    def test_dir8_ar_east(self):
        self.assertEqual(_dir8_ar(90), "شرق") # check if result equal to "شرق"


if __name__ == "__main__":
    unittest.main() # run test functions