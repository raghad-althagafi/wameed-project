import unittest
from Singleton.gee_connection import GEEConnection
GEEConnection.get_instance()

from FireThreatEstimator import normalize, safe_number, compute_threat_score

# Weights used in threat calculation
W_FIRE = 0.25
W_SPREAD = 0.35
W_EXPOSURE = 0.40


class TestFireThreatEstimator(unittest.TestCase):

    def test_normalize_mid_value(self):
        # Test normalization for a normal value
        result = normalize(100, 200)
        value = float(result.getInfo())
        self.assertAlmostEqual(value, 0.5)

    def test_normalize_upper_clamp(self):
        # Test normalization upper limit
        result = normalize(500, 200)
        value = float(result.getInfo())
        self.assertAlmostEqual(value, 1.0)

    def test_safe_number_with_none(self):
        # Test handling of None values
        result = safe_number(None)
        value = float(result.getInfo())
        self.assertEqual(value, 0.0)

    def test_safe_number_with_valid_value(self):
        # Test handling of valid numbers
        result = safe_number(15)
        value = float(result.getInfo())
        self.assertEqual(value, 15.0)

    def test_threat_score_formula(self):
        # Test full threat score calculation
        result = compute_threat_score(1.0, 1.0, 1.0, 0.25, 0.35, 0.40)
        value = float(result.getInfo())
        self.assertAlmostEqual(value, 1.0)

    def test_threat_score_weighted_case(self):
        # Test weighted threat score case
        result = compute_threat_score(0.5, 0.6, 0.8, 0.25, 0.35, 0.40)
        value = float(result.getInfo())
        expected = (0.5 * 0.25) + (0.6 * 0.35) + (0.8 * 0.40)
        self.assertAlmostEqual(value, expected)
    
    


if __name__ == "__main__":
    unittest.main()