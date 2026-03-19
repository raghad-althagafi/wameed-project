from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from pathlib import Path
import math
import traceback
import ee
import joblib
import pandas as pd
from auth_utils import login_required
import os
import requests
from datetime import datetime, timezone, timedelta

# import shared helper functions from FireDetection
from FireDetection import (
    OutsideSaudiError,
    _ensure_inside_saudi,
    _coerce_utc_datetime,
    _safe_number,
    _safe_float
)

fire_prediction_bp = Blueprint("fire_prediction", __name__) # blueprint for the fire prediction routes


# -----------------------------
# CONFIGURATION
# -----------------------------

SCALE_M = 1000 # same spatial resolution used in the training file

# threshold of the fire 
NDVI_SCOPE_THRESHOLD = 0.15 # vegetation area
RISK_MEDIUM_THRESHOLD = 0.40 # medium fire risk
RISK_HIGH_THRESHOLD = 0.60 # high fire risk

# folder that contains this file
BASE_DIR = Path(__file__).resolve().parent

# folder that contains model files
MODEL_DIR = BASE_DIR / "Model"

# path for saved model files
MODEL_PATH = MODEL_DIR / "rf_model.pkl"
PREPROCESSOR_PATH = MODEL_DIR / "preprocessor.pkl"
THRESHOLD_PATH = MODEL_DIR / "threshold.pkl"

# global variables to load model files once only
_model = None
_preprocessor = None
_threshold = None


# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def _load_prediction_artifacts():
    # use global variables so files are not loaded every request
    global _model, _preprocessor, _threshold

    # load trained model if it is not loaded yet
    if _model is None:
        _model = joblib.load(MODEL_PATH)

    # load preprocessor if it is not loaded yet
    if _preprocessor is None:
        _preprocessor = joblib.load(PREPROCESSOR_PATH)

    # load threshold if it exists, otherwise use default threshold
    if _threshold is None:
        if THRESHOLD_PATH.exists():
            _threshold = float(joblib.load(THRESHOLD_PATH))
        else:
            _threshold = 0.35

    return _model, _preprocessor, _threshold


def _build_point(lat, lon):
    # build selected point geometry
    return ee.Geometry.Point([lon, lat])


def _get_terrain_features(point_geom):
    # load SRTM elevation model
    srtm = ee.Image("USGS/SRTMGL1_003")

    # build terrain products
    terrain = ee.Algorithms.Terrain(srtm)

    # combine static terrain bands
    static_img = (
        terrain.select("elevation").rename("elevation")
        .addBands(terrain.select("slope").rename("slope"))
        .addBands(terrain.select("aspect").rename("aspect"))
    )

    # take terrain values at the selected point
    vals = static_img.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=point_geom,
        scale=SCALE_M,
        bestEffort=True,
        maxPixels=1e8
    ).getInfo() or {}

    return {
        "elevation": round(_safe_float(vals.get("elevation"), -9999), 3),
        "slope": round(_safe_float(vals.get("slope"), -9999), 3),
        "aspect": round(_safe_float(vals.get("aspect"), -9999), 3)
    }


def _get_lulc_class(point_geom):
    # load MODIS land cover and sort from newest to oldest
    lc_col = (
        ee.ImageCollection("MODIS/061/MCD12Q1")
        .select("LC_Type1")
        .sort("system:time_start", False)
    )

    # take most recent image if available, otherwise use fallback image
    lulc_img = ee.Image(
        ee.Algorithms.If(
            lc_col.size().gt(0),
            lc_col.first(),
            ee.Image.constant(0).rename("LC_Type1")
        )
    ).rename("lulc")

    # take lulc value at the selected point
    lulc_value = _safe_number(
        lulc_img.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point_geom,
            scale=SCALE_M,
            bestEffort=True,
            maxPixels=1e8
        ).get("lulc"),
        -9999
    ).getInfo()

    return int(float(lulc_value or -9999))


def _get_ndvi_mean(point_geom, end_dt):
    # use recent 32 days to get NDVI
    start_dt = end_dt.advance(-32, "day")

    # load MODIS NDVI collection
    ndvi_col = (
        ee.ImageCollection("MODIS/061/MOD13A1")
        .filterBounds(point_geom)
        .filterDate(start_dt, end_dt)
        .select("NDVI")
    )

    # if images exist use median, otherwise use fallback value
    ndvi_img = ee.Image(
        ee.Algorithms.If(
            ndvi_col.size().gt(0),
            ndvi_col.median().multiply(0.0001).rename("ndvi"),
            ee.Image.constant(-9999).rename("ndvi")
        )
    )

    # take NDVI value at the selected point
    ndvi_value = _safe_number(
        ndvi_img.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point_geom,
            scale=SCALE_M,
            bestEffort=True,
            maxPixels=1e8
        ).get("ndvi"),
        -9999
    ).getInfo()

    return round(float(ndvi_value or -9999), 3)


