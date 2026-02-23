from flask import Blueprint, request, jsonify
import ee
import traceback

fire_threat_bp = Blueprint("fire_threat", __name__)

BUFFER_M = 500  # buffer around point (meters) بعدين بغيرها ****************************

# Normalization caps
FRP_MAX = 200.0
POP_MAX = 500.0
FWI_CAP = 50.0

# Weights
W_FIRE = 0.25
W_SPREAD = 0.35
W_EXPOSURE = 0.40

# -----Utils-------
def normalize(val, max_val):
    return ee.Number(val).divide(max_val).clamp(0, 1)

# Ensures value is not null (returns default if null) to prevent EE calculation errors
def safe_number(val, default=0):
    return ee.Number(ee.Algorithms.If(val, val, default))

def mean_in_aoi(img, aoi, scale, default=0):
    val = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e9
    ).values().get(0)
    return safe_number(val, default)   # ✅ تمنع null


# Helpers: units + RH
def to_celsius(k_img): # Convert temperature from Kelvin (ERA5 units) to Celsius
    return ee.Image(k_img).subtract(273.15)

# Compute wind speed (km/h) from ERA5 wind components u and v (m/s).
# Speed = sqrt(u^2 + v^2), then convert m/s -> km/h by multiplying 3.6
def wind_speed_kmh(u, v):
    u = ee.Image(u) # u = اتجاه شرق/غرب 
    v = ee.Image(v)# v = اتجاه شمال/جنوب
    return u.pow(2).add(v.pow(2)).sqrt().multiply(3.6)

# Estimate relative humidity (%) from air temperature (T) and dew point temperature (Td).
# Uses the Magnus approximation to compute saturation vapor pressure (es) and actual vapor pressure (e),
# then RH = (e/es) * 100, clamped to [0, 100].
def rel_humidity_pct(temp_k, dew_k):
    t = to_celsius(temp_k) # درجة حرارة الهواء
    td = to_celsius(dew_k) # درجة حرارة الندى
    es = t.expression("6.112*exp((17.67*T)/(T+243.5))", {"T": t})
    e  = td.expression("6.112*exp((17.67*Td)/(Td+243.5))", {"Td": td})
    rh = ee.Image(e).divide(es).multiply(100)
    return rh.clamp(0, 100)

def ffmc_next(ffmc_prev, T_c, RH, W_kmh, R_mm):
        
    """
    Compute next-day FFMC based on weather inputs
    (temperature, humidity, wind, rainfall).
    """
    # Ensure FFMC is within valid range
    ffmc_prev = ee.Image(ffmc_prev).clamp(0, 101)

    # Convert FFMC to moisture content mo
    mo = ffmc_prev.expression(
        "147.2*(101.0-FFMC)/(59.5+FFMC)", {"FFMC": ffmc_prev}
    )

    # Rain effect (only if rain > 0.5 mm)
    rf = ee.Image(R_mm).subtract(0.5).max(0)

    # Moisture increase due to rainfall (standard FWI formula)
    mr1 = mo.expression(
        "mo + 42.5*rf*exp(-100.0/(251.0-mo))*(1-exp(-6.93/rf))",
        {"mo": mo, "rf": rf}
    )
    # Additional adjustment for very wet fuels
    mr2 = mr1.expression(
        "mr1 + 0.0015*(mo-150.0)**2*sqrt(rf)",
        {"mr1": mr1, "mo": mo, "rf": rf}
    )
    # Apply conditional rain correction
    mr = ee.Image(ee.Algorithms.If(mo.gt(150), mr2, mr1)).min(250)

    # Drying/wetting equilibrium
    Ed = T_c.expression(
        "0.942*(RH**0.679) + (11*exp((RH-100)/10)) + 0.18*(21.1-T)*(1-exp(-0.115*RH))",
        {"RH": RH, "T": T_c}
    )
    Ew = T_c.expression(
        "0.618*(RH**0.753) + (10*exp((RH-100)/10)) + 0.18*(21.1-T)*(1-exp(-0.115*RH))",
        {"RH": RH, "T": T_c}
    )
    # Drying rate coefficient (ko)
    ko = T_c.expression(
        "0.424*(1-(RH/100)**1.7) + 0.0694*sqrt(W)*(1-(RH/100)**8)",
        {"RH": RH, "W": W_kmh}
    )
    ko = ko.multiply(0.581).multiply(T_c.expression("exp(0.0365*T)", {"T": T_c}))

    # Wetting rate coefficient (kw)
    kw = T_c.expression(
        "0.424*(1-((100-RH)/100)**1.7) + 0.0694*sqrt(W)*(1-((100-RH)/100)**8)",
        {"RH": RH, "W": W_kmh}
    )
    kw = kw.multiply(0.581).multiply(T_c.expression("exp(0.0365*T)", {"T": T_c}))

    # Update moisture m
    m_dry = Ed.add(mr.subtract(Ed).multiply(ko.multiply(-1).exp()))
    m_wet = Ew.subtract(Ew.subtract(mr).multiply(kw.multiply(-1).exp()))
    m_mid = mr

    m = ee.Image(
        ee.Algorithms.If(
            mr.gt(Ed), m_dry,
            ee.Algorithms.If(mr.lt(Ew), m_wet, m_mid)
        )
    )

    ffmc = m.expression("(59.5*(250.0-m))/(147.2+m)", {"m": m})
    return ee.Image(ffmc).clamp(0, 101)

