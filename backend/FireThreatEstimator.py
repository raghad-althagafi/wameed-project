from flask import Blueprint, request, jsonify
import ee
import traceback
from auth_utils import login_required

fire_threat_bp = Blueprint("fire_threat", __name__) #fire threat blue print

BUFFER_M = 500  

# Normalization caps
FRP_MAX = 200.0
POP_MAX = 500.0
FWI_CAP = 50.0

# Weights
W_FIRE = 0.25
W_SPREAD = 0.35
W_EXPOSURE = 0.40

# -----Utility Functions-------
def normalize(val, max_val):
    return ee.Number(val).divide(max_val).clamp(0, 1)

# Ensures value is not null (returns default if null) to prevent EE calculation errors
def safe_number(val, default=0):
    return ee.Number(ee.Algorithms.If(val, val, default))

def mean_in_aoi(img, aoi, scale, default=0): #Calculate the mean
    val = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e9
    ).values().get(0)
    return safe_number(val, default)  


# Helpers: units + RH
def to_celsius(k_img): # Convert temperature from Kelvin to Celsius
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

    # Calculate moisture increase after rainfall (standard FWI formula)
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
    m_dry = Ed.add(mr.subtract(Ed).multiply(ko.multiply(-1).exp())) # Moisture after drying
    m_wet = Ew.subtract(Ew.subtract(mr).multiply(kw.multiply(-1).exp())) # Moisture after wetting
    m_mid = mr # Keep moisture unchanged

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
    # moisture content
    m = ffmc.expression("147.2*(101.0-FFMC)/(59.5+FFMC)", {"FFMC": ffmc})
    # Calculate wind effect
    fW = ee.Image(W_kmh).expression("exp(0.05039*W)", {"W": W_kmh})
    # Calculate fuel moisture effect 
    fF = m.expression("91.9*exp(-0.1386*m)*(1 + (m**5.31)/(4.93e7))", {"m": m})

    isi = fW.multiply(fF).multiply(0.208)
    return isi.max(0)

# Calculate daylight hours based on latitude and date
def daylight_hours(lat, date):
    # Convert latitude from degrees to radians
    lat_rad = ee.Number(lat).multiply(3.14159265359).divide(180)
    # Get day of year
    day = ee.Date(date).getRelative("day", "year").add(1)
    # Approximate solar declination angle
    decl = ee.Number(23.44).multiply(3.14159265359).divide(180).multiply(
        ee.Number(360)
        .multiply(day.add(284))
        .divide(365)
        .multiply(3.14159265359)
        .divide(180)
        .sin()
    )
    # Calculate sunset hour angle
    x = lat_rad.tan().multiply(decl.tan()).multiply(-1).clamp(-1, 1)
    sunset_angle = x.acos()
    # Convert angle to daylight hours
    day_length = sunset_angle.multiply(24).divide(3.14159265359)
    return day_length