def _get_ndwi_mean(point_geom, end_dt):
    # use recent 16 days to get surface reflectance
    start_dt = end_dt.advance(-16, "day")

    # load MODIS surface reflectance using the same bands as the training file
    sr_col = (
        ee.ImageCollection("MODIS/061/MOD09GA")
        .filterBounds(point_geom)
        .filterDate(start_dt, end_dt)
        .select(["sur_refl_b04", "sur_refl_b02"])
    )

    # if images exist use median, otherwise use fallback image
    sr_img = ee.Image(
        ee.Algorithms.If(
            sr_col.size().gt(0),
            sr_col.median(),
            ee.Image.constant([0, 0]).rename(["sur_refl_b04", "sur_refl_b02"])
        )
    )

    # convert bands to real values
    green = sr_img.select("sur_refl_b04").multiply(0.0001)
    nir = sr_img.select("sur_refl_b02").multiply(0.0001)

    # NDWI = (green - nir) / (green + nir)
    ndwi = green.subtract(nir).divide(green.add(nir)).rename("ndwi")

    # take NDWI value at the selected point
    ndwi_value = _safe_number(
        ndwi.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point_geom,
            scale=SCALE_M,
            bestEffort=True,
            maxPixels=1e8
        ).get("ndwi"),
        -9999
    ).getInfo()

    return round(float(ndwi_value or -9999), 3)


import requests
from datetime import timedelta

def _get_weather_features(lat, lon, when_iso):
    when_dt = _coerce_utc_datetime(when_iso)
    now_utc = datetime.now(timezone.utc)

    target_hour = when_dt.replace(minute=0, second=0, microsecond=0)
    end_hour = target_hour + timedelta(hours=1)

    hourly_vars = "temperature_2m,dew_point_2m,precipitation,vapour_pressure_deficit,wind_speed_10m"

    # historical
    if target_hour < now_utc.replace(minute=0, second=0, microsecond=0):
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": hourly_vars,
            "start_date": target_hour.strftime("%Y-%m-%d"),
            "end_date": target_hour.strftime("%Y-%m-%d"),
            "timezone": "GMT",
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm"
        }
        mode = "archive"
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": hourly_vars,
            "start_hour": target_hour.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end_hour.strftime("%Y-%m-%dT%H:%M"),
            "timezone": "GMT",
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm"
        }
        mode = "forecast"

    response = requests.get(url, params=params, timeout=20)
    print("OPEN-METEO MODE:", mode)
    print("OPEN-METEO STATUS:", response.status_code)
    print("OPEN-METEO URL:", response.url)
    print("OPEN-METEO TEXT:", response.text[:500])
    response.raise_for_status()

    payload = response.json()
    hourly = payload.get("hourly") or {}

    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    dews = hourly.get("dew_point_2m") or []
    precs = hourly.get("precipitation") or []
    vpds = hourly.get("vapour_pressure_deficit") or []
    winds = hourly.get("wind_speed_10m") or []

    if not times:
        raise ValueError("Open-Meteo returned no hourly weather data.")

    # archive returns whole day; forecast request above usually returns one hour
    target_key = target_hour.strftime("%Y-%m-%dT%H:00")
    idx = 0
    for i, t in enumerate(times):
        if str(t).startswith(target_key):
            idx = i
            break

    temperature = temps[idx] if idx < len(temps) else None
    dew_point = dews[idx] if idx < len(dews) else None
    precipitation = precs[idx] if idx < len(precs) else None
    vpd = vpds[idx] if idx < len(vpds) else None
    wind_speed = winds[idx] if idx < len(winds) else None

    if None in (temperature, dew_point, precipitation, vpd, wind_speed):
        raise ValueError("Open-Meteo response is missing required weather fields.")

    print("OPEN-METEO lat/lon:", lat, lon)
    print("OPEN-METEO target hour UTC:", target_hour.isoformat())
    print("OPEN-METEO values:", {
        "temperature": temperature,
        "dew_point": dew_point,
        "precipitation": precipitation,
        "vpd": vpd,
        "wind_speed": wind_speed
    })
    print(f"lat={lat}, lon={lon}")
    # print(f"probability={probability}")
    # print(f"threshold={threshold}")

    return {
        "temperature": round(float(temperature), 3),
        "wind_speed": round(float(wind_speed), 3),
        "precipitation": round(float(precipitation), 6),
        "vpd": round(float(vpd), 3)
    }

def _build_prediction_features(lat, lon, when_iso=None):
    # if there is no datetime from frontend, use current UTC time
    ref_dt = _coerce_utc_datetime(when_iso)
    ref_iso = ref_dt.isoformat()

    # build selected point
    point_geom = _build_point(lat, lon)

    # convert datetime to ee.Date
    end_dt = ee.Date(ref_iso)

    # extract static and dynamic features
    terrain = _get_terrain_features(point_geom)
    weather = _get_weather_features(lat, lon, ref_iso)
    ndvi_mean = _get_ndvi_mean(point_geom, end_dt)
    ndwi_mean = _get_ndwi_mean(point_geom, end_dt)
    lulc_class = _get_lulc_class(point_geom)

    # return all raw features in the same structure used by the model
    return {
        "elevation": terrain["elevation"],
        "slope": terrain["slope"],
        "aspect": terrain["aspect"],
        "lulc": lulc_class,
        "temperature": weather["temperature"],
        "wind_speed": weather["wind_speed"],
        "precipitation": weather["precipitation"],
        "vpd": weather["vpd"],
        "ndvi": ndvi_mean,
        "ndwi": ndwi_mean
    }, ref_iso


