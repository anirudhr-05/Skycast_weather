#!/usr/bin/env python3
"""
SkyCast Weather  (v1.0, single file)
====================================
Run:   python skycast_weather.py        (Python 3.8+, no pip installs)
Open:  http://127.0.0.1:8000

"SkyCast" is the small JSON API in this file. It uses two Open-Meteo services:
  forecast (weather)  and  air quality (AQI, pollutants)
Endpoints:  /api/skycast             info
            /api/skycast/weather?lat=13.08&lon=80.27&name=Chennai
            /api/skycast/search?q=chennai
If the internet is down, it falls back to built-in demo data automatically.
"""
import json, math, random, threading, time, webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import urlopen

PORT, TTL, TS, INF = 8000, 120, "%Y-%m-%dT%H:%M", float("inf")
GEO = "https://geocoding-api.open-meteo.com/v1/search"
FC = "https://api.open-meteo.com/v1/forecast"
AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"
_cache = {}


def fetch(url, **p):                                   # one gatekeeper + 2-minute cache
    k = url + urlencode(sorted(p.items()))
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    with urlopen(url + "?" + urlencode(p), timeout=10) as r:
        d = json.load(r)
    _cache[k] = (time.time(), d)
    return d


# ---------- demo data (same shape as the real API) ----------
def demo_forecast(lat, lon):
    now = datetime.utcnow() + timedelta(hours=round(lon / 15))
    t0, rnd = now.replace(hour=0, minute=0, second=0, microsecond=0), random.Random(int(lat * 10))
    H = {k: [] for k in ("time", "temperature_2m", "relative_humidity_2m", "precipitation_probability", "precipitation",
                         "weather_code", "wind_speed_10m", "wind_gusts_10m", "uv_index", "cloud_cover", "visibility",
                         "is_day", "dew_point_2m")}
    for i in range(168):
        t = t0 + timedelta(hours=i); cl = 50 + 40 * math.sin(i / 9 + lat)
        pop = max(0, min(100, 60 * math.sin(i / 11 + 1) + 25 + rnd.gauss(0, 5)))
        pr = round(max(0, (pop - 55) / 15), 1); day = 6 <= t.hour < 18
        tp = 28 - abs(lat) * .3 + 4 * math.sin(math.pi * (t.hour - 9) / 12 * 1.0) - cl / 40
        for k, v in zip(H, (t.strftime(TS), round(tp, 1), round(78 - (tp - 28) * 2), round(pop), pr,
                            95 if pr > 5 else 63 if pr > 1 else 61 if pr > 0 else 3 if cl > 80 else 2 if cl > 50 else 0,
                            round(10 + 5 * math.sin(i / 13), 1), round(18 + 7 * math.sin(i / 13), 1),
                            round(max(0, 9 * math.sin(math.pi * (t.hour - 6) / 12)) * (1 - cl / 130), 1) if day else 0,
                            round(cl), round(max(2000, 24000 - pop * 160)), int(day), round(tp - 4, 1))):
            H[k].append(v)
    D = {k: [] for k in ("time", "weather_code", "temperature_2m_max", "temperature_2m_min",
                         "precipitation_probability_max", "sunrise", "sunset", "uv_index_max")}
    for d in range(7):
        s = slice(d * 24, d * 24 + 24); date = H["time"][d * 24][:10]
        for k, v in zip(D, (date, max(H["weather_code"][s]), max(H["temperature_2m"][s]), min(H["temperature_2m"][s]),
                            max(H["precipitation_probability"][s]), date + "T06:05", date + "T17:43", max(H["uv_index"][s]))):
            D[k].append(v)
    h = int(now.hour)
    cur = {"time": now.strftime(TS), "temperature_2m": H["temperature_2m"][h], "apparent_temperature": H["temperature_2m"][h] + 2,
           "relative_humidity_2m": H["relative_humidity_2m"][h], "wind_speed_10m": H["wind_speed_10m"][h],
           "wind_gusts_10m": H["wind_gusts_10m"][h], "weather_code": H["weather_code"][h], "is_day": H["is_day"][h],
           "precipitation": H["precipitation"][h], "pressure_msl": 1008, "wind_direction_10m": 70}
    return {"current": cur, "hourly": H, "daily": D}


def demo_air(fc):
    t = fc["hourly"]["time"]
    return {"current": {"us_aqi": 57, "pm2_5": 24, "pm10": 44, "ozone": 51, "nitrogen_dioxide": 53},
            "hourly": {"time": t, "us_aqi": [round(57 + 20 * math.sin(i / 7)) for i in range(len(t))]}}


