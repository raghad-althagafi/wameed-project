from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
import ee
import traceback
from auth_utils import login_required

fire_detection_bp = Blueprint("fire_detection", __name__) # blueprint for the fire detection feature

class OutsideSaudiError(Exception):
    pass


# -----------------------------
# CONFIGURATION
# -----------------------------

# 500 m around the selected point making 1 km x 1 km
STRICT_BUFFER_M = 500      # around clicked point
REGION_BUFFER_M = 1500     # wider nearby region to 3 km x 3 km

# use 48 hours because active-fire products are daily products
WINDOW_HOURS = 48

# check persistence in the previous 7 days
PERSISTENCE_DAYS = 7

# confidence of the firemask
FIREMASK_THRESHOLD = 5

# NDVI thresholds used as a vegetation confidence rule
NDVI_LOW_THRESHOLD = 0.08
NDVI_GOOD_THRESHOLD = 0.20

# vegetation-related land-cover classes accepted by the project:
# forests, shrublands, savannas, grasslands, croplands, and mixed cropland/natural vegetation
BURNABLE_LULC_CLASSES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14]
SPECIAL_LULC_CLASSES = [16]

# fire products used in the project
PRODUCTS = [
    {
        "label": "VIIRS",
        "dataset_id": "NASA/VIIRS/002/VNP14A1",
        "scale_m": 1000
    },
    {
        "label": "MODIS_TERRA",
        "dataset_id": "MODIS/061/MOD14A1",
        "scale_m": 1000
    },
    {
        "label": "MODIS_AQUA",
        "dataset_id": "MODIS/061/MYD14A1",
        "scale_m": 1000
    }
]

# names for MCD12Q1 LC_Type1 classes
LULC_NAMES = {
    1: "Evergreen Needleleaf Forest",
    2: "Evergreen Broadleaf Forest",
    3: "Deciduous Needleleaf Forest",
    4: "Deciduous Broadleaf Forest",
    5: "Mixed Forest",
    6: "Closed Shrublands",
    7: "Open Shrublands",
    8: "Woody Savannas",
    9: "Savannas",
    10: "Grasslands",
    11: "Permanent Wetlands",
    12: "Croplands",
    13: "Urban and Built-up",
    14: "Cropland/Natural Vegetation Mosaic",
    15: "Permanent Snow and Ice",
    16: "Barren or Sparsely Vegetated",
    17: "Water Bodies"
}

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def _get_saudi_geometry():
    # get Saudi Arabia boundary from Google Earth Engine
    countries = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
    saudi_feature = countries.filter(ee.Filter.eq("country_na", "Saudi Arabia")).first()

# if the feature is missing, this is an internal server issue
    if saudi_feature is None:
        raise RuntimeError("Saudi Arabia boundary was not found in GEE dataset.")

    return saudi_feature.geometry()


def _ensure_inside_saudi(lat: float, lon: float):
    # check if the selected point is inside Saudi Arabia
    saudi_geom = _get_saudi_geometry()

    # build the selected poin
    pt = ee.Geometry.Point([lon, lat])

    # check whether the point is inside the Saudi polygon
    inside = saudi_geom.contains(pt, ee.ErrorMargin(1)).getInfo()

    if not bool(inside):
        raise OutsideSaudiError("Selected location is outside Saudi Arabia")


def _coerce_utc_datetime(value):
    # if there is a valid value then convert it to UTC datetime
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc) # take the currrect time if there is no value

    # check if the datetime has timezone informatio
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) # if there is no timezone info, assume it is UTC
    else:
        dt = dt.astimezone(timezone.utc) # convert from the current timezone to the current UTC

    return dt


def _safe_number(value, default=0):
    # return a safe value
    return ee.Number(ee.Algorithms.If(value, value, default))

# convert the value to float
def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)

