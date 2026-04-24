import unittest  # unit test library
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch

sys.modules.setdefault("ee", types.ModuleType("ee")) # Create a fake ee module before importing the target file

# Create a fake auth_utils module so login_required does not cause errors
fake_auth = types.ModuleType("auth_utils")
fake_auth.login_required = lambda f: f
sys.modules["auth_utils"] = fake_auth

import FireDetection as fd

class TestFireDetection(unittest.TestCase):

    def test_get_ndvi_rule_good(self): # Check that high NDVI returns good vegetation
        self.assertEqual(fd._get_ndvi_rule(0.25), "good_vegetation")

    def test_final_decision_no_sensor_detection(self): # Check that no active fire sources means no fire detection
        is_detected, reason = fd._final_decision(
            active_sources= [],
            lulc_burnable= False,
            special_lulc= False,
            persistence_confirmed= False,
            land_type_group= "non_vegetation"
        )

        self.assertFalse(is_detected)
        self.assertIn("لم يتم رصد أي حريق", reason)

    def test_final_decision_burnable_land(self): # Check that fire is accepted when the land type is burnable
        is_detected, reason = fd._final_decision(
            active_sources= [{"source_name": "VIIRS"}],
            lulc_burnable= True,
            special_lulc= False,
            persistence_confirmed= False,
            land_type_group= "forest"
        )

        self.assertTrue(is_detected)
        self.assertIn("forest", reason)

    def test_detect_active_fire_strict_area_detected(self): # Check the case when fire is detected in the strict area
        ref_dt = datetime(2025, 6, 16, 11, 0, tzinfo= timezone.utc)

        # Fake result returned from _analyze_aoi
        strict_result = {
            "ok": True,
            "is_detected": True,
            "decision_reason": "test decision",
            "detected_at": "2025-06-16T11:00:00+00:00",
            "dataset_time": "2025-06-16T10:30:00+00:00",
            "fire_datetime": "2025-06-16T11:00:00+00:00",
            "temperature": 31.5,
            "humidity": 22.4,
            "sensor_agreement_count": 2,
            "fused_confidence": "High",
            "primary_source": "VIIRS",
            "total_fire_pixels": 4,
            "max_frp": 18.2,
            "ndvi_mean": 0.23,
            "ndvi_rule": "good_vegetation",
            "lulc_class": 1,
            "lulc_name": "Evergreen Needleleaf Forest",
            "lulc_burnable": True,
            "special_lulc": False,
            "land_type_group": "forest",
            "previous_fire_observations": 1,
            "persistence_confirmed": True,
            "sources": []
        }

        # Replace helper functions with fixed values during the test
        with patch.object(fd, "_coerce_utc_datetime", return_value=ref_dt), \
             patch.object(fd, "_analyze_aoi", return_value=strict_result):

            result = fd.detect_active_fire(18.2, 42.5, "2025-06-16T11:00:00Z")

        # Check the returned result
        self.assertTrue(result["ok"])
        self.assertTrue(result["is_detected"])
        self.assertTrue(result["selected_point_has_fire"])
        self.assertFalse(result["detected_nearby"])

if __name__ == "__main__":
    unittest.main()  # run test functions