def isi_from_ffmc_wind(ffmc, W_kmh):
    ffmc = ee.Image(ffmc).clamp(0, 101)

    m = ffmc.expression("147.2*(101.0-FFMC)/(59.5+FFMC)", {"FFMC": ffmc})

    fW = ee.Image(W_kmh).expression("exp(0.05039*W)", {"W": W_kmh})
    fF = m.expression("91.9*exp(-0.1386*m)*(1 + (m**5.31)/(4.93e7))", {"m": m})

    isi = fW.multiply(fF).multiply(0.208)
    return isi.max(0)

# ----------------------
# DMC / DC / BUI / FWI (SAFE EE ops)
# ----------------------
def dmc_next(dmc_prev, T_c, RH, R_mm, month_num):
    P0 = ee.Image(dmc_prev)
    T  = ee.Image(T_c)
    H  = ee.Image(RH)
    R  = ee.Image(R_mm)

   
    T = T.max(-1.1)


    EL = ee.List([6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0])
    Le = ee.Number(EL.get(ee.Number(month_num).subtract(1)))  # month_num is 1..12
    Le_img = ee.Image.constant(Le)

    # K = 1.894 (T + 1.1) (100 - H) Le * 10^-6
    K = ee.Image.constant(1.894).multiply(T.add(1.1)).multiply(ee.Image.constant(100).subtract(H)).multiply(Le_img).multiply(1e-6)

    # --- Rain routine only if r0 > 1.5 mm
    rain_event = R.gt(1.5)

    #  re = 0.92 r0 - 1.27
    re = R.multiply(0.92).subtract(1.27).max(0)

    #  Mo = 20 + exp(5.6348 - P0/43.43)
    Mo = P0.expression("20 + exp(5.6348 - P/43.43)", {"P": P0})

    #  b piecewise based on P0
    b_13a = P0.expression("100/(0.5 + 0.3*P)", {"P": P0})               # P0 <= 33
    b_13b = P0.expression("14 - 1.3*log(P)", {"P": P0})                # 33 < P0 <= 65
    b_13c = P0.expression("6.2*log(P) - 17.2", {"P": P0})              # P0 > 65

    b = ee.Image(
        ee.Algorithms.If(
            P0.lte(33), b_13a,
            ee.Algorithms.If(P0.lte(65), b_13b, b_13c)
        )
    )

    #  Mr = Mo + 1000 re / (48.77 + b re)
    Mr = Mo.add(re.multiply(1000).divide(ee.Image.constant(48.77).add(b.multiply(re))))

    #  Pr = 244.72 - 43.43 ln(Mr - 20)
    Pr = Mr.expression("244.72 - 43.43*log(Mr - 20)", {"Mr": Mr})

    #  Pr cannot be < 0 => raise negatives to 0
    Pr = Pr.max(0)

    #  P = (P0 or Pr) + 100K
    P_base = ee.Image(ee.Algorithms.If(rain_event, Pr, P0))
    P = P_base.add(K.multiply(100))

    return P.max(0)

