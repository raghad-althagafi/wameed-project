from flask import Blueprint, request, jsonify   # Flask tools: Blueprint + request + jsonify
import ee                                       # Google Earth Engine
import math                                     # math (sin/cos/atan2)

fire_spread_bluePrint = Blueprint("fire_spread", __name__)  # Blueprint لانتشار الحريق

def _norm_deg(deg):                              # تطبيع الزاوية إلى 0..360
    return (deg % 360.0 + 360.0) % 360.0

def _dir8_ar(angle_deg):                         # تحويل زاوية إلى اتجاه عربي (8 اتجاهات)
    dirs = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]
    return dirs[int((_norm_deg(angle_deg) + 22.5) // 45) % 8]

@fire_spread_bluePrint.route("/api/fire/spread-direction", methods=["GET", "POST"])  # GET/POST للاختبار
def spread_direction():

    USE_TEST_INPUT = True  # خليها True وقت الاختبار، وبعدها رجعيها False

    # -------- 1) إدخال القيم: إما اختبار ثابت أو من الريكوست --------
    if USE_TEST_INPUT:
        lat = 40.09
        lon = -105.36
        when_iso = "2021-12-30T18:09:00Z"
    else:
        data = request.get_json(silent=True) or {}
        lat = float(data.get("lat"))              # لازم يجي من الفرونت
        lon = float(data.get("lon"))              # لازم يجي من الفرونت
        when_iso = data.get("datetime")           # لازم يجي من الفرونت

        if not when_iso:
            return jsonify({"error": "Missing datetime"}), 400

    # -------- 2) منطقة 1km x 1km حول نقطة اليوزر --------
    point = ee.Geometry.Point([lon, lat])         # (lon, lat)
    region = point.buffer(500).bounds()           # مربع تقريبًا 1كم × 1كم

    # -------- 3) نافذة زمنية ساعة واحدة --------
    t0 = ee.Date(when_iso)                        # وقت البداية
    t1 = t0.advance(1, "hour")                    # نهاية بعد ساعة

    # -------- 4) الميل + اتجاه الانحدار من SRTM --------
    dem = ee.Image("USGS/SRTMGL1_003")            # DEM
    terrain = ee.Terrain.products(dem)            # slope/aspect

    slope = terrain.select("slope").reduceRegion( # متوسط الميل داخل المنطقة
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=30,
        bestEffort=True
    ).get("slope")

    aspect = terrain.select("aspect").reduceRegion(  # متوسط اتجاه الانحدار داخل المنطقة
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=30,
        bestEffort=True
    ).get("aspect")

    upslope = ee.Number(aspect).add(180).mod(360) # تحويل downslope إلى upslope

    # -------- 5) الرياح U,V من ERA5-Land --------
    wind = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
            .filterDate(t0, t1)
            .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
            .mean())

    u = wind.select("u_component_of_wind_10m").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=1000,
        bestEffort=True
    ).get("u_component_of_wind_10m")

    v = wind.select("v_component_of_wind_10m").reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=1000,
        bestEffort=True
    ).get("v_component_of_wind_10m")

    # -------- 6) تنزيل القيم مرة واحدة --------
    vals = ee.Dictionary({"slope": slope, "upslope": upslope, "u": u, "v": v}).getInfo()

    slope_deg = float(vals.get("slope") or 0.0)       # الميل بالدرجات
    upslope_deg = float(vals.get("upslope") or 0.0)   # اتجاه upslope
    u_val = float(vals.get("u") or 0.0)               # U
    v_val = float(vals.get("v") or 0.0)               # V

    # -------- 7) اتجاه الرياح (إلى أين تهب) + سرعتها --------
    wind_to_deg = _norm_deg(math.degrees(math.atan2(u_val, v_val)))  # 0=شمال،90=شرق
    wind_speed = math.sqrt(u_val*u_val + v_val*v_val)                # m/s

    # -------- 8) ω: الرياح بالنسبة للـ upslope --------
    omega = math.radians(_norm_deg(wind_to_deg - upslope_deg))       # radians

    # -------- 9) قوة المتجهات (اتجاه فقط - تبسيط عملي) --------
    D_w = wind_speed                                                 # قوة الرياح
    D_s = math.tan(math.radians(slope_deg))                          # قوة الميل

    # -------- 10) جمع المتجهات --------
    X = D_s + D_w * math.cos(omega)                                  # X
    Y = D_w * math.sin(omega)                                        # Y

    # -------- 11) اتجاه الانتشار النهائي --------
    alpha = math.degrees(math.atan2(Y, X))                           # α
    spread_bearing = _norm_deg(upslope_deg + alpha)                  # bearing
    spread_text = _dir8_ar(spread_bearing)                           # اتجاه عربي

    return jsonify({"spread_direction_ar": spread_text}), 200   # نرجّع النص فقط