def _get_gfs_weather(aoi, when_iso):
    when_dt = _coerce_utc_datetime(when_iso)
    when = ee.Date(when_dt.isoformat())

    era = (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .filterDate(when.advance(-2, "hour"), when.advance(2, "hour"))
        .filterBounds(aoi)
    )

    fallback = ee.Image.constant([273.15, 0]).rename([
        "temperature_2m",
        "relative_humidity"
    ])

    def add_time_diff(img):
        diff = ee.Number(img.get("system:time_start")).subtract(when.millis()).abs()
        return img.set("time_diff", diff)

    img = ee.Image(
        ee.Algorithms.If(
            era.size().gt(0),
            era.map(add_time_diff).sort("time_diff").first(),
            fallback
        )
    )

    # temperature from Kelvin to Celsius
    temp_k = _safe_float(
        img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=10000,
            bestEffort=True,
            maxPixels=1e9
        ).get("temperature_2m").getInfo(),
        273.15
    )

    # compute RH from dewpoint if direct RH band is unavailable
    vals = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=10000,
        bestEffort=True,
        maxPixels=1e9
    ).getInfo() or {}

    temp_k = _safe_float(vals.get("temperature_2m"), 273.15)
    dew_k = _safe_float(vals.get("dewpoint_temperature_2m"), 273.15)

    temp_c = temp_k - 273.15
    dew_c = dew_k - 273.15

    # Magnus formula
    import math
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    e = 6.112 * math.exp((17.67 * dew_c) / (dew_c + 243.5))
    rh = max(0, min(100, (e / es) * 100 if es else 0))

    print("WEATHER VALUES:", vals)
    print("ERA count:", era.size().getInfo())
    print("FINAL WEATHER:", {
        "temperature": round(temp_c, 2),
        "humidity": round(rh, 2)
    })
    return {
        "temperature": round(temp_c, 2),
        "humidity": round(rh, 2)
    }


def _to_iso_from_millis(value_ms, fallback_iso=None):
    try:
        if value_ms is None:
            return fallback_iso # return fallback iso
        # convert it to seconds to utc to iso
        return datetime.fromtimestamp(float(value_ms) / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return fallback_iso # return the fallback value


def _build_aoi(lat, lon, buffer_m):
    # create area around the selected point
    point = ee.Geometry.Point([lon, lat])
    return point.buffer(buffer_m).bounds()


def _fallback_fire_image(end_dt):
    # fallback fire image when no image exists
    return (
        ee.Image.constant([0, 0])
        .rename(["FireMask", "MaxFRP"])
        .set("system:time_start", end_dt.millis())
    )


def _summarize_fire_product(aoi, start_dt, end_dt, product):
    # read product settings
    label = product["label"]
    dataset_id = product["dataset_id"]
    scale_m = product["scale_m"]

    # load the fire image collection for the selected dataset in the time
    collection = (
        ee.ImageCollection(dataset_id)
        .filterDate(start_dt, end_dt)
        .filterBounds(aoi)
    )

    # number of source images were found
    collection_count = collection.size()
    fallback_img = _fallback_fire_image(end_dt)

    # merge all images across time to detect fire if it appeared in any image
    merged_img = ee.Image(
        ee.Algorithms.If(
            collection_count.gt(0),
            collection.select(["FireMask", "MaxFRP"]).max(),
            fallback_img
        )
    )

    # keep latest image only to report dataset time
    latest_img = ee.Image(
        ee.Algorithms.If(
            collection_count.gt(0),
            collection.sort("system:time_start", False).first(),
            fallback_img
        )
    )

    # pixels with FireMask >= threshold are considered fire pixels
    fire_mask = merged_img.select("FireMask").gte(FIREMASK_THRESHOLD)

    # count fire pixels in AOI
    fire_pixels = _safe_number(
        fire_mask.unmask(0).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=aoi,
            scale=scale_m,
            bestEffort=True,
            maxPixels=1e9
        ).get("FireMask"),
        0
    )

    # maximum FireMask class among pixels that passed threshold
    max_firemask_class = _safe_number(
        merged_img.select("FireMask").updateMask(fire_mask).reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=aoi,
            scale=scale_m,
            bestEffort=True,
            maxPixels=1e9
        ).get("FireMask"),
        0
    )

    # maximum FireMask regardless of threshold (for debugging)
    max_any_firemask = _safe_number(
        merged_img.select("FireMask").reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=aoi,
            scale=scale_m,
            bestEffort=True,
            maxPixels=1e9
        ).get("FireMask"),
        0
    )

    # maximum FRP among fire pixels
    frp_max = _safe_number(
        merged_img.select("MaxFRP").updateMask(fire_mask).reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=aoi,
            scale=scale_m,
            bestEffort=True,
            maxPixels=1e9
        ).get("MaxFRP"),
        0
    )

    # build one summary dictionary
    summary = ee.Dictionary({
        "collection_count": collection_count,
        "fire_pixels": fire_pixels,
        "max_firemask_class": max_firemask_class,
        "max_any_firemask": max_any_firemask,
        "frp_max": frp_max,
        "dataset_time_ms": latest_img.get("system:time_start")
    }).getInfo()

    # convert returned values into normal Python types
    fire_pixels_value = int(float(summary.get("fire_pixels") or 0))
    fire_class_value = int(float(summary.get("max_firemask_class") or 0))
    max_any_firemask_value = int(float(summary.get("max_any_firemask") or 0))
    frp_value = float(summary.get("frp_max") or 0.0)
    # if at least one real source image existed in the collection
    has_source_image = int(float(summary.get("collection_count") or 0)) > 0

    # return the final summarized fire result for this product
    return {
        "source_name": label,
        "dataset_id": dataset_id,
        "has_source_image": has_source_image,
        "is_detected": fire_pixels_value > 0,
        "fire_pixels": fire_pixels_value,
        "max_firemask_class": fire_class_value,
        "max_any_firemask": max_any_firemask_value,
        "frp_max": round(frp_value, 3),
        "dataset_time": _to_iso_from_millis(summary.get("dataset_time_ms"))
    }


