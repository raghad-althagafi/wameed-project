from flask import Blueprint, request, jsonify # Blueprint, reguest for input data, jsonify for response
import ee # google earth engine
import traceback
from auth_utils import login_required

fire_area_bp = Blueprint("fire_area", __name__) # Blueprint for burned area route

# ---------------------------- CONFIGURATION ----------------------------

# Near real-time VIIRS active fire products used for current fire analysis
NRT_PRODUCTS = [
    {"label": "VIIRS_SNPP_375M", "dataset_id": "NASA/LANCE/SNPP_VIIRS/C2"},
    {"label": "VIIRS_NOAA20_375M", "dataset_id": "NASA/LANCE/NOAA20_VIIRS/C2"},
]

# Main settings used in the burned area calculation
SEARCH_RADIUS_M = 5000 # search within 5 km around the selected point
WINDOW_HOURS = 48 # look back 48 hours from the selected time
CONFIDENCE_MIN = 1 # keep nominal and high confidence pixels only
PIXEL_SCALE_M = 375 # VIIRS NRT pixel size 
AGGREGATION_DISTANCE_M = 750 # connect nearby hotspots into one fire cluster

ALL_LABELS = [p["label"] for p in NRT_PRODUCTS] # List of all datasets used in the response

# Save Saudi land geometry once so it is not loaded again in every request
_SAUDI_GEOM = None

# ---------------------------- SAUDI LAND BOUNDARY ----------------------------

def _saudi_land():
    global _SAUDI_GEOM
    # Load the Saudi Arabia land boundary only once
    if _SAUDI_GEOM is None:
        _SAUDI_GEOM = (
            ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
            .filter(ee.Filter.eq("country_na", "Saudi Arabia"))
            .geometry()
        )
    return _SAUDI_GEOM

# ---------------------------- FIRE MASK HELPERS ----------------------------

def _blank(end_dt):
    # Return an empty image when no fire image is found
    return (
        ee.Image.constant(0)
        .rename("active")
        .toByte()
        .set("system:time_start", end_dt.millis())
    )

def _nrt_mask(img):
    # Keep only NRT pixels with confidence above the minimum threshold
    return (
        ee.Image.constant(1)
        .updateMask(img.select("confidence").gte(CONFIDENCE_MIN))
        .rename("active")
        .toByte()
    )

def _nrt_product_mask(aoi, start_dt, end_dt, product):
    # Get NRT images inside the selected area and time window
    col = (
        ee.ImageCollection(product["dataset_id"])
        .filterDate(start_dt, end_dt)
        .filterBounds(aoi)
    )

    # If images exist build the mask, otherwise return a blank image
    return (
        ee.Image(
            ee.Algorithms.If(
                col.size().gt(0),
                col.map(_nrt_mask).max(),
                _blank(end_dt)
            )
        )
        .select("active")
        .unmask(0)
        .toByte()
    )

def _combined_fire_mask(aoi, when_iso):
    end_dt = ee.Date(when_iso) # Convert user time into an Earth Engine date
    start_dt = end_dt.advance(-WINDOW_HOURS, "hour") # Build a time window that looks back for the selected number of hours

    # Build masks from all near real-time products
    layers = [_nrt_product_mask(aoi, start_dt, end_dt, p) for p in NRT_PRODUCTS]

    # Combine all masks into one final fire mask
    return (
        ee.ImageCollection.fromImages(layers)
        .max()
        .gt(0)
        .selfMask()
        .rename("active")
        .toByte()
    )

# ---------------------------- GEOMETRY HELPERS ----------------------------

def _count_pixels(mask, geom):
    # Count how many real fire pixels exist inside the given geometry
    return int(
        ee.Number(
            mask.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=geom,
                scale=PIXEL_SCALE_M,
                bestEffort=True,
                maxPixels=1e9
            ).get("active")
        ).getInfo() or 0
    )

def _to_polygons(mask, aoi):
    # Convert fire pixels from raster into polygon features
    return mask.reduceToVectors(
        geometry= aoi,
        scale= PIXEL_SCALE_M,
        geometryType= "polygon",
        reducer= ee.Reducer.countEvery(),
        maxPixels= 1e9,
        bestEffort= True
    )

def _make_clusters(mask, aoi):
    # Expand fire pixels so nearby hotspots can connect into one cluster
    expanded= (
        mask.focalMax(radius= AGGREGATION_DISTANCE_M / 2, units= "meters")
        .selfMask()
    )

    # Convert the expanded result into cluster polygons
    return expanded.reduceToVectors(
        geometry= aoi,
        scale= PIXEL_SCALE_M,
        geometryType= "polygon",
        reducer= ee.Reducer.countEvery(),
        maxPixels= 1e9,
        bestEffort= True
    )

def _best_cluster(clusters_fc, point):
    # First try to find a cluster that directly contains the selected point
    inside= clusters_fc.filterBounds(point)

    # If no cluster contains the point, use all clusters and choose the nearest one
    pool= ee.FeatureCollection(
        ee.Algorithms.If(inside.size().gt(0), inside, clusters_fc)
    )

    # Sort clusters by distance to the selected point and return the closest one
    return ee.Feature(
        pool.map(lambda f: f.set("d", f.geometry().distance(point, 1)))
        .sort("d")
        .first()
    )

def _clip(geom, aoi):
    # Clip the final geometry to the search area and Saudi land boundary
    return (
        geom.intersection(aoi, maxError= 1)
        .intersection(_saudi_land(), maxError= 1)
    )
 
# ---------------------------- CORE LOGIC ----------------------------