def dc_next(dc_prev, T, R):
    dc_prev = ee.Image(dc_prev)
    T = ee.Image(T)
    R = ee.Image(R)

    re = R.multiply(0.83).subtract(1.27).max(0)

    
    dc_rain = dc_prev.subtract(re.multiply(400).divide(re.add(800)))
    dc_no_rain = dc_prev.add(T.multiply(0.05))

    return ee.Image(ee.Algorithms.If(R.gt(2.8), dc_rain, dc_no_rain)).max(0)

def bui_from_dmc_dc(dmc, dc):
    dmc = ee.Image(dmc)
    dc = ee.Image(dc)

    c04dc = dc.multiply(0.4)
    c08dc = dc.multiply(0.8)

    bui_case1 = dmc.multiply(c08dc).divide(dmc.add(c04dc))

    ratio = c08dc.divide(dmc.add(c04dc))
    term = ee.Image.constant(1).subtract(ratio)

    bui_case2 = dmc.subtract(
        term.multiply(
            ee.Image.constant(0.92).add(
                ee.Image.constant(0.0114).multiply(dmc).pow(1.7)
            )
        )
    )

    bui = ee.Image(ee.Algorithms.If(dmc.lte(c04dc), bui_case1, bui_case2))
    return bui.max(0)

def fwi_from_isi_bui(isi, bui):
    isi = ee.Image(isi)
    bui = ee.Image(bui)

    fD_case1 = ee.Image.constant(0.626).multiply(bui.pow(0.809)).add(2)

    fD_case2 = ee.Image.constant(1000).divide(
        ee.Image.constant(25).add(
            ee.Image.constant(108.64).multiply(bui.multiply(-0.023).exp())
        )
    )

    fD = ee.Image(ee.Algorithms.If(bui.lte(80), fD_case1, fD_case2))

    B = isi.multiply(fD).multiply(0.1)

    fwi_case1 = B
    fwi_case2 = ee.Image.constant(2.72).multiply(
        ee.Image.constant(0.434).multiply(B.log()).pow(0.647)
    ).exp()

    fwi = ee.Image(ee.Algorithms.If(B.lte(1), fwi_case1, fwi_case2))
    return fwi.max(0)