# ---------- SkyCast core ----------
def parse(s): return datetime.strptime(s[:16], TS)
def hr12(s): d = parse(s); return f"{d.hour % 12 or 12} {'AM' if d.hour < 12 else 'PM'}"
def trap(x, a, b, c, d):                                # 1.0 inside ideal range, 0.0 beyond the bad limit
    if x <= a or x >= d: return 0.0
    return (x - a) / (b - a) if x < b else 1.0 if x <= c else (d - x) / (d - c)

LOW = lambda ok, bad: (-INF, -INF, ok, bad)             # smaller is better
HIGH = lambda bad, ok: (bad, ok, INF, INF)              # larger is better
LBL = dict(t="temperature", h="humidity", pop="rain chance", pr="rainfall", w="wind", g="gusts",
           uv="UV", cl="cloud cover", vis="visibility", aqi="air quality")
ACT = {  # activities are DATA: (field, weight, trapezoid) + vetoes (field, above, cap, why)
    "run": dict(title="Run", icon="🏃", n=2, hrs=[(5, 21)],
                rules=[("t", 3, (8, 14, 24, 32)), ("h", 2, (15, 35, 70, 95)), ("uv", 2, LOW(4, 9)),
                       ("pop", 3, LOW(15, 55)), ("aqi", 2, LOW(50, 150))], veto=[("pop", 60, 35, "rain is likely")]),
    "laundry": dict(title="Drying clothes", icon="👕", n=3, hrs=[(8, 17)], day=True,
                    rules=[("h", 3, LOW(55, 90)), ("w", 2, (2, 8, 30, 50)), ("uv", 2, HIGH(.5, 4)), ("pop", 4, LOW(5, 30))],
                    veto=[("pop", 40, 30, "rain would wet the clothes")]),
    "commute": dict(title="Two-wheeler commute", icon="🛵", n=1, hrs=[(6, 22)],
                    rules=[("pop", 4, LOW(10, 50)), ("pr", 3, LOW(.1, 2)), ("g", 3, LOW(20, 50)), ("vis", 2, HIGH(1000, 5000))],
                    veto=[("pr", 2, 20, "heavy rain")]),
    "spray": dict(title="Crop spraying", icon="🌾", n=2, hrs=[(5, 10), (16, 19)],
                  rules=[("w", 4, (2, 5, 15, 25)), ("pop", 4, LOW(5, 20)), ("t", 2, (10, 18, 30, 35)), ("g", 2, LOW(15, 30))],
                  veto=[("pop", 30, 20, "rain may wash it off"), ("w", 25, 20, "spray would drift")]),
    "stars": dict(title="Stargazing", icon="🔭", n=2, hrs=None, night=True,
                  rules=[("cl", 5, LOW(10, 60)), ("pop", 3, LOW(10, 40)), ("vis", 1, HIGH(5000, 15000)), ("aqi", 2, LOW(50, 150))],
                  veto=[("cl", 70, 20, "the sky is mostly covered")]),
}


def score_hour(h, a):
    tot = wt = 0.0
    for f, w, shp in a["rules"]:
        if h.get(f) is not None: tot += w * trap(h[f], *shp); wt += w
    s = 100 * tot / wt if wt else 0
    for f, above, cap, _ in a["veto"]:
        if h.get(f) is not None and h[f] > above: s = min(s, cap)
    return s


def allowed(h, a):
    hr = int(h["time"][11:13])
    if a.get("day") and not h["day"]: return False
    if a.get("night") and h["day"]: return False
    return True if not a["hrs"] else any(x <= hr < y for x, y in a["hrs"])


def find_windows(hrs, key, top=3):
    a, cands = ACT[key], []
    for i in range(len(hrs) - a["n"] + 1):
        seg = hrs[i:i + a["n"]]
        if not all(allowed(h, a) for h in seg): continue
        sc = [score_hour(h, a) for h in seg]
        base, good, bad = 0.7 * sum(sc) / len(sc) + 0.3 * min(sc), [], []
        for f, w, shp in a["rules"]:
            v = [h[f] for h in seg if h.get(f) is not None]
            if v:
                avg = sum(v) / len(v); s = trap(avg, *shp)
                txt = f"{LBL[f]} {avg:.0f}" + ("%" if f in ("h", "pop", "cl") else "")
                (good if s >= .8 else bad if s < .5 else []).append(txt)
        bad += [why for f, ab, _, why in a["veto"] if any(h.get(f) is not None and h[f] > ab for h in seg)]
        cands.append(dict(start=seg[0]["time"], end=(parse(seg[-1]["time"]) + timedelta(hours=1)).strftime(TS),
                          score=int(max(0, min(100, base + .5))), good=good[:3], bad=bad, i0=i, i1=i + a["n"]))
    cands.sort(key=lambda c: -c["score"]); out = []
    for c in cands:
        if all(c["i1"] <= o["i0"] or c["i0"] >= o["i1"] for o in out): out.append(c)
        if len(out) == top: break
    return dict(title=a["title"], icon=a["icon"], windows=out)


