import unittest # unit test library
from unittest.mock import MagicMock, patch
import FireAreaEstimator as fa 

class TestFireAreaEstimator(unittest.TestCase):

    def test_build_no_pixels_returns_none(self): # No pixels found in cluster
        pixel_fc = MagicMock()
        selected_pixels = MagicMock()
        pixel_fc.filterBounds.return_value = selected_pixels
        selected_pixels.size.return_value.getInfo.return_value = 0

        geom, method = fa._build_area_geometry(
            pixel_fc, MagicMock(), 5, MagicMock()
        )

        self.assertIsNone(geom)
        self.assertEqual(method, "no_pixels_in_cluster")

    def test_build_large_cluster_uses_convex_hull(self): # Large cluster should use convex hull
        pixel_fc = MagicMock()
        selected_pixels = MagicMock()
        cluster_geom = MagicMock()
        pixel_fc.filterBounds.return_value = selected_pixels
        selected_pixels.size.return_value.getInfo.return_value = 4
        cluster_geom.convexHull.return_value = "convex_geom"

        with patch.object(fa, "_clip", return_value="clipped_geom"):
            geom, method = fa._build_area_geometry(
                pixel_fc, cluster_geom, 4, MagicMock()
            )

        self.assertEqual(geom, "clipped_geom")
        self.assertEqual(method, "convex_hull_perimeter")

    def test_build_small_cluster_uses_footprint(self): # Small cluster should use hotspot footprint
        pixel_fc = MagicMock()
        selected_pixels = MagicMock()
        pixel_fc.filterBounds.return_value = selected_pixels
        selected_pixels.size.return_value.getInfo.return_value = 2
        selected_pixels.geometry.return_value.dissolve.return_value = "dissolved_geom"

        with patch.object(fa, "_clip", return_value="clipped_geom"):
            geom, method = fa._build_area_geometry(
                pixel_fc, MagicMock(), 2, MagicMock()
            )

        self.assertEqual(geom, "clipped_geom")
        self.assertEqual(method, "hotspot_footprint_only")

    def test_success_area_converted_to_km2(self): # Check area conversion from m² to km²
        geom = MagicMock()
        geom.getInfo.return_value = {"type": "Polygon"}

        fake_number = MagicMock()
        fake_number.getInfo.return_value = 2000000.0

        with patch("FireAreaEstimator.ee.Number", return_value=fake_number):
            result = fa._success(geom, 5, "convex_hull_perimeter")

        self.assertTrue(result["ok"])
        self.assertEqual(result["burned_area_km2"], 2.0)
        self.assertEqual(result["total_hotspot_count"], 5)
        self.assertEqual(result["method"], "convex_hull_perimeter")

if __name__ == "__main__":
    unittest.main() # run test functions 