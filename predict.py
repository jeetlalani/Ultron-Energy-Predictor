"""Ultron QuickML prediction client for electricity demand.
Usage: python predict.py --input sample_test_input.csv --output predictions.csv
Credentials come from environment variables, never from this file."""
import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

ENDPOINT_URL = os.environ.get(
    "QUICKML_ENDPOINT_URL",
    "https://api.catalyst.zoho.in/quickml/v1/project/101788000000016049/endpoints/predict",
)
_token_cache = {"value": None, "time": 0}


def get_access_token():
    """Exchange the Zoho refresh token for an access token (cached ~50 min)."""
    refresh = os.environ.get("QUICKML_REFRESH_TOKEN")
    client_id = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    if not all([refresh, client_id, client_secret]):
        token = os.environ.get("QUICKML_OAUTH_TOKEN")
        if token:
            return token
        raise RuntimeError("Missing Zoho OAuth credentials in environment variables.")
    if _token_cache["value"] and time.time() - _token_cache["time"] < 3000:
        return _token_cache["value"]
    accounts_url = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in").rstrip("/")
    r = requests.post(f"{accounts_url}/oauth/v2/token", timeout=15, data={
        "refresh_token": refresh, "client_id": client_id,
        "client_secret": client_secret, "grant_type": "refresh_token"})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"Zoho did not return an access token: {r.text[:200]}")
    _token_cache["value"], _token_cache["time"] = token, time.time()
    return token


def get_headers():
    endpoint_key = os.environ.get("QUICKML_ENDPOINT_KEY")
    if not endpoint_key:
        raise RuntimeError("QUICKML_ENDPOINT_KEY is not configured.")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-QUICKML-ENDPOINT-KEY": endpoint_key,
        "Authorization": "Zoho-oauthtoken " + get_access_token(),
        "CATALYST-ORG": os.environ.get("CATALYST_ORG", "60093178974"),
        "Environment": os.environ.get("CATALYST_ENV", "Development"),
    }


def _parse(body):
    result = body.get("result")
    if isinstance(result, list):
        if len(result) != 1:
            raise ValueError(f"Expected one prediction; received {len(result)} results.")
        result = result[0]
    if isinstance(result, dict):
        for key in ("prediction", "predicted-result", "target_demand_kw", "value"):
            if key in result:
                result = result[key]
                break
    try:
        value = float(result)
    except (TypeError, ValueError) as exc:
        raise ValueError("Could not read a number from QuickML response: " + repr(body)[:300]) from exc
    if not np.isfinite(value):
        raise ValueError("QuickML returned an invalid number.")
    return value


def _call(features, headers):
    """One prediction, with up to 2 tries for temporary errors."""
    last = None
    for attempt in range(2):
        try:
            r = requests.post(ENDPOINT_URL, json={"data": features}, headers=headers, timeout=15)
            if r.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"QuickML HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(1 + attempt)
                continue
            if not r.ok:
                raise RuntimeError(f"QuickML HTTP {r.status_code}: {r.text[:400]}")
            return _parse(r.json())
        except requests.RequestException as exc:
            last = exc
            time.sleep(1 + attempt)
    raise last


def fallback_predictions(df):
    """Demo-only formula; NOT the trained model."""
    hours = pd.to_datetime(df["timestamp"]).dt.hour
    base = 120 + 30 * np.sin(2 * np.pi * (hours - 6) / 24)
    cooling = np.maximum(0, df["ambient_temp_c"] - 24) * 8.5
    return (base + cooling).to_numpy(dtype=float)


WEATHER = {"ambient_temp_c": 25.0, "humidity_pct": 60.0, "solar_irradiance_wm2": 0.0}


def _features(df):
    """One feature dict per row: time parts plus the three weather columns."""
    ts = pd.to_datetime(df["timestamp"], errors="raise")
    w = pd.DataFrame({c: pd.to_numeric(df.get(c), errors="coerce") for c in WEATHER}, index=df.index)
    for c, dflt in WEATHER.items():
        w[c] = w[c].interpolate(limit_direction="both").fillna(dflt)
    return [{"hour": int(t.hour), "date": int(t.day), "month": int(t.month),
             **{c: round(float(w[c].iloc[i]), 4) for c in WEATHER}} for i, t in enumerate(ts)]


def predict_with_source(input_df):
    """Returns (predictions, source, warning). Identical feature rows share one call."""
    try:
        feats = _features(input_df.reset_index(drop=True))
        keys = [tuple(f.values()) for f in feats]
        unique = {k: f for k, f in zip(keys, feats)}
        headers = get_headers()
        with ThreadPoolExecutor(max_workers=16) as ex:
            values = list(ex.map(lambda f: _call(f, headers), unique.values()))
        lookup = dict(zip(unique.keys(), values))
        return np.array([lookup[k] for k in keys], dtype=float), "quickml", ""
    except Exception as exc:
        warning = f"QuickML prediction failed: {exc}"
        print(warning, flush=True)
        if os.environ.get("ALLOW_FALLBACK", "true").lower() == "false":
            raise RuntimeError(warning) from exc
        return fallback_predictions(input_df), "fallback", warning


def predict(input_df):
    """Predicted demand (kW) for each input row."""
    return predict_with_source(input_df)[0]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="sample_test_input.csv")
    ap.add_argument("--output", default="predictions.csv")
    a = ap.parse_args()
    df = pd.read_csv(a.input)
    preds = predict(df)
    pd.DataFrame({"timestamp": df["timestamp"], "target_demand_kw": np.round(preds, 2)}).to_csv(a.output, index=False)
    print(f"Wrote {len(preds)} predictions to {a.output}. First 5:\n{preds[:5]}")