def _build_area_geometry(pixel_fc, cluster_geom, n_pixels_in_cluster, aoi):
    # Keep only the pixel polygons that belong to the selected cluster
    selected_pixels= pixel_fc.filterBounds(cluster_geom)
    has_pixels= int(selected_pixels.size().getInfo() or 0)

    # If no polygons are found, nothing can be drawn
    if has_pixels == 0:
        return None, "no_pixels_in_cluster"

    # If the cluster is large enough, build an outer perimeter around it
    if n_pixels_in_cluster >= 3:
        geom = _clip(cluster_geom.convexHull(maxError= 1), aoi)
        method = "convex_hull_perimeter"

    # If the cluster is very small, keep the actual hotspot footprints only
    else:
        geom = _clip(selected_pixels.geometry().dissolve(maxError= 1), aoi)
        method = "hotspot_footprint_only"

    return geom, method

# ---------------------------- RESPONSE HELPERS ----------------------------

def _success(geom, n_pixels, method):
    # Convert area from square meters to square kilometers
    area_km2 = (ee.Number(geom.area(maxError=1)).getInfo() or 0) / 1e6

    return {
        "ok": True,
        "burned_area_km2": round(float(area_km2), 4),
        "total_hotspot_count": int(n_pixels),
        "burned_area_geojson": geom.getInfo(),
        "method": method,
        "time_window_hours": WINDOW_HOURS,
        "search_radius_m": SEARCH_RADIUS_M,
        "aggregation_distance_m": AGGREGATION_DISTANCE_M,
        "datasets": ALL_LABELS,
    }

# ---------------------------- ROUTE ----------------------------

@fire_area_bp.route("/fire-burned-area", methods=["POST"])
@login_required
def estimate_fire_burned_area():
    try:
        # Read request data from frontend
        body = request.get_json(silent=True) or {}
        lat = body.get("lat")
        lon = body.get("lon")
        when_iso = body.get("datetime")

        # Make sure all required values exist
        if lat is None or lon is None or not when_iso:
            return jsonify({"ok": False, "error": "Missing lat/lon/datetime"}), 400

        lat, lon = float(lat), float(lon) # Convert coordinates to float

        point = ee.Geometry.Point([lon, lat]) # Create the selected point
        aoi = point.buffer(SEARCH_RADIUS_M) # Create the search area around the selected point

        # Build one final fire mask from all available fire datasets
        fire_mask = _combined_fire_mask(aoi, when_iso)

        # Count all detected fire pixels inside the search area
        n_pixels = _count_pixels(fire_mask, aoi)

        # If no satellite pixels are found, return a small minimum estimate
        if n_pixels == 0:
            print("BURNED AREA: 0 satellite pixels → using minimum circular estimate")

            min_geom = _clip(point.buffer(PIXEL_SCALE_M / 2), aoi) # Use a small circle around the selected point as a fallback geometry

            return jsonify({
                "ok": True,
                "burned_area_km2": round((ee.Number(min_geom.area(maxError=1)).getInfo() or 0) / 1e6, 4),
                "total_hotspot_count": 0,
                "burned_area_geojson": min_geom.getInfo(),
                "method": "minimum_estimate_no_satellite_pixels",
                "time_window_hours": WINDOW_HOURS,
                "search_radius_m": SEARCH_RADIUS_M,
                "aggregation_distance_m": AGGREGATION_DISTANCE_M,
                "datasets": ALL_LABELS,
            }), 200

        # Convert the fire mask into fire pixel polygons
        pixel_fc= _to_polygons(fire_mask, aoi)

        # Group nearby fire pixels into clusters
        clusters= _make_clusters(fire_mask, aoi)
        n_clusters= int(clusters.size().getInfo() or 0)

        # If no cluster is formed, use all hotspot footprints as fallback
        if n_clusters == 0:
            geom= _clip(pixel_fc.geometry().dissolve(maxError=1), aoi)
            method= "hotspot_footprint_only"

            print(f"BURNED AREA: no cluster formed → fallback {method}")
            return jsonify(_success(geom, n_pixels, method)), 200

        # Choose the best cluster for the selected point
        cluster= _best_cluster(clusters, point)
        cluster_geom= cluster.geometry()

        # Count how many fire pixels exist inside the selected cluster
        cluster_mask= fire_mask.clip(cluster_geom)
        n_cluster_pixels= _count_pixels(cluster_mask, cluster_geom)

        # If the selected cluster has no pixels, use all pixels as fallback
        if n_cluster_pixels == 0:
            geom= _clip(pixel_fc.geometry().dissolve(maxError=1), aoi)
            method= "hotspot_footprint_only"

            print("BURNED AREA: cluster pixel count = 0 → fallback")
            return jsonify(_success(geom, n_pixels, method)), 200

        # Build the final burned area geometry for the selected cluster
        geom, method= _build_area_geometry(
            pixel_fc, cluster_geom, n_cluster_pixels, aoi
        )

        # If no geometry is returned, fallback to all pixel footprints
        if geom is None:
            geom = _clip(pixel_fc.geometry().dissolve(maxError=1), aoi)
            method = "hotspot_footprint_only"

            print("BURNED AREA: no vector pixels in cluster → fallback")

        # Print debug information
        print("BURNED AREA DEBUG:", {
            "method": method,
            "satellite_pixels_total": n_pixels,
            "satellite_pixels_cluster": n_cluster_pixels,
        })

        return jsonify(_success(geom, n_pixels, method)), 200 # Return the final burned area result

    except Exception as e:
        print("=== BURNED AREA ERROR ===")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500