def alerts(cur, hrs, aq):
    out, nxt = [], hrs[:6]
    pk = max(nxt, key=lambda h: h["pop"]) if nxt else None
    if cur["precip"] >= .1: out.append(("warn", "It is raining now", "Carry an umbrella; it may continue for a couple of hours."))
    elif pk and pk["pop"] >= 60: out.append(("warn", "Rain likely soon", f"{pk['pop']:.0f}% chance around {hr12(pk['time'])}."))
    if cur["feels"] >= 38: out.append(("danger", "Heat caution", f"Feels like {cur['feels']:.0f}°C. Drink water, avoid midday sun."))
    if cur["uv"] >= 8: out.append(("warn", "Very high UV", f"UV index {cur['uv']:.0f}. Use sunscreen."))
    if cur["gust"] >= 45: out.append(("warn", "Strong gusts", f"Up to {cur['gust']:.0f} km/h. Take care on two-wheelers."))
    if aq.get("aqi") and aq["aqi"] >= 101: out.append(("danger" if aq["aqi"] >= 151 else "warn", "Poor air quality", f"AQI {aq['aqi']:.0f}. Limit outdoor exercise."))
    if nxt and cur["temp"] - min(h["t"] for h in nxt) >= 6: out.append(("info", "Temperature drop", "Down 6°C or more in the next 6 hours."))
    return out or [("ok", "All calm", "No alerts. Conditions look calm for the next few hours.")]


