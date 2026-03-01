from flask import Blueprint, request, jsonify # BluePrint, reguest for input data, jsonify for response
import ee # google earth engine
import math # sin, cos, atan

fire_spread_bluePrint = Blueprint("fire_spread", __name__) # Blue print for fire spread

def _norm_deg(deg): # if the degree is negative or above 360, it will return it in correct way
    return (deg % 360.0 + 360.0) % 360.0

def _dir8_ar(angle_deg): # the function take the degree as input and convert the degree into a direction
    dirs = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"] # divided into 8 directions
    return dirs[int((_norm_deg(angle_deg) + 22.5) // 45) % 8]

@fire_spread_bluePrint.route("/fire-spread-direction", methods=["POST"])
def spread_direction():

     # read json
    data = request.get_json(silent=True) or {}

    lat = float(data.get("lat")) # take lat from json and convert it to float
    lon = float(data.get("lon")) # take lon from json and convert it to float
    when_iso = data.get("datetime") # take datetime from json

    # if datetimelat, lon missing it will return error message
    if lat is None or lon is None or not when_iso:
        return jsonify({"error": "Missing lat/lon/datetime"}), 400

    # ------------- Convert user point into 1 km * 1 km region ----------------
    point = ee.Geometry.Point([lon, lat]) # the point the user selects
    region = point.buffer(500).bounds() # convert it into region 1 km * 1 km

    # ----------- convert time into time window equal to one hour --------
    t0 = ee.Date(when_iso) # convert the specific time into time in ee
    t1 = t0.advance(1, "hour") # return time window of one hour

    # ------------- get the slope and aspect --------------------
    dem = ee.Image("USGS/SRTMGL1_003")
    terrain = ee.Terrain.products(dem)

    slope = terrain.select("slope").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=30,
        bestEffort=True
    ).get("slope") # return the slope mean foe the region

    aspect = terrain.select("aspect").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=30,
        bestEffort=True
    ).get("aspect") # return the aspect mean foe the region

    upslope = ee.Number(aspect).add(180).mod(360) # convert the aspect into upslope by adding 180 degree

    # Fetch values from google earth engine into python
    vals = ee.Dictionary({"slope": slope, "upslope": upslope}).getInfo()

    # convert values into float
    slope_deg = float(vals.get("slope") or 0.0)
    upslope_deg = float(vals.get("upslope") or 0.0)

    # -------- wind from NOAA GFS0P25 --------
    region_wind = point.buffer(15000).bounds() # convert it into bigger region for wind (better with coarse models)

    gfs = ee.ImageCollection("NOAA/GFS0P25")

    t_prev = t0.advance(-6, "hour") # take time window before the requested time because GFS updates every 6 hours

    gfs_img = (gfs
               .filter(ee.Filter.gte("forecast_time", t_prev.millis()))
               .filter(ee.Filter.lte("forecast_time", t1.millis()))
               .sort("forecast_time", False) # get the nearest time to the user datetime
               .first())

    u = ee.Image(gfs_img).select("u_component_of_wind_10m_above_ground").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region_wind,
        scale=30000,
        bestEffort=True
    ).get("u_component_of_wind_10m_above_ground") # get the u component for wind which reflect wind speed East/West

    v = ee.Image(gfs_img).select("v_component_of_wind_10m_above_ground").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region_wind,
        scale=30000,
        bestEffort=True
    ).get("v_component_of_wind_10m_above_ground") # get the v component for wind which reflect wind speed north/south

    # Fetch values from google earth engine into python
    vals_wind = ee.Dictionary({"u": u, "v": v}).getInfo()

    # convert values into float
    u_val = float(vals_wind.get("u") or 0.0)
    v_val = float(vals_wind.get("v") or 0.0)

    wind_to_deg = _norm_deg(math.degrees(math.atan2(u_val, v_val))) # wind direction
    wind_speed = math.sqrt(u_val*u_val + v_val*v_val) # wind speed

    # calculate the diffrence between wind_to_deg and upslope_deg,
    omega = math.radians(_norm_deg(wind_to_deg - upslope_deg)) # convert to radians for sin, cos later

    D_w = wind_speed # wind factor
    D_s = math.tan(math.radians(slope_deg)) # slope factor

    # -------- vectors addition--------
    X = D_s + D_w * math.cos(omega)
    Y = D_w * math.sin(omega)

    # -------- The final Spread Direction calculation --------
    alpha = math.degrees(math.atan2(Y, X))
    spread_bearing = _norm_deg(upslope_deg + alpha)
    spread_text = _dir8_ar(spread_bearing) # convert the result into arabic text represnt the direction

    return jsonify({"spread_direction_ar": spread_text}), 200 # return the direction text only