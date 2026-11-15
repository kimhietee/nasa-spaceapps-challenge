"""Synthetic FIRMS-like detections for development. NOT REAL DATA.
Built so the pipeline has something realistic to chew on: seasonal peaks, an unusual year,
VIIRS detecting more than MODIS after 2012, a volcano and a persistent industrial heat source."""
import numpy as np
import pandas as pd

from .config import CONFIG

# name, lon, lat, spread(deg), weight, peak_week, width, 2nd_peak_week, 2nd_amplitude
ZONES = [
    ("Bukidnon plateau", 125.05, 7.95, 0.25, 3.0, 14, 4.5, 41, 0.35),
    ("South Mindanao", 124.60, 7.00, 0.50, 2.5, 13, 5.0, 40, 0.30),
    ("Central Luzon", 120.80, 15.40, 0.50, 3.0, 11, 4.0, 45, 0.20),
    ("Negros", 123.00, 10.20, 0.35, 2.0, 12, 5.0, 47, 0.30),
    ("Palawan and others", 118.80, 9.90, 0.60, 1.0, 12, 5.0, 38, 0.20),
    ("Cagayan Valley", 121.70, 17.40, 0.50, 1.5, 15, 5.0, 44, 0.20),
]
BASE_RATE = 9.0  # events per zone-weight per week at peak=1


def _bump(week, centre, width):
    return np.exp(-(((week - centre) / width) ** 2))


def make_demo_firms(seed=42, start_year=2003, end_year=2025):
    rng = np.random.default_rng(seed)
    W, S, E, N = CONFIG["ph_bbox"]
    rows = []
    weeks = np.arange(1, 53)

    def add(df_events, sensor):
        rows.append(df_events.assign(_sensor=sensor))

    for year in range(start_year, end_year + 1):
        yf = rng.lognormal(0, 0.22) * (2.3 if year == 2016 else 1.0) * (0.5 if year == 2011 else 1.0)
        ev_lon, ev_lat, ev_date = [], [], []
        for _, zlon, zlat, sd, wt, pk, wd, pk2, a2 in ZONES:
            lam = wt * BASE_RATE * (0.06 + _bump(weeks, pk, wd) + a2 * _bump(weeks, pk2, 3)) * yf
            counts = rng.poisson(lam)
            wk = np.repeat(weeks, counts)
            n = len(wk)
            ev_lon.append(np.clip(zlon + rng.normal(0, sd, n), W + 0.05, E - 0.05))
            ev_lat.append(np.clip(zlat + rng.normal(0, sd, n), S + 0.05, N - 0.05))
            day = (wk - 1) * 7 + rng.integers(0, 7, n)
            ev_date.append(pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(np.minimum(day, 364), unit="D"))
        ev = pd.DataFrame({"longitude": np.concatenate(ev_lon), "latitude": np.concatenate(ev_lat),
                           "acq_date": np.concatenate([d.to_numpy() for d in ev_date])})
        n = len(ev)
        # MODIS sees roughly 45% of events (coarser pixel)
        mod = ev[rng.random(n) < 0.45].copy()
        mod["confidence"] = rng.integers(15, 101, len(mod))
        mod["satellite"] = rng.choice(["Terra", "Aqua"], len(mod))
        add(mod, "MODIS")
        # VIIRS from 2012: sees ~97% of events, often several pixels per event
        if year >= CONFIG["viirs_start_year"]:
            v = ev[rng.random(n) < 0.97].copy()
            v = v.loc[v.index.repeat(1 + rng.poisson(0.8, len(v)))].reset_index(drop=True)
            v["longitude"] += rng.normal(0, 0.002, len(v))
            v["latitude"] += rng.normal(0, 0.002, len(v))
            v["confidence"] = rng.choice(["l", "n", "h"], len(v), p=[0.08, 0.70, 0.22])
            v["satellite"] = "N"
            add(v, "VIIRS")
            if year >= 2018:  # NOAA-20 duplicates, to prove the core series ignores them
                v2 = v.sample(frac=0.8, random_state=int(rng.integers(1e6))).copy()
                v2["satellite"] = "N20"
                add(v2, "VIIRS")
        # Kanlaon volcano area: detections spread over all months, every year
        k = pd.DataFrame({"longitude": 123.132 + rng.normal(0, 0.01, 40), "latitude": 10.412 + rng.normal(0, 0.01, 40),
                          "acq_date": pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(rng.integers(0, 365, 40), unit="D")})
        k["confidence"] = 80
        k["satellite"] = "Aqua"
        add(k, "MODIS")
        # Persistent industrial heat source (all months, all years, fixed cell)
        f = pd.DataFrame({"longitude": 121.050, "latitude": 14.150,
                          "acq_date": pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(rng.integers(0, 365, 60), unit="D")})
        f["confidence"] = 90
        f["satellite"] = "Aqua"
        add(f, "MODIS")

    df = pd.concat(rows, ignore_index=True)
    is_v = df["_sensor"] == "VIIRS"
    df["instrument"] = np.where(is_v, "VIIRS", "MODIS")
    df["frp"] = np.round(rng.lognormal(1.8, 0.9, len(df)), 1)
    df["daynight"] = rng.choice(["D", "N"], len(df), p=[0.8, 0.2])
    df["acq_time"] = rng.integers(0, 2400, len(df))
    df["type"] = 0
    df["acq_date"] = pd.to_datetime(df["acq_date"]).dt.strftime("%Y-%m-%d")
    return df.drop(columns=["_sensor"])