def _get_ndvi_mean(aoi, end_dt):
    # start the search 32 days before the given end date
    start_dt = end_dt.advance(-32, "day")

    # load the MODIS NDVI image collection
    ndvi_collection = (
        ee.ImageCollection("MODIS/061/MOD13A1")
        .filterDate(start_dt, end_dt)
        .filterBounds(aoi)
    )

    # fallback image with NDVI = 0
    fallback_ndvi = ee.Image.constant(0).rename("NDVI")

    # use the latest NDVI image if available
    latest_ndvi = ee.Image(
        ee.Algorithms.If(
            ndvi_collection.size().gt(0),
            ndvi_collection.sort("system:time_start", False).first(),
            fallback_ndvi  # otherwise the fallback
        )
    )

    # calculate the mean value
    ndvi_mean_raw = _safe_number(
        latest_ndvi.select("NDVI").reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=500,
            bestEffort=True,
            maxPixels=1e9
        ).get("NDVI"),
        0
    ).getInfo()

    # MODIS NDVI is scaled by 10000
    ndvi_mean = float(ndvi_mean_raw) * 0.0001
    return round(ndvi_mean, 3)


def _get_lulc_class(aoi, ref_year):
    # load image collection
    lc_all = ee.ImageCollection("MODIS/061/MCD12Q1")

    year_start = ee.Date.fromYMD(ref_year, 1, 1)
    year_end = ee.Date.fromYMD(ref_year + 1, 1, 1)

    # filter the collection to the requested year only
    lc_year = lc_all.filterDate(year_start, year_end)

    # create a fallback land-cover imag
    fallback_lc = ee.Image(
        ee.Algorithms.If(
            lc_all.size().gt(0),
            lc_all.sort("system:time_start", False).first(),
            ee.Image.constant(0).rename("LC_Type1")
        )
    )

    # use the image from the requested year if available
    lc_img = ee.Image(
        ee.Algorithms.If(
            lc_year.size().gt(0),
            lc_year.first(),
            fallback_lc # otherwise use the fallback image
        )
    )

    # compute the dominant land-cover
    lc_value = _safe_number(
        lc_img.select("LC_Type1").reduceRegion(
            reducer=ee.Reducer.mode(),
            geometry=aoi,
            scale=500,
            bestEffort=True,
            maxPixels=1e9
        ).get("LC_Type1"),
        0
    ).getInfo()

    # convert the returned value into a normal Python integer
    lc_class = int(float(lc_value or 0))
    return lc_class

# return True if the land-cover class is in the list of burnable classes
def _is_burnable_lulc(lulc_class):
    return lulc_class in BURNABLE_LULC_CLASSES

# return True if the land-cover class is in the list of special classes
def _is_special_lulc(lulc_class):
    return lulc_class in SPECIAL_LULC_CLASSES

# group LULC into classes
def _get_land_type_group(lulc_class):
    if lulc_class in [1, 2, 3, 4, 5]:
        return "forest"
    if lulc_class in [12, 14]:
        return "agriculture"
    if lulc_class in [6, 7]:
        return "shrubland"
    if lulc_class in [8, 9, 10]:
        return "grassland"
    if lulc_class == 16:
        return "sparse_vegetation"
    return "non_vegetation"


def _get_ndvi_rule(ndvi_mean):
    if ndvi_mean >= NDVI_GOOD_THRESHOLD:
        return "good_vegetation"
    if ndvi_mean >= NDVI_LOW_THRESHOLD:
        return "weak_vegetation"
    return "very_low_vegetation"