# get the fire
def _get_risk_level(probability, threshold):
    probability = float(probability)
    threshold = float(threshold)
    threshold = float(threshold)

    if probability < threshold:
        return "safe", "لا يوجد توقع لحدوث حريق"
    elif probability < RISK_MEDIUM_THRESHOLD:
        return "low", "خطر حريق منخفض"
    elif probability < RISK_HIGH_THRESHOLD:
        return "medium", "خطر حريق متوسط"
    else:
        return "high", "خطر حريق مرتفع"


def predict_fire_risk(lat, lon, when_iso=None):
    # load trained model, preprocessor, and saved threshold
    model, preprocessor, threshold = _load_prediction_artifacts()

    # build input features for the selected location and time
    features, predicted_at = _build_prediction_features(lat, lon, when_iso)

    # get NDVI value from built features
    ndvi_value = features.get("ndvi")

    # if NDVI is missing, prediction cannot continue
    if ndvi_value is None or ndvi_value == -9999:
        return {
            "ok": True,
            "status": "ndvi_unavailable",
            "is_predicted": False,
            "probability": None,
            "threshold": float(threshold),
            "predicted_at": predicted_at,
            "features": features,
            "risk_level": "safe",
            "message_ar": "تعذر تحديد نطاق الغطاء النباتي لأن قيمة NDVI غير متوفرة."
        }

    # if NDVI is below the vegetation threshold, the point is outside forest scope
    if ndvi_value < NDVI_SCOPE_THRESHOLD:
        return {
            "ok": True,
            "status": "outside_forest_scope",
            "is_predicted": False,
            "probability": None,
            "threshold": float(threshold),
            "predicted_at": predicted_at,
            "features": features,
            "risk_level": "safe",
            "message_ar": "هذه المنطقة لا تُعد منطقة ذات غطاء نباتي كافٍ للتنبؤ بحرائق الغابات."
        }

    # convert features dictionary into one-row dataframe for prediction
    X_new = pd.DataFrame([features])

    # reorder columns to match the columns used during training
    if hasattr(preprocessor, "feature_names_in_"):
        X_new = X_new.reindex(columns=list(preprocessor.feature_names_in_))

    # apply preprocessing pipeline
    X_processed = preprocessor.transform(X_new)

    # convert sparse matrix to normal array if needed
    if hasattr(X_processed, "toarray"):
        X_processed = X_processed.toarray()

    # get processed feature names from preprocessor
    processed_feature_names = preprocessor.get_feature_names_out()

    # convert processed data into dataframe for model input
    X_processed_df = pd.DataFrame(X_processed, columns=processed_feature_names)

    # get probability of class 1 = fire
    probability = float(model.predict_proba(X_processed_df)[0, 1])

    # determine if the probability passes the saved threshold
    is_predicted = probability >= threshold

    # determine risk level and Arabic label
    risk_level, risk_label_ar = _get_risk_level(probability, threshold)

    # return final prediction result
    return {
        "ok": True,
        "status": "predicted",
        "is_predicted": bool(is_predicted),
        "probability": round(probability, 4),
        "threshold": float(threshold),
        "risk_level": risk_level,
        "risk_label_ar": risk_label_ar,
        "predicted_at": predicted_at,
        "features": features
    }

# -----------------------------
# ROUTE
# -----------------------------

@fire_prediction_bp.route("/fire-prediction", methods=["POST"]) # route for method POST
@login_required # take user token and check it
def fire_prediction_route(): # function that analyze fire prediction
    user_id = g.user_uid # get user id from the token only for debugging

    # read json body safely
    data = request.get_json(silent=True) or {}

    # read coordinates and optional datetime from frontend
    lat = data.get("lat")
    lon = data.get("lon")
    when_iso = data.get("datetime")

    # validate required fields
    if lat is None or lon is None:
        return jsonify({
            "ok": False,
            "error": "missing_lat_lon",
            "message": "Missing lat/lon"
        }), 400

    try:
        # convert coordinates to float
        lat_f = float(lat)
        lon_f = float(lon)

        # make sure point is inside Saudi Arabia
        _ensure_inside_saudi(lat_f, lon_f)

        # run prediction
        result = predict_fire_risk(lat_f, lon_f, when_iso)

        # return the prediction result
        return jsonify(result), 200

    except OutsideSaudiError as e:
        return jsonify({
            "ok": False,
            "error": "outside_saudi",
            "message": str(e)
        }), 400

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": "internal_server_error",
            "message": str(e)
        }), 500

    except Exception:
        tb = traceback.format_exc()
        print(f">>> ERROR in /fire-prediction for user {user_id}:\n{tb}")

        return jsonify({
            "ok": False,
            "error": "internal_server_error",
            "message": "An internal error occurred during fire prediction.",
            "details": tb
        }), 500