# Core compute
def compute_fire_threat(lat: float, lon: float, when_iso: str, w_fire: float, w_spread: float, w_exposure: float):
    AOI = ee.Geometry.Point([lon, lat]).buffer(BUFFER_M)

    DAY = ee.Date(when_iso)
    START = DAY
    END = DAY.advance(1, "day")

    # Fire Power (VIIRS FRP)
    active_fire_collection = (
        ee.ImageCollection("NASA/VIIRS/002/VNP14A1")
        .filterDate(START, END)
        .filterBounds(AOI)
    )

    active_fire_img = ee.Image(active_fire_collection.max())
    fire_mask = active_fire_img.select("FireMask").gte(7)

    frp_max = active_fire_img.select("MaxFRP").updateMask(fire_mask).reduceRegion(
        reducer=ee.Reducer.max(),
        geometry=AOI,
        scale=500,
        maxPixels=1e9
    ).get("MaxFRP")

    frp_max = safe_number(frp_max, 0)
    fire_power = normalize(frp_max, FRP_MAX)

    # Build DAILY weather (ERA5)
    era = (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .filterDate(START, END)
        .filterBounds(AOI)
    )

    def daily_weather(date):
        date = ee.Date(date)

        img = (era
               .filterDate(date, date.advance(1, "day"))
               .filter(ee.Filter.calendarRange(9, 9, "hour"))
               .first())

        fallback = ee.Image.constant([273.15, 273.15, 0, 0, 0]).rename([
            "temperature_2m",
            "dewpoint_temperature_2m",
            "u_component_of_wind_10m",
            "v_component_of_wind_10m",
            "total_precipitation"
        ])

        img = ee.Image(ee.Algorithms.If(img, img, fallback))

        T  = img.select("temperature_2m")
        Td = img.select("dewpoint_temperature_2m")
        RH = rel_humidity_pct(T, Td)

        u = img.select("u_component_of_wind_10m")
        v = img.select("v_component_of_wind_10m")
        W = wind_speed_kmh(u, v)

        pr = (era.select("total_precipitation")
              .filterDate(date, date.advance(1, "day"))
              .sum()
              .multiply(1000))

        out = (to_celsius(T).rename("T")
               .addBands(RH.rename("RH"))
               .addBands(W.rename("W"))
               .addBands(pr.rename("R")))

        return out.set({
    "system:time_start": date.millis(),
    "month": date.get("month")  # 1..12
        })

    n_days = ee.Number(ee.Date(END).difference(ee.Date(START), "day")).toInt()
    dates = ee.List.sequence(0, n_days.subtract(1)).map(
        lambda d: ee.Date(START).advance(ee.Number(d), "day")
    )
    daily = ee.ImageCollection(dates.map(daily_weather))

    # ---- Iterate FWI
    FFMC0 = ee.Image.constant(85)
    DMC0  = ee.Image.constant(6)
    DC0   = ee.Image.constant(15)

    def step(img, state):
        state = ee.Dictionary(state)

        ffmc_prev = ee.Image(state.get("ffmc"))
        dmc_prev  = ee.Image(state.get("dmc"))
        dc_prev   = ee.Image(state.get("dc"))

        img = ee.Image(img)
        T  = img.select("T")
        RH = img.select("RH")
        W  = img.select("W")
        R  = img.select("R")

        ffmc_today = ffmc_next(ffmc_prev, T, RH, W, R)
        isi_today  = isi_from_ffmc_wind(ffmc_today, W)

        month_num = ee.Number(img.get("month"))
        dmc_today  = dmc_next(dmc_prev, T, RH, R, month_num)
        dc_today   = dc_next(dc_prev, T, R)

        bui_today  = bui_from_dmc_dc(dmc_today, dc_today)
        fwi_today  = fwi_from_isi_bui(isi_today, bui_today)

        out = (img
               .addBands(ffmc_today.rename("FFMC"))
               .addBands(dmc_today.rename("DMC"))
               .addBands(dc_today.rename("DC"))
               .addBands(bui_today.rename("BUI"))
               .addBands(isi_today.rename("ISI"))
               .addBands(fwi_today.rename("FWI")))

        col = ee.ImageCollection(state.get("col")).merge(ee.ImageCollection([out]))
        return ee.Dictionary({"ffmc": ffmc_today, "dmc": dmc_today, "dc": dc_today, "col": col})

    init = ee.Dictionary({"ffmc": FFMC0, "dmc": DMC0, "dc": DC0, "col": ee.ImageCollection([])})
    result_iter = ee.Dictionary(daily.sort("system:time_start").iterate(step, init))
    fwi_daily = ee.ImageCollection(result_iter.get("col"))

    day_img = ee.Image(fwi_daily.filterDate(DAY, DAY.advance(1, "day")).first())

    day_img = ee.Image(ee.Algorithms.If(
        day_img,
        day_img,
        ee.Image.constant([0, 0, 0, 0, 0, 0]).rename(["T","RH","W","R","ISI","FWI"])
    ))

    isi_day_img = day_img.select("ISI")
    fwi_day_img = day_img.select("FWI")

    # ---- Slope modifier
    dem = ee.Image("USGS/SRTMGL1_003")
    slope = ee.Terrain.slope(dem)
    slope_factor = slope.divide(45).clamp(0, 1).multiply(0.3).add(1.0)

    fwi_norm = fwi_day_img.divide(FWI_CAP).clamp(0, 1)
    spread_img = fwi_norm.multiply(slope_factor).clamp(0, 1)
    spread_index = mean_in_aoi(spread_img, AOI, 500)

    # ---- Exposure (WorldPop)
    population = (
        ee.ImageCollection("WorldPop/GP/100m/pop")
        .filterDate("2020-01-01", "2021-01-01")
        .mean()
    )

    pop_mean = population.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=AOI,
        scale=100,
        maxPixels=1e9
    ).values().get(0)

    pop_mean = safe_number(pop_mean, 0)
    exposure = normalize(pop_mean, POP_MAX)

    # ---- Threat Score
    threat_score = (
        fire_power.multiply(w_fire)
        .add(spread_index.multiply(w_spread))
        .add(exposure.multiply(w_exposure))
        .clamp(0, 1)
    )

    threat_level = ee.Algorithms.If(
        threat_score.lt(0.33), "منخفضة",
        ee.Algorithms.If(threat_score.lt(0.66), "متوسطة", "عالية")
    )

    # ---- Debug fire present
    fire_present = ee.Number(
        active_fire_img.select("FireMask").gte(7).reduceRegion(
            ee.Reducer.anyNonZero(),
            AOI,
            1000,
            maxPixels=1e9
        ).get("FireMask")
    )

    # ---- Output (JSON-ready)
    result = {
        "AOI_center": {"lon": lon, "lat": lat},
        "date": DAY.format("YYYY-MM-dd").getInfo(),

        "FRP_max_MW": frp_max.getInfo(),
        "fire_power_norm": fire_power.getInfo(),

        "ISI_day_mean_raw": mean_in_aoi(isi_day_img, AOI, 500).getInfo(),
        "FWI_day_mean_raw": mean_in_aoi(fwi_day_img, AOI, 500).getInfo(),

        "spread_index": spread_index.getInfo(),

        "population_mean": pop_mean.getInfo(),
        "exposure_norm": exposure.getInfo(),

        "threat_score": threat_score.getInfo(),
        "threat_level": threat_level.getInfo(),

        "fire_present": fire_present.getInfo(),
    }
    print(result)

    return result