# count the number of the detected fire in the previous persistence window
def _count_previous_fire_observations(aoi, ref_end_dt):
    previous_start_dt = ref_end_dt.advance(-(PERSISTENCE_DAYS + 2), "day")
    previous_end_dt = ref_end_dt.advance(-2, "day")

    count = 0
    # check each fire product separately
    for product in PRODUCTS:
        result = _summarize_fire_product(aoi, previous_start_dt, previous_end_dt, product)
        if result["is_detected"]:
            count += 1
    return count

# pick the strongest source among active sources
def _pick_primary_source(active_sources):
    if not active_sources:
        return None

    # sort sources from strongest to weakest based on max_firemask_class first then frp_max
    sorted_sources = sorted(
        active_sources,
        key=lambda item: (item["max_firemask_class"], item["frp_max"]),
        reverse=True
    )
    return sorted_sources[0]["source_name"]

# create confidence label
def _compute_fused_confidence(active_sources, ndvi_rule, lulc_burnable, persistence_confirmed):
    # the number of the fire sources are currently active
    count = len(active_sources)

    if count == 0:
        return "None"

    if count >= 2 and lulc_burnable and ndvi_rule == "good_vegetation":
        return "Very High"

    if count >= 2 and lulc_burnable:
        return "High"

    if count == 1 and lulc_burnable and ndvi_rule == "good_vegetation" and persistence_confirmed:
        return "High"

    if count == 1 and lulc_burnable and ndvi_rule == "good_vegetation":
        return "Medium"

    if count == 1 and lulc_burnable and ndvi_rule == "weak_vegetation" and persistence_confirmed:
        return "Medium"

    return "Low"


def _final_decision(active_sources, lulc_burnable, special_lulc, persistence_confirmed, land_type_group):
    sensor_count = len(active_sources)

    if sensor_count == 0:
        return False, "لم يتم رصد أي حريق بواسطة المستشعرات"

    if lulc_burnable:
        return True, f"تم رصد حريق في أرض من نوع {land_type_group}"

    if special_lulc:
        if sensor_count >= 2 or persistence_confirmed:
            return True, "تم رصد حريق في منطقة ذات غطاء نباتي متناثر"
        return False, "الأدلة ضعيفة في منطقة ذات غطاء نباتي متناثر"

    return False, "الحرارة المرصودة تقع خارج المناطق المرتبطة بالغطاء النباتي"

# -----------------------------
# CORE DETECTION FUNCTION
# -----------------------------

def _analyze_aoi(lat: float, lon: float, ref_dt, ref_iso, buffer_m):
    # build analysis area around the selected point
    aoi = _build_aoi(lat, lon, buffer_m)

    # current detection time window
    end_dt = ee.Date(ref_iso)
    start_dt = end_dt.advance(-WINDOW_HOURS, "hour")

    # step 1: read all fire products inside this AOI
    sources = []
    for product in PRODUCTS:
        src_result = _summarize_fire_product(aoi, start_dt, end_dt, product)
        sources.append(src_result)

    # keep only products that detected fire
    active_sources = [src for src in sources if src["is_detected"]]
    sensor_agreement_count = len(active_sources)
    base_detected = sensor_agreement_count > 0

    # step 2: vegetation condition using NDVI
    ndvi_mean = _get_ndvi_mean(aoi, end_dt)
    ndvi_rule = _get_ndvi_rule(ndvi_mean)

    # step 3: land cover condition
    lulc_class = _get_lulc_class(aoi, ref_dt.year)
    lulc_name = LULC_NAMES.get(lulc_class, "Unknown")
    lulc_burnable = _is_burnable_lulc(lulc_class)
    special_lulc = _is_special_lulc(lulc_class)
    land_type_group = _get_land_type_group(lulc_class)

    # step 4: persistence check using previous days
    previous_fire_observations = _count_previous_fire_observations(aoi, end_dt)
    persistence_confirmed = previous_fire_observations > 0

    # step 5: final decision for this AOI
    is_detected, decision_reason = _final_decision(
        active_sources=active_sources,
        lulc_burnable=lulc_burnable,
        special_lulc=special_lulc,
        persistence_confirmed=persistence_confirmed,
        land_type_group=land_type_group
    )

    # extra summary values
    primary_source = _pick_primary_source(active_sources)
    fused_confidence = _compute_fused_confidence(
        active_sources=active_sources,
        ndvi_rule=ndvi_rule,
        lulc_burnable=lulc_burnable,
        persistence_confirmed=persistence_confirmed
    )

    # keep dataset time only as a reference from the satellite product
    total_fire_pixels = sum(src["fire_pixels"] for src in active_sources)
    max_frp = max((src["frp_max"] for src in active_sources), default=0.0)

    active_times = [src["dataset_time"] for src in active_sources if src["dataset_time"]]
    latest_dataset_time = max(active_times) if active_times else None

    # use request time itself as the fire time shown or saved by the system
    fire_datetime = ref_iso
    # weather is taken at the same request time
    weather = _get_gfs_weather(aoi, fire_datetime)

    return {
        "aoi": aoi,
        "buffer_m": buffer_m,
        "ok": True,
        "is_detected": is_detected,
        "base_detected": base_detected,
        "decision_reason": decision_reason,
        # request / detection times
        "detected_at": ref_iso,
        "dataset_time": latest_dataset_time, # satellite reference time only
        "fire_datetime": fire_datetime, # final displayed or saved fire time = request time
        "temperature": weather["temperature"],
        "humidity": weather["humidity"],
        # fire summary
        "sensor_agreement_count": sensor_agreement_count,
        "fused_confidence": fused_confidence,
        "primary_source": primary_source,
        "total_fire_pixels": total_fire_pixels,
        "max_frp": round(max_frp, 3),
        # environment summary
        "ndvi_mean": ndvi_mean,
        "ndvi_rule": ndvi_rule,
        "lulc_class": lulc_class,
        "lulc_name": lulc_name,
        "lulc_burnable": lulc_burnable,
        "special_lulc": special_lulc,
        "land_type_group": land_type_group,
        # persistence summary
        "previous_fire_observations": previous_fire_observations,
        "persistence_confirmed": persistence_confirmed,
        # source summaries
        "sources": sources
    }

