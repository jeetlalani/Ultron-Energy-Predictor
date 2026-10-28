"""Ultron backend (Flask on Catalyst AppSail): cleaning, QuickML call, serves the dashboard."""
import os
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from predict import predict_with_source

app = Flask(__name__, static_folder="static")
# column: (min, max, default when nothing is known)
LIM = {"ambient_temp_c": (-30, 60, 25), "humidity_pct": (0, 100, 60), "solar_irradiance_wm2": (0, 1400, 0)}
SHORT = {"ambient_temp_c": "T", "humidity_pct": "H", "solar_irradiance_wm2": "S"}
MAX_ROWS = 24  # one 24-hour forecast window (keeps requests fast)


def preprocess(rows):
    log = []
    df = pd.DataFrame([{"timestamp": r.get("ts"), "ambient_temp_c": r.get("T"),
                        "humidity_pct": r.get("H"), "solar_irradiance_wm2": r.get("S")} for r in rows])
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    if (~ts.notna()).sum():
        log.append(f"Dropped {(~ts.notna()).sum()} rows with unreadable timestamps.")
    df = df[ts.notna()].copy()
    df["timestamp"] = ts[ts.notna()].dt.floor("h")
    df = df.sort_values("timestamp")
    n0 = len(df)
    df = df.drop_duplicates("timestamp").reset_index(drop=True)
    if len(df) < n0:
        log.append(f"Removed {n0 - len(df)} duplicate hours.")
    for c, (lo, hi, dflt) in LIM.items():
        v = pd.to_numeric(df[c], errors="coerce")
        if v.isna().sum():
            log.append(f"Filled {int(v.isna().sum())} missing {c} values by interpolation.")
        v = v.interpolate(limit_direction="both").fillna(dflt)
        if ((v < lo) | (v > hi)).sum():
            log.append(f"Clipped {int(((v < lo) | (v > hi)).sum())} out-of-range {c} values.")
        df[c] = v.clip(lo, hi)
    if len(df) > MAX_ROWS:
        log.append(f"Using the first {MAX_ROWS} of {len(df)} hours.")
        df = df.head(MAX_ROWS)
    return df, log


def sdk_predict(df):
    """Call QuickML through the Catalyst SDK (logs in automatically inside AppSail)."""
    import zcatalyst_sdk
    quickml = zcatalyst_sdk.initialize(req=request).quick_ml()
    key = os.environ["QUICKML_ENDPOINT_KEY"]
    out = []
    for rec in df.to_dict(orient="records"):
        rec["timestamp"] = str(rec["timestamp"])
        res = quickml.run_inference(key, rec)
        item = res["result"]
        item = item[0] if isinstance(item, list) else item
        out.append(float(item["prediction"] if isinstance(item, dict) else item))
    return np.array(out, dtype=float)


@app.route("/")
def home():
    return send_from_directory("static", "index.html")


@app.route("/api/health")
def health():
    return jsonify(status="ok")


@app.route("/api/forecast", methods=["POST"])
def forecast():
    rows = (request.get_json(silent=True) or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        return jsonify(error="Send a non-empty 'rows' list."), 400
    df, log = preprocess(rows)
    if df.empty:
        return jsonify(error="No valid rows. Need timestamp, ambient_temp_c, humidity_pct, solar_irradiance_wm2."), 400
    preds, source, warn = None, "quickml", ""
    if os.environ.get("USE_SDK") == "1":
        try:
            preds = sdk_predict(df)
        except Exception as e:
            warn = f"QuickML SDK call failed ({e})."
    if preds is None:
        preds, source, w2 = predict_with_source(df)
        warn = warn or w2
    if warn and source == "fallback":
        log.append(warn + " Showing the starter fallback formula instead.")
    out = []
    for (_, r), p in zip(df.iterrows(), preds):
        d = {"ts": r["timestamp"].strftime("%Y-%m-%d %H:%M:%S"), "b": round(float(max(0, p)), 2)}
        d.update({SHORT[c]: float(r[c]) for c in LIM})
        out.append(d)
    return jsonify(rows=out, log=log, source=source)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", 9000)))