# DMC / DC / BUI / FWI
def dmc_next(dmc_prev, T_c, RH, R_mm, lat, date):
    # Convert previous DMC and weather inputs to Earth Engine images
    P0 = ee.Image(dmc_prev)
    T  = ee.Image(T_c)
    H  = ee.Image(RH)
    R  = ee.Image(R_mm)

    # Prevent temperature from going below -1.1 to keep the DMC equation valid
    T = T.max(-1.1)
    # Calculate daylight hours based on latitude and date
    Le = daylight_hours(lat, date)
    Le_img = ee.Image.constant(Le)

    # Calculate the daily drying rate based on temperature, humidity, and month
    K = ee.Image.constant(1.894).multiply(T.add(1.1)).multiply(ee.Image.constant(100).subtract(H)).multiply(Le_img).multiply(1e-6)

    # Check if rainfall is high enough to affect DMC
    rain_event = R.gt(1.5)

    # Calculate effective rainfall
    re = R.multiply(0.92).subtract(1.27).max(0)

    # Convert previous DMC to moisture content
    Mo = P0.expression("20 + exp(5.6348 - P/43.43)", {"P": P0})

    # Calculate b value for low DMC conditions
    b_13a = P0.expression("100/(0.5 + 0.3*P)", {"P": P0}) 
    # Calculate b value for medium DMC conditions              
    b_13b = P0.expression("14 - 1.3*log(P)", {"P": P0}) 
    # Calculate b value for high DMC conditions               
    b_13c = P0.expression("6.2*log(P) - 17.2", {"P": P0})              

    # Select the correct b equation based on the previous DMC value
    b = ee.Image(
        ee.Algorithms.If(
            P0.lte(33), b_13a,
            ee.Algorithms.If(P0.lte(65), b_13b, b_13c)
        )
    )

    # Calculate moisture content after rainfall
    Mr = Mo.add(re.multiply(1000).divide(ee.Image.constant(48.77).add(b.multiply(re))))

    # Convert moisture content after rainfall back to DMC
    Pr = Mr.expression("244.72 - 43.43*log(Mr - 20)", {"Mr": Mr})

    # Prevent DMC after rainfall from becoming negative
    Pr = Pr.max(0)

    # Use rainfall-adjusted DMC if rain is significant; otherwise use previous DMC
    P_base = ee.Image(ee.Algorithms.If(rain_event, Pr, P0))
    # Add the daily drying effect to get the updated DMC
    P = P_base.add(K.multiply(100))

    return P.max(0)

def dc_next(dc_prev, T, R):
    # Convert previous dc and weather inputs to Earth Engine images
    dc_prev = ee.Image(dc_prev)
    T = ee.Image(T)
    R = ee.Image(R)

    re = R.multiply(0.83).subtract(1.27).max(0) # Calculate effective rainfall for DC

    
    dc_rain = dc_prev.subtract(re.multiply(400).divide(re.add(800))) # Calculate DC after rainfall effect
    dc_no_rain = dc_prev.add(T.multiply(0.05)) # Calculate DC when there is no significant rain

    return ee.Image(ee.Algorithms.If(R.gt(2.8), dc_rain, dc_no_rain)).max(0)

def bui_from_dmc_dc(dmc, dc):
    # Convert to an Earth Engine image
    dmc = ee.Image(dmc)
    dc = ee.Image(dc)

    c04dc = dc.multiply(0.4) # Calculate 40% of DC, used as a threshold in the BUI formula
    c08dc = dc.multiply(0.8) # Calculate 80% of DC, used in the BUI formula

    # Calculate BUI when DMC is less than or equal to 40% of DC
    bui_case1 = dmc.multiply(c08dc).divide(dmc.add(c04dc))

    # Calculate ratio used in the second BUI case
    ratio = c08dc.divide(dmc.add(c04dc))
    # Calculate adjustment term for the second BUI case
    term = ee.Image.constant(1).subtract(ratio)

    # Calculate BUI when DMC is greater than 40% of DC
    bui_case2 = dmc.subtract(
        term.multiply(
            ee.Image.constant(0.92).add(
                ee.Image.constant(0.0114).multiply(dmc).pow(1.7)
            )
        )
    )
    # Select the correct BUI formula based on the relationship between DMC and DC
    bui = ee.Image(ee.Algorithms.If(dmc.lte(c04dc), bui_case1, bui_case2))
    return bui.max(0)