# Detect fire
def detect_active_fire(lat: float, lon: float, when_iso=None):
    # convert request time to UTC.
    ref_dt = _coerce_utc_datetime(when_iso)
    ref_iso = ref_dt.isoformat()

    print("TEST LAT:", lat)
    print("TEST LON:", lon)
    print("TEST INPUT TIME:", when_iso)
    print("TEST UTC TIME:", ref_iso)

    # step 1: strict area around clicked point
    strict_result = _analyze_aoi(lat, lon, ref_dt, ref_iso, STRICT_BUFFER_M)

    # if fire found in strict area, return it directly
    if strict_result["is_detected"]:
        return {
            "ok": True,
            "is_detected": True,
            "detected_nearby": False,
            "selected_point_has_fire": True,
            "message": "Active fire detected at the selected area",
            "decision_reason": strict_result["decision_reason"],
            "lat": lat,
            "lon": lon,
            "detected_at": strict_result["detected_at"],
            "dataset_time": strict_result["dataset_time"],
            "fire_datetime": strict_result["fire_datetime"],
            "temperature": strict_result["temperature"],
            "humidity": strict_result["humidity"],
            "analysis_radius_m": STRICT_BUFFER_M,
            "region_radius_m": REGION_BUFFER_M,
            "data_source": "VIIRS + MODIS with NDVI + LULC + Persistence filters",
            "sensor_agreement_count": strict_result["sensor_agreement_count"],
            "fused_confidence": strict_result["fused_confidence"],
            "primary_source": strict_result["primary_source"],
            "total_fire_pixels": strict_result["total_fire_pixels"],
            "max_frp": strict_result["max_frp"],
            "ndvi_mean": strict_result["ndvi_mean"],
            "ndvi_rule": strict_result["ndvi_rule"],
            "lulc_class": strict_result["lulc_class"],
            "lulc_name": strict_result["lulc_name"],
            "lulc_burnable": strict_result["lulc_burnable"],
            "special_lulc": strict_result["special_lulc"],
            "land_type_group": strict_result["land_type_group"],
            "previous_fire_observations": strict_result["previous_fire_observations"],
            "persistence_confirmed": strict_result["persistence_confirmed"],
            "sources": strict_result["sources"]
        }

    # Step 2: wider nearby region
    region_result = _analyze_aoi(lat, lon, ref_dt, ref_iso, REGION_BUFFER_M)

    # if fire is found only in the wider region, mark it as nearby
    if region_result["is_detected"]:
        return {
            "ok": True,
            "is_detected": True,
            "detected_nearby": True,
            "selected_point_has_fire": False,
            "message": "Fire detected near the selected point in the surrounding region",
            "decision_reason": region_result["decision_reason"],
            "lat": lat,
            "lon": lon,
            "detected_at": region_result["detected_at"],
            "dataset_time": region_result["dataset_time"],
            "fire_datetime": region_result["fire_datetime"],
            "temperature": region_result["temperature"],
            "humidity": region_result["humidity"],
            "analysis_radius_m": STRICT_BUFFER_M,
            "region_radius_m": REGION_BUFFER_M,
            "data_source": "VIIRS + MODIS with NDVI + LULC + Persistence filters",
            "sensor_agreement_count": region_result["sensor_agreement_count"],
            "fused_confidence": region_result["fused_confidence"],
            "primary_source": region_result["primary_source"],
            "total_fire_pixels": region_result["total_fire_pixels"],
            "max_frp": region_result["max_frp"],
            "ndvi_mean": region_result["ndvi_mean"],
            "ndvi_rule": region_result["ndvi_rule"],
            "lulc_class": region_result["lulc_class"],
            "lulc_name": region_result["lulc_name"],
            "lulc_burnable": region_result["lulc_burnable"],
            "special_lulc": region_result["special_lulc"],
            "land_type_group": region_result["land_type_group"],
            "previous_fire_observations": region_result["previous_fire_observations"],
            "persistence_confirmed": region_result["persistence_confirmed"],
            "sources": region_result["sources"]
        }

    # no fire found in strict area or nearby region
    return {
        "ok": True,
        "is_detected": False,
        "detected_nearby": False,
        "selected_point_has_fire": False,
        "message": "No reliable active fire detected in the selected area or nearby region",
        "decision_reason": strict_result["decision_reason"],
        "lat": lat,
        "lon": lon,
        "detected_at": strict_result["detected_at"],
        "dataset_time": strict_result["dataset_time"],
        "fire_datetime": strict_result["fire_datetime"],
        "temperature": strict_result["temperature"],
        "humidity": strict_result["humidity"],
        "analysis_radius_m": STRICT_BUFFER_M,
        "region_radius_m": REGION_BUFFER_M,
        "data_source": "VIIRS + MODIS with NDVI + LULC + Persistence filters",
        "sensor_agreement_count": strict_result["sensor_agreement_count"],
        "fused_confidence": strict_result["fused_confidence"],
        "primary_source": strict_result["primary_source"],
        "total_fire_pixels": strict_result["total_fire_pixels"],
        "max_frp": strict_result["max_frp"],
        "ndvi_mean": strict_result["ndvi_mean"],
        "ndvi_rule": strict_result["ndvi_rule"],
        "lulc_class": strict_result["lulc_class"],
        "lulc_name": strict_result["lulc_name"],
        "lulc_burnable": strict_result["lulc_burnable"],
        "special_lulc": strict_result["special_lulc"],
        "land_type_group": strict_result["land_type_group"],
        "previous_fire_observations": strict_result["previous_fire_observations"],
        "persistence_confirmed": strict_result["persistence_confirmed"],
        "sources": strict_result["sources"]
    }


