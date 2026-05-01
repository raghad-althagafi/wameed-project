import unittest  # unit test library
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch
import numpy as np

# create a fake ee module
sys.modules.setdefault("ee", types.ModuleType("ee"))

# create a fake auth_utils module
fake_auth = types.ModuleType("auth_utils")
fake_auth.login_required = lambda f: f
sys.modules["auth_utils"] = fake_auth

import FirePrediction as fp

# create a fake preprocessor 
class FakePreprocessor:
    feature_names_in_ = [
        "elevation", "slope", "aspect", "lulc", "temperature",
        "wind_speed", "precipitation", "vpd", "ndvi", "ndwi"
    ]

    # arrange features and transform it to array
    def transform(self, x):
        return x[self.feature_names_in_].to_numpy()

    # fake fetaures after preprocessing
    def get_feature_names_out(self):
        return self.feature_names_in_

# create fake model
class FakeModel:
    def __init__(self, probability):
        self.probability = probability

    def predict_proba(self, x):
        return np.array([[1-self.probability, self.probability]])

# create a test fire prediction
class TestFirePrediction(unittest.TestCase):
    def setUp(self):
        self.lat = 17.53960592243366
        self.lon = 42.93497900449253
        self.predicted_at = "2025-07-04T10:14:00+00:00"
        self.valid_features = {
            "elevation": 2208,
            "slope": 4,
            "aspect": 115,
            "lulc": 7,
            "temperature": 30.907886759440146,
            "wind_speed": 1.1782647580648822,
            "precipitation": 0.0,
            "vpd": 3.0676487058421156,
            "ndvi": 0.51695,
            "ndwi": -0.43250185910040045
        }

    # test fire prediction status
    def test_safe(self):
        risk_level, message = fp._get_risk_level(0.2, 0.35)
        self.assertEqual(risk_level, "safe")
        self.assertIn("لا يوجد توقع لحدوث حريق", message)

    def test_low(self):
        risk_level, message = fp._get_risk_level(0.37, 0.35)
        self.assertEqual(risk_level, "low")
        self.assertIn( "خطر حريق منخفض" ,message)

    def test_medium(self):
        risk_level, message = fp._get_risk_level(0.5, 0.35)
        self.assertEqual(risk_level, "medium")
        self.assertIn( "خطر حريق متوسط" ,message)

    def test_high(self):
        risk_level, message = fp._get_risk_level(0.9, 0.35)
        self.assertEqual(risk_level, "high")
        self.assertIn( "خطر حريق مرتفع" ,message)

    # test a high fire prediction process
    def test_high_prediction(self):
        with patch.object(fp, "_build_prediction_features", return_value = (self.valid_features, self.predicted_at)), \
             patch.object(fp, "_load_prediction_artifacts", return_value = (FakeModel(0.9), FakePreprocessor(), 0.35)):
            result = fp.predict_fire_risk(self.lat, self.lon, self.predicted_at)

        # check the result
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "predicted")
        self.assertTrue(result["is_predicted"])
        self.assertEqual(result["probability"], 0.9)
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["risk_label_ar"], "خطر حريق مرتفع")

    # test a safe fire prediction process
    def test_safe_prediction(self):
        with patch.object(fp, "_build_prediction_features", return_value = (self.valid_features, self.predicted_at)), \
             patch.object(fp, "_load_prediction_artifacts", return_value = (FakeModel(0.2), FakePreprocessor(), 0.35)):
            result = fp.predict_fire_risk(self.lat, self.lon, self.predicted_at)

        # check the result
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "predicted")
        self.assertFalse(result["is_predicted"])
        self.assertEqual(result["probability"], 0.2)
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["risk_label_ar"], "لا يوجد توقع لحدوث حريق")

    # test missing ndvi
    def test_missing_ndvi(self):
        features = self.valid_features.copy()
        features["ndvi"] = -9999

        with patch.object(fp, "_build_prediction_features", return_value = (features, self.predicted_at)), \
             patch.object(fp, "_load_prediction_artifacts", return_value = (FakeModel(0.9), FakePreprocessor(), 0.35)):
            result = fp.predict_fire_risk(self.lat, self.lon, self.predicted_at)

        # check the result
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ndvi_unavailable")
        self.assertFalse(result["is_predicted"])
        self.assertIsNone(result["probability"])
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["message_ar"], "تعذر تحديد نطاق الغطاء النباتي لأن قيمة NDVI غير متوفرة.")

    # test forest scope
    def test_forest(self):
        features = self.valid_features.copy()
        features["ndvi"] = 0.10

        with patch.object(fp, "_build_prediction_features", return_value=(features, self.predicted_at)), \
             patch.object(fp, "_load_prediction_artifacts", return_value=(FakeModel(0.90), FakePreprocessor(), 0.35)):
            result = fp.predict_fire_risk(self.lat, self.lon, self.predicted_at)

        # check the result
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "outside_forest_scope")
        self.assertFalse(result["is_predicted"])
        self.assertIsNone(result["probability"])
        self.assertEqual(result["risk_level"], "safe")
        self.assertEqual(result["message_ar"], "هذه المنطقة لا تُعد منطقة ذات غطاء نباتي كافٍ للتنبؤ بحرائق الغابات.")

# run test functions 
if __name__ == "__main__":
    unittest.main()   