def fwi_from_isi_bui(isi, bui):
    # Convert to an Earth Engine image
    isi = ee.Image(isi)
    bui = ee.Image(bui)
    # Calculate drying factor when BUI is less than or equal to 80
    fD_case1 = ee.Image.constant(0.626).multiply(bui.pow(0.809)).add(2)
    # Calculate drying factor when BUI is greater than 80
    fD_case2 = ee.Image.constant(1000).divide(
        ee.Image.constant(25).add(
            ee.Image.constant(108.64).multiply(bui.multiply(-0.023).exp())
        )
    )
    # Select the correct drying factor based on the BUI value
    fD = ee.Image(ee.Algorithms.If(bui.lte(80), fD_case1, fD_case2))
    # Calculate the intermediate fire intensity value
    B = isi.multiply(fD).multiply(0.1)
    # Use B directly when it is less than or equal to 1
    fwi_case1 = B
    # Apply the final FWI transformation when B is greater than 1
    fwi_case2 = ee.Image.constant(2.72).multiply(
        ee.Image.constant(0.434).multiply(B.log()).pow(0.647)
    ).exp()

    # Select the correct FWI formula based on the B value
    fwi = ee.Image(ee.Algorithms.If(B.lte(1), fwi_case1, fwi_case2))
    return fwi.max(0)


def compute_threat_score(fire_power, spread_index, exposure, w_fire, w_spread, w_exposure):
    return (
        ee.Number(fire_power).multiply(w_fire)
        .add(ee.Number(spread_index).multiply(w_spread))
        .add(ee.Number(exposure).multiply(w_exposure))
        .clamp(0, 1)
    )