# -----------------------------
# ROUTE
# -----------------------------
# route used to run the full fire detection process
@fire_detection_bp.route("/fire-detection", methods=["POST"])
@login_required
def fire_detection_route():
    # user UID comes from verified Firebase token
    user_id = g.user_uid
    data = request.get_json(silent=True) or {}

    lat = data.get("lat")
    lon = data.get("lon")
    when_iso = data.get("datetime")

    if lat is None or lon is None:
        return jsonify({
            "ok": False,
            "error": "missing_lat_lon",
            "message": "Missing lat/lon"
        }), 400

    try:
        lat_f = float(lat)
        lon_f = float(lon)

        # validate that the selected point is inside Saudi Arabia
        _ensure_inside_saudi(lat_f, lon_f)

        # run fire detection only after passing Saudi boundary validation
        result = detect_active_fire(lat_f, lon_f, when_iso)
        return jsonify(result), 200

    except OutsideSaudiError as e:
        return jsonify({
            "ok": False,
            "error": "outside_saudi",
            "message": str(e)
        }), 400

    except Exception:
        tb = traceback.format_exc()
        print(f">>> ERROR in /fire-detection for user {user_id}:\n{tb}")

        return jsonify({
            "ok": False,
            "error": "internal_server_error",
            "message": "An internal error occurred during fire detection.",
            "details": tb
        }), 500