def get_weather(lat, lon, name="", region="", country=""):
    src = "SkyCast · Open-Meteo (live)"
    try:                                                 # forecast
        f = fetch(FC, latitude=lat, longitude=lon, timezone="auto", forecast_days=7,
                  current="temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m,"
                          "wind_gusts_10m,precipitation,pressure_msl,wind_direction_10m",
                  hourly="temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,weather_code,"
                         "wind_speed_10m,wind_gusts_10m,uv_index,cloud_cover,visibility,is_day,dew_point_2m",
                  daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset,uv_index_max")
    except Exception:
        f, src = demo_forecast(lat, lon), "SkyCast · demo data (offline)"
    try:                                                 # air quality (optional)
        a = fetch(AQ, latitude=lat, longitude=lon, timezone="auto", forecast_days=7,
                  current="us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide", hourly="us_aqi")
    except Exception:                                    # never mix fake AQI with live weather
        a = demo_air(f) if "demo" in src else {"current": {}, "hourly": {"time": [], "us_aqi": []}}
    by_t = dict(zip(a["hourly"]["time"], a["hourly"]["us_aqi"])); H = f["hourly"]; v = lambda k, i, d=0: H[k][i] if H[k][i] is not None else d
    hours = [dict(time=H["time"][i], t=v("temperature_2m", i), h=v("relative_humidity_2m", i), pop=v("precipitation_probability", i),
                  pr=v("precipitation", i), code=int(v("weather_code", i)), w=v("wind_speed_10m", i), g=v("wind_gusts_10m", i),
                  uv=v("uv_index", i), cl=v("cloud_cover", i), vis=v("visibility", i, 24000), day=bool(v("is_day", i, 1)),
                  aqi=by_t.get(H["time"][i])) for i in range(len(H["time"]))]
    c = f["current"]; stamp = c["time"][:13] + ":00"
    i0 = next((i for i, h in enumerate(hours) if h["time"] >= stamp), 0); ahead = hours[i0:i0 + 48]
    ac = a.get("current") or {}
    aq = dict(aqi=ac.get("us_aqi"), pm25=ac.get("pm2_5"), pm10=ac.get("pm10"), o3=ac.get("ozone"), no2=ac.get("nitrogen_dioxide"))
    d = f["daily"]; days = [dict(date=d["time"][i], code=int(d["weather_code"][i] or 0), hi=d["temperature_2m_max"][i],
                                 lo=d["temperature_2m_min"][i], pop=d["precipitation_probability_max"][i] or 0,
                                 sr=d["sunrise"][i], ss=d["sunset"][i], uv=d["uv_index_max"][i] or 0) for i in range(len(d["time"]))]
    now = dict(time=c["time"], temp=c["temperature_2m"], feels=c["apparent_temperature"], hum=c["relative_humidity_2m"],
               wind=c["wind_speed_10m"], gust=c["wind_gusts_10m"], dir=c.get("wind_direction_10m"), code=int(c["weather_code"]),
               day=bool(c["is_day"]), precip=c["precipitation"], pressure=c.get("pressure_msl"), uv=ahead[0]["uv"] if ahead else 0,
               vis=ahead[0]["vis"] if ahead else 0, dew=H["dew_point_2m"][i0],
               rain24=round(sum(h["pr"] for h in ahead[:24]), 1))
    best = find_windows(ahead, "run", 1)["windows"]
    story = (f"{'Rain is most likely around ' + hr12(max(ahead[:12], key=lambda h: h['pop'])['time']) + '.' if ahead and max(h['pop'] for h in ahead[:12]) >= 50 else 'Mostly dry for the next 12 hours.'}"
             + (f" Best time to run: {parse(best[0]['start']):%a} {hr12(best[0]['start'])} (score {best[0]['score']})." if best else ""))
    return dict(api="SkyCast", source=src, fetched=time.time(), demo="demo" in src,
                city=dict(name=name or f"{lat:.2f},{lon:.2f}", region=region, country=country, lat=lat, lon=lon),
                now=now, aq=aq, hours=ahead[:36], days=days, alerts=[dict(level=l, title=t, text=x) for l, t, x in alerts(now, ahead, aq)],
                windows={k: find_windows(ahead, k) for k in ACT}, story=story)


def search_cities(q):
    try:
        r = fetch(GEO, name=q, count=5, language="en").get("results") or []
        return [dict(name=x["name"], region=x.get("admin1", ""), country=x.get("country", ""), lat=x["latitude"], lon=x["longitude"]) for x in r]
    except Exception:
        demo = [("Chennai", "Tamil Nadu", "India", 13.08, 80.27), ("Mumbai", "Maharashtra", "India", 19.08, 72.88),
                ("Delhi", "Delhi", "India", 28.61, 77.21), ("London", "England", "United Kingdom", 51.51, -.13),
                ("Bengaluru", "Karnataka", "India", 12.97, 77.59), ("New York", "New York", "United States", 40.71, -74.01)]
        return [dict(name=n, region=r, country=c, lat=la, lon=lo) for n, r, c, la, lo in demo if q.lower() in n.lower()]


# ---------- the dashboard page (served at /) ----------
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SkyCast Weather</title><style>
:root{--bg:#0b1020;--p:#121a2e;--p2:#172038;--b:#223052;--tx:#e8edf7;--mu:#8793ad;--ac:#38a3ff;--or:#fb923c;--gn:#34d399;--rd:#f87171;--yl:#fbbf24}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:flex;min-height:100vh}
aside{width:240px;background:#0d1426;border-right:1px solid var(--b);padding:18px 14px;position:sticky;top:0;height:100vh;overflow:auto;flex-shrink:0}
.logo{font-size:20px;font-weight:800;margin-bottom:2px}.sub{color:var(--mu);font-size:12px}.sec{color:var(--mu);font-size:11px;letter-spacing:.08em;margin:22px 0 8px}
.nav{padding:10px 12px;border-radius:8px;cursor:pointer;color:var(--mu)}.nav.on{background:#16264a;color:#fff;border-left:3px solid var(--ac)}.nav:hover{color:#fff}
.loc{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:8px;cursor:pointer}.loc:hover,.loc.on{background:var(--p2)}.loc b{font-weight:600}.loc small{color:var(--mu);display:block}.loc span{font-size:18px;color:var(--gn);font-weight:700}
.x{color:var(--mu);margin-left:6px;font-size:12px}main{flex:1;padding:22px;min-width:0}
.top{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:18px}h1{margin:0;font-size:26px}
.bar{display:flex;gap:8px;align-items:center;position:relative}input{background:var(--p);border:1px solid var(--b);color:var(--tx);padding:9px 12px;border-radius:8px;width:260px}
button{background:var(--p);border:1px solid var(--b);color:var(--tx);padding:8px 13px;border-radius:8px;cursor:pointer}button.on{background:var(--ac);color:#04121f;border-color:var(--ac);font-weight:700}
.res{position:absolute;top:42px;left:0;width:300px;background:var(--p2);border:1px solid var(--b);border-radius:8px;z-index:9;overflow:hidden}.res div{padding:9px 12px;cursor:pointer}.res div:hover{background:#1f2c4d}
.grid{display:grid;gap:14px;grid-template-columns:repeat(12,1fr)}.card{background:var(--p);border:1px solid var(--b);border-radius:10px;padding:16px;min-width:0}
.c4{grid-column:span 4}.c5{grid-column:span 5}.c7{grid-column:span 7}.c8{grid-column:span 8}.c3{grid-column:span 3}.c6{grid-column:span 6}.c12{grid-column:span 12}
@media(max-width:1100px){.c3,.c4,.c5,.c6,.c7,.c8{grid-column:span 12}aside{display:none}}
h3{margin:0 0 12px;font-size:15px}.big{font-size:64px;font-weight:700;line-height:1}.big small{font-size:22px;color:var(--mu);font-weight:500}.ic{font-size:64px;float:right}
.mu{color:var(--mu)}.pill{font-size:11px;padding:2px 8px;border-radius:4px;background:#1b3a66;color:var(--ac);margin-left:8px}.row{display:flex;gap:16px;flex-wrap:wrap;color:var(--mu);margin-top:8px;font-size:13px}
svg text{fill:#cbd5e1;font-size:11px}svg .m{fill:var(--mu)}.strip{display:flex;gap:8px;overflow-x:auto}.hr{min-width:62px;text-align:center;padding:8px 4px;border-radius:8px;background:var(--p2)}.hr.now{outline:1px solid var(--ac)}.hr b{display:block;margin:2px 0}.hr i{font-style:normal;color:var(--ac);font-size:11px}
.d{display:grid;grid-template-columns:58px 28px 40px 1fr 40px;gap:8px;align-items:center;padding:7px 0}.rng{height:6px;border-radius:4px;background:#222f50;position:relative}.rng i{position:absolute;top:0;bottom:0;border-radius:4px;background:linear-gradient(90deg,var(--gn),var(--yl),var(--or))}
.stat{font-size:12px;color:var(--mu);letter-spacing:.05em}.val{font-size:28px;font-weight:700;margin:6px 0}.val small{font-size:13px;color:var(--mu);font-weight:400}
.meter{height:7px;background:#222f50;border-radius:4px;overflow:hidden;margin-top:6px}.meter i{display:block;height:100%}
.al{padding:10px 12px;border-radius:8px;margin-bottom:8px;background:var(--p2);border-left:4px solid var(--mu)}.al.warn{border-color:var(--yl)}.al.danger{border-color:var(--rd)}.al.ok{border-color:var(--gn)}.al.info{border-color:var(--ac)}.al b{display:block}
.win{display:grid;grid-template-columns:70px 1fr;gap:12px;padding:12px 0;border-top:1px solid var(--b)}.sc{font-size:30px;font-weight:700;text-align:center}.g{color:var(--gn);font-size:13px}.w{color:var(--yl);font-size:13px}
.tile{cursor:pointer}.tile:hover{border-color:var(--ac)}.foot{margin-top:16px;color:var(--mu);font-size:12px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
</style></head><body>
<aside><div class="logo">⛅ SkyCast</div><div class="sub">Weather Intelligence</div>
<div class="sec">MENU</div><div id="nav"></div><div class="sec">SAVED LOCATIONS</div><div id="locs"></div>
<div class="sec">DATA PROVIDER</div><div class="sub" id="prov">…</div></aside>
<main><div class="top"><div><h1 id="hi"></h1><div class="sub" id="clock"></div></div>
<div class="bar"><input id="q" placeholder="Search city to add…"><div class="res" id="res" hidden></div>
<button id="uC" class="on">°C</button><button id="uF">°F</button><button id="rf">⟳ Refresh</button></div></div>
<div id="view"></div><div class="foot"><span id="st"></span><span>Auto-refresh every 5 min · SkyCast API v1</span></div></main>
<script>
const $=s=>document.querySelector(s),E=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const DEF=[{name:'Chennai',region:'Tamil Nadu',country:'India',lat:13.08,lon:80.27},{name:'Bengaluru',region:'Karnataka',country:'India',lat:12.97,lon:77.59},{name:'Mumbai',region:'Maharashtra',country:'India',lat:19.08,lon:72.88},{name:'Delhi',region:'Delhi',country:'India',lat:28.61,lon:77.21},{name:'London',region:'England',country:'United Kingdom',lat:51.51,lon:-.13}];
const SAME=(a,b)=>a.name.toLowerCase()==b.name.toLowerCase()&&(a.country||'')==(b.country||'');
let S={unit:'C',view:'home',cur:0,data:{},act:'run',cities:(()=>{let l;try{l=JSON.parse(localStorage.tt)||DEF}catch(e){l=DEF}return l.filter((c,i)=>l.findIndex(x=>SAME(x,c))==i)})()};
const K=c=>c.lat.toFixed(2)+','+c.lon.toFixed(2),save=()=>{try{localStorage.tt=JSON.stringify(S.cities)}catch(e){}};
const T=c=>Math.round(S.unit=='C'?c:c*1.8+32)+'°',hh=s=>{let h=+s.slice(11,13);return (h%12||12)+(h<12?' AM':' PM')},dn=d=>new Date(d+'T00:00').toLocaleDateString('en',{weekday:'short'});
const ICON=(c,d=1)=>c<2?(d?'☀️':'🌙'):c==2?(d?'⛅':'☁️'):c==3?'☁️':c<50?'🌫️':c<70||(c>=80&&c<83)?'🌧️':c<80||c>=85&&c<90?'❄️':'⛈️';
const WMO={0:'Clear sky',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Fog',51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',71:'Light snow',73:'Snow',75:'Heavy snow',80:'Rain showers',81:'Rain showers',82:'Violent showers',95:'Thunderstorm',96:'Thunderstorm, hail',99:'Thunderstorm, hail'};
const AQL=a=>a==null?'unavailable':a<=50?'Good':a<=100?'Moderate':a<=150?'Sensitive':a<=200?'Unhealthy':'Very unhealthy',AQC=a=>a<=50?'#34d399':a<=100?'#fbbf24':a<=150?'#fb923c':'#f87171';
async function load(c,force){try{const r=await fetch(`/api/skycast/weather?lat=${c.lat}&lon=${c.lon}&name=${encodeURIComponent(c.name)}&region=${encodeURIComponent(c.region)}&country=${encodeURIComponent(c.country)}`);S.data[K(c)]=await r.json()}catch(e){}render()}
const all=()=>Promise.all(S.cities.map(c=>load(c)));
function chart(hs){const W=700,H=210,p=30,v=hs.map(h=>S.unit=='C'?h.t:h.t*1.8+32),lo=Math.min(...v)-1,hi=Math.max(...v)+1,x=i=>p+i*(W-2*p)/(v.length-1),y=a=>p+(H-2*p-8)*(1-(a-lo)/(hi-lo)),pts=v.map((a,i)=>x(i)+','+y(a)).join(' ');
return `<svg viewBox="0 0 ${W} ${H}" width="100%"><polygon points="${p},${H-p+6} ${pts} ${x(v.length-1)},${H-p+6}" fill="rgba(251,146,60,.14)"/><polyline points="${pts}" fill="none" stroke="#fb923c" stroke-width="2.5" stroke-linejoin="round"/>`+v.map((a,i)=>i%3?'':`<circle cx="${x(i)}" cy="${y(a)}" r="3.5" fill="#fb923c"/><text x="${x(i)}" y="${y(a)-10}" text-anchor="middle">${Math.round(a)}°</text><text class="m" x="${x(i)}" y="${H-6}" text-anchor="middle">${i?hh(hs[i].time):'Now'}</text>`).join('')+'</svg>'}
const hero=d=>{const n=d.now,t=d.days[0];return `<div class="card"><span class="ic">${ICON(n.code,n.day)}</span><div class="mu">● ${E(d.city.name)} <span class="mu">${E(d.city.region)}</span><span class="pill">NOW</span></div>
<div class="big" style="margin-top:14px">${T(n.temp)}<small>${S.unit}</small></div><h3 style="margin:10px 0 2px;font-size:20px">${WMO[n.code]||'—'}</h3>
<div class="row"><span>Feels ${T(n.feels)}</span><span>H ${T(t.hi)} · L ${T(t.lo)}</span><span>Humidity ${Math.round(n.hum)}%</span><span>Wind ${Math.round(n.wind)} km/h</span></div>
<p class="mu" style="margin:12px 0 0">${E(d.story)}</p><div class="sub" style="margin-top:8px">Updated ${new Date(d.fetched*1e3).toLocaleTimeString()} · ${E(d.source)}</div></div>`};
const alertsH=d=>`<div class="card"><h3>Weather alerts <span class="pill">${d.alerts.filter(a=>a.level!='ok').length} active</span></h3>${d.alerts.map(a=>`<div class="al ${a.level}"><b>${E(a.title)}</b>${E(a.text)}</div>`).join('')}</div>`;
const strip=d=>`<div class="card"><h3>Hourly forecast</h3><div class="strip">${d.hours.slice(0,14).map((h,i)=>`<div class="hr ${i?'':'now'}">${i?hh(h.time):'Now'}<b>${ICON(h.code,h.day)}</b>${T(h.t)}<br><i>☂ ${Math.round(h.pop)}%</i></div>`).join('')}</div></div>`;
const week=d=>{const lo=Math.min(...d.days.map(x=>x.lo)),hi=Math.max(...d.days.map(x=>x.hi));return `<div class="card"><h3>7-day forecast</h3>${d.days.map((x,i)=>`<div class="d"><b>${i?dn(x.date):'Today'}</b><span>${ICON(x.code)}</span><span class="mu">${T(x.lo)}</span><div class="rng"><i style="left:${(x.lo-lo)/(hi-lo||1)*100}%;right:${100-(x.hi-lo)/(hi-lo||1)*100}%"></i></div><span>${T(x.hi)}</span></div>`).join('')}</div>`};
const aqH=d=>{const a=d.aq,r=[['PM2.5',a.pm25,60],['PM10',a.pm10,150],['O₃',a.o3,180],['NO₂',a.no2,200]];return `<div class="card"><h3>Air quality <span class="pill" style="color:${AQC(a.aqi||0)}">AQI ${a.aqi??'n/a'} · ${AQL(a.aqi)}</span></h3>${r.map(([n,v,m])=>`<div style="margin:9px 0"><div style="display:flex;justify-content:space-between"><b>${n}</b><span class="mu">${v??'–'} µg/m³</span></div><div class="meter"><i style="width:${Math.min(100,(v||0)/m*100)}%;background:${AQC((v||0)/m*150)}"></i></div></div>`).join('')}</div>`};
const tiles=d=>{const n=d.now,t=d.days[0],T2=(a,b,c,e='')=>`<div class="card"><div class="stat">${a}</div><div class="val">${b}</div><div class="mu">${c}</div>${e}</div>`;
return [T2('UV INDEX',Math.round(n.uv),n.uv>=8?'Very high · SPF 50+':n.uv>=6?'High · Use SPF 30+':n.uv>=3?'Moderate':'Low',`<div class="meter"><i style="width:${n.uv/11*100}%;background:linear-gradient(90deg,#34d399,#fbbf24,#f87171)"></i></div>`),
T2('WIND',`${Math.round(n.wind)} <small>km/h</small>`,`Gusts ${Math.round(n.gust)} km/h`),T2('HUMIDITY',`${Math.round(n.hum)} <small>%</small>`,`Dew point ${T(n.dew)}`,`<div class="meter"><i style="width:${n.hum}%;background:var(--ac)"></i></div>`),
T2('AIR QUALITY',`${d.aq.aqi??'–'} <small>AQI</small>`,AQL(d.aq.aqi)),T2('SUNRISE & SUNSET',t.sr.slice(11,16),'Sunset '+t.ss.slice(11,16)),
T2('PRESSURE',`${Math.round(n.pressure||0)} <small>hPa</small>`,'Mean sea level'),T2('VISIBILITY',`${(n.vis/1000).toFixed(1)} <small>km</small>`,n.vis<5000?'Reduced visibility':'Clear'),T2('PRECIPITATION',`${n.rain24} <small>mm</small>`,'Expected in next 24 h')].map(x=>x.replace('class="card"','class="card c3"')).join('')};
const acts=d=>{const A=d.windows[S.act];return `<div class="card c12"><h3>Activity Window Finder — best windows in the next 48 hours</h3><div class="bar" style="margin-bottom:8px;flex-wrap:wrap">${Object.entries(d.windows).map(([k,v])=>`<button class="${k==S.act?'on':''}" onclick="S.act='${k}';render()">${v.icon} ${v.title}</button>`).join('')}</div>
${A.windows.length?A.windows.map((w,i)=>`<div class="win"><div class="sc" style="color:${w.score>=80?'#34d399':w.score>=60?'#a3e635':w.score>=40?'#fbbf24':'#f87171'}">${w.score}<div class="sub">${w.score>=80?'Great':w.score>=60?'Good':w.score>=40?'Okay':'Poor'}</div></div><div><b>#${i+1} · ${dn(w.start.slice(0,10))} ${hh(w.start)} – ${hh(w.end)}</b>${w.good.map(g=>`<div class="g">✓ ${E(g)}</div>`).join('')}${w.bad.map(g=>`<div class="w">⚠ ${E(g)}</div>`).join('')}</div></div>`).join(''):'<p class="mu">No suitable window in the next 48 hours.</p>'}</div>`};
function render(){const c=S.cities[S.cur],d=c&&S.data[K(c)];
$('#nav').innerHTML=[['home','▦ Home'],['dash','☰ Dashboard'],['act','◎ Activities'],['cities','⇄ My Cities']].map(([k,l])=>`<div class="nav ${S.view==k?'on':''}" onclick="S.view='${k}';render()">${l}</div>`).join('');
$('#locs').innerHTML=S.cities.map((x,i)=>{const w=S.data[K(x)];return `<div class="loc ${i==S.cur?'on':''}" onclick="S.cur=${i};render()"><div><b>${E(x.name)}</b><small>${w?WMO[w.now.code]||'':'loading…'}</small></div><span>${w?T(w.now.temp):''}<i class="x" onclick="event.stopPropagation();del(${i})">✕</i></span></div>`}).join('');
$('#uC').className=S.unit=='C'?'on':'';$('#uF').className=S.unit=='F'?'on':'';
if(d)$('#prov').innerHTML=(d.demo?'<span style="color:#fbbf24">● Demo data (offline)</span>':'<span style="color:#34d399">● SkyCast live</span>')+'<br>Open-Meteo forecast + air quality';
$('#st').textContent=d?'● Live · '+E(d.city.name)+' · '+d.city.lat.toFixed(2)+', '+d.city.lon.toFixed(2):'';
if(!d){$('#view').innerHTML='<div class="card">Loading weather from SkyCast…</div>';return}
const g=new Date(d.now.time).getHours();$('#hi').textContent=(g<12?'Good morning':g<17?'Good afternoon':'Good evening')+' — '+d.city.name;
if(S.view=='home')$('#view').innerHTML=`<div class="grid"><div class="c7">${hero(d)}</div><div class="c5">${alertsH(d)}</div><div class="c12">${strip(d)}</div>${tiles(d).split('<div class="card c3">').slice(1,5).map(x=>'<div class="card c3">'+x).join('')}</div>`;
else if(S.view=='dash')$('#view').innerHTML=`<div class="grid"><div class="c4">${hero(d)}</div><div class="c4 card"><h3>Next 24 hours</h3>${chart(d.hours.slice(0,25))}</div><div class="c4">${week(d)}</div><div class="c8">${strip(d)}</div><div class="c4">${aqH(d)}</div>${tiles(d)}<div class="c12">${alertsH(d)}</div></div>`;
else if(S.view=='act')$('#view').innerHTML=`<div class="grid">${acts(d)}</div>`;
else $('#view').innerHTML=`<div class="grid">${S.cities.map((x,i)=>{const w=S.data[K(x)];return `<div class="card c4 tile" onclick="S.cur=${i};S.view='dash';render()"><b>${E(x.name)}</b> <span class="mu">${E(x.region)}</span><div class="big" style="font-size:44px;margin:10px 0">${w?T(w.now.temp):'…'}</div><div class="mu">${w?(WMO[w.now.code]||'')+' · H '+T(w.days[0].hi)+' L '+T(w.days[0].lo)+' · AQI '+(w.aq.aqi??'–'):''}</div></div>`}).join('')}</div>`}
function del(i){if(S.cities.length<2)return;S.cities.splice(i,1);S.cur=0;save();render()}
$('#q').addEventListener('keydown',async e=>{if(e.key!='Enter')return;const q=e.target.value.trim();if(q.length<2)return;const r=await (await fetch('/api/skycast/search?q='+encodeURIComponent(q))).json(),b=$('#res');b.hidden=false;b.innerHTML=r.length?r.map((c,i)=>`<div data-i="${i}">＋ ${E([c.name,c.region,c.country].filter(Boolean).join(', '))}</div>`).join(''):'<div>No city found</div>';b.onclick=ev=>{const i=ev.target.dataset.i;if(i==null)return;const c=r[i];if(!S.cities.some(x=>SAME(x,c)))S.cities.push(c);S.cur=S.cities.findIndex(x=>SAME(x,c));save();b.hidden=true;e.target.value='';load(c);render()}});
$('#uC').onclick=()=>{S.unit='C';render()};$('#uF').onclick=()=>{S.unit='F';render()};$('#rf').onclick=all;
setInterval(()=>$('#clock').textContent=new Date().toLocaleString('en',{weekday:'long',day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}),1000);setInterval(all,3e5);
render();all();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, body, ctype="application/json", code=200):
        b = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u, q = urlparse(self.path), parse_qs(urlparse(self.path).query); g = lambda k, d="": q.get(k, [d])[0]
        try:
            if u.path == "/": self.reply(PAGE, "text/html")
            elif u.path == "/api/skycast":
                self.reply(dict(api="SkyCast", version="1.0", sources=["Open-Meteo forecast", "Open-Meteo air quality"],
                                endpoints=["/api/skycast/weather?lat=&lon=&name=", "/api/skycast/search?q="]))
            elif u.path == "/api/skycast/weather":
                self.reply(get_weather(float(g("lat")), float(g("lon")), g("name"), g("region"), g("country")))
            elif u.path == "/api/skycast/search": self.reply(search_cities(g("q")))
            else: self.reply({"error": "not found"}, code=404)
        except (ValueError, KeyError):
            self.reply({"error": "bad request: check lat, lon or q"}, code=400)

    def log_message(self, *a): pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"SkyCast API running -> http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: srv.server_close()