# Core compute
def compute_fire_threat(lat: float, lon: float, when_iso: str, w_fire: float, w_spread: float, w_exposure: float):
    # Create the area of interest around the selected location
    AOI = ee.Geometry.Point([lon, lat]).buffer(BUFFER_M)
    # Time setup 
    WHEN = ee.Date(when_iso)
    DAY_START = ee.Date(WHEN.format("YYYY-MM-dd"))
    DAY_END   = DAY_START.advance(1, "day")

    # Load VIIRS active fire data for the selected area and day
    active_fire_collection = (
        ee.ImageCollection("NASA/VIIRS/002/VNP14A1")
        .filterBounds(AOI)
        .filterDate(DAY_START, DAY_END)
    )

    # Use the first fire image if data exists; otherwise create an empty image, make sure its not null
    active_fire_img = ee.Image(
    ee.Algorithms.If(
        active_fire_collection.size().gt(0),
        active_fire_collection.first(),
        ee.Image.constant([0, 0]).rename(["FireMask", "MaxFRP"])
    )
)

    # Select active fire pixels only; FireMask values 7, 8, and 9 indicate active fire
    fire_mask = active_fire_img.select("FireMask").gte(7)
    # Select the fire radiative power band
    frp_img = active_fire_img.select("MaxFRP").updateMask(fire_mask)
    # Get the maximum FRP value inside the area of interest
    frp_max = frp_img.reduceRegion(
        reducer=ee.Reducer.max(),
        geometry=AOI,
        scale=1000,
        maxPixels=1e9
    ).get("MaxFRP")

    # Replace null FRP values with 0 to avoid calculation errors
    frp_max = safe_number(frp_max, 0)
    fire_power = normalize(frp_max, FRP_MAX)

    # ---------- FWI spin-up (daily, 14 days before fire day) ----------
    FWI_START = DAY_START.advance(-14, "day")
    FWI_END   = DAY_END

    # Load ERA5-Land weather data
    era_ic = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
              .filterBounds(AOI)
              .filterDate(FWI_START, FWI_END))

    # Build a daily weather image for each day
    def daily_fwi_weather(date):
        # Convert the input date to an Earth Engine Date object
        date = ee.Date(date)
        # daily mean for T, Td, u, v (stable)
        day_mean = era_ic.filterDate(date, date.advance(1, "day")).mean()
        T_k  = day_mean.select("temperature_2m")
        Td_k = day_mean.select("dewpoint_temperature_2m")
        RH   = rel_humidity_pct(T_k, Td_k)
        u = day_mean.select("u_component_of_wind_10m")
        v = day_mean.select("v_component_of_wind_10m")
        W = wind_speed_kmh(u, v)

        # Calculate total daily precipitation
        R = (era_ic.select("total_precipitation")
             .filterDate(date, date.advance(1, "day"))
             .sum()
             .multiply(1000))
        # Create one daily weather image containing the required FWI inputs
        out = (to_celsius(T_k).rename("T")
               .addBands(RH.rename("RH"))
               .addBands(W.rename("W"))
               .addBands(R.rename("R")))
        # Add date metadata to the image so it can be sorted and filtered later
        return out.set({
            "system:time_start": date.millis(),
            "month": date.get("month")  # 1..12
        })
    # Create a list of dates from FWI_START to FWI_END
    n_days = ee.Number(FWI_END.difference(FWI_START, "day")).toInt()
    dates = ee.List.sequence(0, n_days.subtract(1)).map(
        lambda d: ee.Date(FWI_START).advance(ee.Number(d), "day")
    )
    daily = ee.ImageCollection(dates.map(daily_fwi_weather))

    # ---- Iterate FWI over DAILY collection ----
    # Initial values
    FFMC0 = ee.Image.constant(85)
    DMC0  = ee.Image.constant(6)
    DC0   = ee.Image.constant(15)

    def step(img, state):
        # Convert the current state to an Earth Engine dictionary
        state = ee.Dictionary(state)
        # Get the previous day's FWI component values
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

        date = ee.Date(img.get("system:time_start"))
        dmc_today = dmc_next(dmc_prev, T, RH, R, lat, date)
        dc_today  = dc_next(dc_prev, T, R)

        bui_today = bui_from_dmc_dc(dmc_today, dc_today)
        fwi_today = fwi_from_isi_bui(isi_today, bui_today)
        # Add the calculated FWI components to the image
        out = (img
               .addBands(ffmc_today.rename("FFMC"))
               .addBands(dmc_today.rename("DMC"))
               .addBands(dc_today.rename("DC"))
               .addBands(bui_today.rename("BUI"))
               .addBands(isi_today.rename("ISI"))
               .addBands(fwi_today.rename("FWI")))
        # Add the updated daily image to the output collection
        col = ee.ImageCollection(state.get("col")).merge(ee.ImageCollection([out]))
        return ee.Dictionary({"ffmc": ffmc_today, "dmc": dmc_today, "dc": dc_today, "col": col})

    # Create the initial state for the FWI iteration
    init = ee.Dictionary({"ffmc": FFMC0, "dmc": DMC0, "dc": DC0, "col": ee.ImageCollection([])})
    # Apply the step function day by day over the daily weather collection
    result_iter = ee.Dictionary(daily.sort("system:time_start").iterate(step, init))
    # Extract the collection that contains the calculated daily FWI values
    fwi_daily = ee.ImageCollection(result_iter.get("col"))

    day_img = ee.Image(fwi_daily.filterDate(DAY_START, DAY_END).first())
    # If no image is found for that day, use a default image with zero values
    day_img = ee.Image(ee.Algorithms.If(
        day_img,
        day_img,
        ee.Image.constant([0, 0, 0, 0, 0, 0]).rename(["T","RH","W","R","ISI","FWI"])
    ))

    fwi_day_img = day_img.select("FWI")

    # ---- Slope modifier
    # Load the Digital Elevation Model (DEM) data
    dem = ee.Image("USGS/SRTMGL1_003")
    # Calculate the slope degree from the elevation data
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

    pop_mean = mean_in_aoi(population, AOI, 100)
    exposure = normalize(pop_mean, POP_MAX)

    # Threat Score
    threat_score = compute_threat_score(
    fire_power, spread_index, exposure,
    w_fire, w_spread, w_exposure
    )

    threat_level = ee.Algorithms.If(
        threat_score.lt(0.33), "منخفضة",
        ee.Algorithms.If(threat_score.lt(0.66), "متوسطة", "عالية")
    )

    # Output
    result = {
        "threat_score": threat_score.getInfo(),
        "threat_level": threat_level.getInfo(),
    }

    return result


# Route
@fire_threat_bp.route("/fire-threat", methods=["POST"])
@login_required
def fire_threat_route():

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