# ======================
# Route يربطه بالفرونت
# ======================
@fire_threat_bp.route("/fire-threat", methods=["POST"])
def fire_threat_route():
    print(">>> fire-threat route HIT")

    data = request.get_json(silent=True) or {}

    lat = data.get("lat")
    lon = data.get("lon")
    when_iso = data.get("datetime")

    # ---- user weights ----
    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    w_fire = clamp(float(data.get("w_fire", W_FIRE)), 0.10, 1.0)
    w_spread = clamp(float(data.get("w_spread", W_SPREAD)), 0.10, 1.0)
    w_exposure = clamp(float(data.get("w_exposure", W_EXPOSURE)), 0.10, 1.0)

    total = w_fire + w_spread + w_exposure
    w_fire /= total
    w_spread /= total
    w_exposure /= total

    # ---- validation ----
    if lat is None or lon is None or not when_iso:
        return jsonify({"error": "Missing lat/lon/datetime"}), 400

    try:
        out = compute_fire_threat(float(lat), float(lon), str(when_iso), w_fire, w_spread, w_exposure)
        return jsonify(out), 200

    except Exception as e:
        tb = traceback.format_exc()
        print(">>> ERROR in fire-threat:\n", tb)
        return jsonify({"error": "calculation_failed"}), 500
