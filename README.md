# Ultron Energy Predictor

**Smart microgrid demand forecasting and power-source planning for HackSphere 3.0.**

[Open the live application](https://ultron-50047149305.development.catalystappsail.in/)

Ultron forecasts hourly electricity demand from time and weather inputs. Its dashboard displays demand, power-source switching schedules, critical overload alerts, and battery state of charge. Users can forecast one hour, generate a 24-hour window, or supply hourly telemetry through CSV.

## Features

- **Hourly forecasts:** Enter a date, hour, ambient temperature, humidity, and solar irradiance.
- **24-hour planning:** Generate a full-day window using a typical weather curve around the supplied inputs. These additional weather values are estimates, not a live weather feed.
- **CSV input:** Upload hourly telemetry using the challenge schema.
- **Data cleanup:** Normalize timestamps, remove duplicate hours, fill missing weather values, and clip out-of-range values.
- **Switching schedule:** Show main-grid and renewable-storage periods with their transition reasons.
- **Overload alerts:** Flag demand at or above 200 kW.
- **Battery planning:** Set battery capacity and initial charge, inspect projected charge, and identify insufficient stored energy.
- **Extra-energy scenarios:** Add hourly demand and a reason, then review the resulting dispatch and battery implications.
- **Prediction-source transparency:** Distinguish QuickML output from the demo-only fallback formula.

## Implementation status

The public dashboard is deployed on Zoho Catalyst AppSail. During a review on **28 October 2026**, its 24-hour request reported a QuickML timeout and displayed fallback predictions. This describes that observed run, not a permanent service status.

A fallback result demonstrates the dashboard workflow; it does **not** validate the trained model or establish its accuracy. Verify the QuickML connection and run evaluation with fallback disabled before submission. No measured RMSE is claimed in this repository documentation.

## Technology

| Component | Implementation |
| --- | --- |
| Web backend | Python and Flask |
| Telemetry processing | pandas and NumPy |
| Prediction client | requests with concurrent per-row inference |
| Model service | Zoho Catalyst QuickML |
| Hosting | Zoho Catalyst AppSail |
| Dashboard | Static frontend served from `static/index.html` |
| Optional inference route | Catalyst Python SDK when `USE_SDK=1` |

## Repository files

| Path | Purpose |
| --- | --- |
| `app.py` | Flask routes, preprocessing, optional SDK inference, and static frontend serving |
| `predict.py` | QuickML REST client, feature construction, fallback handling, and CSV prediction CLI |
| `static/index.html` | Dashboard entry point; include the frontend and any referenced assets |
| `app-config.json` | AppSail launch configuration; commit only a credential-free version |
| `requirements.txt` | Python dependencies; create and pin versions tested in your deployment |
| `train_telemetry.csv` | Official starter training data, if included |
| `sample_test_input.csv` | Official starter sample inputs, if included |
| `test_eval.py` | Official starter contract check, if included |

**Filename requirement:** If your prediction script is named `predict.py`, rename it to `predict.py`. The backend imports `predict_with_source` from `predict`.

The frontend, dependency manifest, and evaluation assets must be included separately if they are not already in the repository. The supplied backend and prediction script alone are not a complete dashboard deployment.

## Local setup

The supplied AppSail configuration selects Python 3.13.

1. Clone the repository and open its root directory.
2. Confirm `predict.py` and `static/index.html` are present.
3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate it:

   ```bash
   # macOS / Linux
   source .venv/bin/activate

   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   ```

5. Install the dependencies used by the default REST path:

   ```bash
   python -m pip install Flask numpy pandas requests
   ```

   Record tested versions in `requirements.txt`. The optional SDK route additionally requires the package that provides `zcatalyst_sdk`.

6. Configure the environment variables below, then start the backend:

   ```bash
   python app.py
   ```

7. Open **http://localhost:9000**.

The app binds to `0.0.0.0`. It uses `X_ZOHO_CATALYST_LISTEN_PORT` when supplied by AppSail, otherwise port `9000`. The current entry point uses Flask's built-in server.

## Environment variables

Store secrets in your shell environment or AppSail environment settings. The code does not automatically load a `.env` file.

| Variable | Purpose / behavior |
| --- | --- |
| `QUICKML_ENDPOINT_URL` | Published QuickML REST prediction URL. The script has a project-specific default; explicitly override it for your deployment. |
| `QUICKML_ENDPOINT_KEY` | Required endpoint key for REST inference and the optional SDK route. |
| `QUICKML_REFRESH_TOKEN` | OAuth refresh token for obtaining access tokens. |
| `ZOHO_CLIENT_ID` | OAuth client ID used with the refresh token. |
| `ZOHO_CLIENT_SECRET` | OAuth client secret used with the refresh token. |
| `QUICKML_OAUTH_TOKEN` | Alternative access token when the full refresh-token credential set is unavailable. |
| `ZOHO_ACCOUNTS_URL` | OAuth account-server base URL. Default: `https://accounts.zoho.in`. |
| `CATALYST_ORG` | Catalyst organization header. The script has a project-specific default; set it for your organization. |
| `CATALYST_ENV` | REST environment header. Default: `Development`. |
| `ALLOW_FALLBACK` | Defaults to `true`. Set exactly to `false` (case-insensitive) to raise an error when QuickML fails. |
| `USE_SDK` | Set to `1` to try Catalyst SDK inference first. Otherwise the backend uses the REST client. |
| `X_ZOHO_CATALYST_LISTEN_PORT` | Listening port provided by AppSail; defaults locally to `9000`. |

For automatic OAuth refresh, configure all three of `QUICKML_REFRESH_TOKEN`, `ZOHO_CLIENT_ID`, and `ZOHO_CLIENT_SECRET`. Access tokens obtained this way are cached in process for approximately 50 minutes.

**Credential safety:** Never commit refresh tokens, access tokens, endpoint keys, or client secrets. Replace any real values in `app-config.json` with secure deployment configuration. If credentials have been exposed, rotate them; removing them from the latest commit does not remove them from Git history.

## Telemetry and feature preparation

### CSV format

```csv
timestamp,ambient_temp_c,humidity_pct,solar_irradiance_wm2
2026-10-28 12:00:00,32,55,800
2026-10-28 13:00:00,33,53,770
```

The training data additionally contains `target_demand_kw`, the regression target. Inference inputs do not require that column.

### Backend cleanup

`app.py` performs the following steps:

1. Drop rows with unreadable timestamps.
2. Floor timestamps to the hour, sort them, and remove duplicate hours.
3. Convert weather inputs to numeric values.
4. Interpolate missing values in both directions, then use defaults where needed.
5. Clip values to the supported ranges below.
6. Keep the first 24 valid hours after sorting and deduplication.

| Field | Minimum | Maximum | Default |
| --- | ---: | ---: | ---: |
| Ambient temperature (°C) | -30 | 60 | 25 |
| Humidity (%) | 0 | 100 | 60 |
| Solar irradiance (W/m²) | 0 | 1400 | 0 |

### QuickML feature contract

The REST client derives **`hour`, `date`, and `month`** from `timestamp`; `date` means the day of the month. It sends these with `ambient_temp_c`, `humidity_pct`, and `solar_irradiance_wm2`, rounding weather values to four decimal places.

The published QuickML model must accept this exact feature schema. Train and deploy the model with consistent training and inference transformations. The app does not train the model itself.

Identical feature rows share one inference call. The client runs up to 16 calls concurrently, uses a 15-second request timeout, and attempts a request up to twice for supported transient failures.

The optional SDK path currently sends a timestamp and weather fields directly, rather than the REST client's derived time fields. Confirm that the model schema matches the chosen route before enabling `USE_SDK=1`. An SDK failure causes the backend to attempt the REST path.

## HTTP API

### `GET /api/health`

Returns:

```json
{"status": "ok"}
```

This is a backend liveness check. It does **not** test QuickML authentication or inference.

### `POST /api/forecast`

The JSON API uses abbreviated keys, unlike the CSV format:

```json
{
  "rows": [
    {"ts": "2026-10-28 12:00:00", "T": 32, "H": 55, "S": 800}
  ]
}
```

Example local request:

```bash
curl -X POST http://localhost:9000/api/forecast \
  -H "Content-Type: application/json" \
  -d '{"rows":[{"ts":"2026-10-28 12:00:00","T":32,"H":55,"S":800}]}'
```

The response contains:

| Field | Meaning |
| --- | --- |
| `rows[].ts` | Cleaned hourly timestamp |
| `rows[].T`, `H`, `S` | Cleaned weather values |
| `rows[].b` | Predicted demand in kW, clamped to at least zero and rounded to two decimals |
| `log` | Cleanup messages and applicable fallback warning |
| `source` | `quickml` or `fallback` |

A missing or empty `rows` list, or a batch with no valid timestamps, returns HTTP 400. Each row should be an object with the documented keys. With fallback disabled, an inference failure raises an exception; the current route does not convert that exception into a custom JSON error response.

The supplied API returns demand predictions. It does not return grid-mode, battery, or overload fields; those planning outputs appear in the website's dashboard workflow.

## Grid switching and battery behavior

The website describes these challenge rules:

| Condition | Result |
| --- | --- |
| Demand **>160 kW**, or hour **18:00–22:00 inclusive** | Renewable storage mode |
| Demand **≤160 kW**, outside the evening window | Main grid mode |
| Demand **≥200 kW** | Critical overload alert, independently of grid mode |

The dashboard lets users configure capacity in kWh and initial charge as a percentage. In storage mode, it models the battery covering the whole hour's demand. In main-grid mode, it models recharging at 100 kW. It displays insufficient-energy warnings when the battery cannot cover the selected hour.

These are software planning outputs. This repository documentation does not claim physical grid switching or connected battery hardware.

## CSV predictions and evaluation

Run the prediction client from the repository root:

```bash
python predict.py --input sample_test_input.csv --output predictions.csv
```

Output columns:

```csv
timestamp,target_demand_kw
```

The CLI writes one prediction per input row and preserves the original timestamp column and row order. It does not apply the backend's 24-row cap, sorting, timestamp deduplication, or weather clipping. Supply valid CSV timestamps and numeric telemetry for evaluation.

**Disable fallback for model verification:**

```bash
# macOS / Linux
export ALLOW_FALLBACK=false
python predict.py --input sample_test_input.csv --output predictions.csv
python test_eval.py
```

```powershell
# Windows PowerShell
$env:ALLOW_FALLBACK = "false"
python predict.py --input sample_test_input.csv --output predictions.csv
python test_eval.py
```

Use the official `test_eval.py` from the starter kit. A successful contract check verifies output compatibility; it does not establish accuracy on the hidden test set. In the dashboard API, confirm `source` is `quickml` before treating results as trained-model predictions.

### Demo fallback

When allowed, a QuickML failure uses this deterministic formula:

```text
base = 120 + 30 × sin(2π × (hour − 6) / 24)
cooling = max(0, ambient_temp_c − 24) × 8.5
fallback_demand_kw = base + cooling
```

This formula ignores humidity and solar irradiance. It is not the trained QuickML model and must not be presented as model-accuracy evidence. If any inference in a REST batch fails, the client falls back for the whole batch when fallback is enabled.

## Catalyst AppSail deployment

The supplied configuration uses this launch setup:

```json
{
  "command": "python3 app.py",
  "build_path": "./",
  "stack": "python_3_13",
  "env_variables": {},
  "memory": 256,
  "scripts": {}
}
```

1. Include `app.py`, `predict.py`, the frontend under `static/`, and a tested dependency manifest in the deployment bundle.
2. Train and publish the regression model in QuickML with the matching input schema.
3. Set endpoint, organization, environment, and OAuth configuration securely in the deployment environment.
4. Deploy the application to AppSail with the launch configuration above.
5. Check `/api/health`, then submit a valid `/api/forecast` request.
6. Verify `source: "quickml"`, review the dashboard results, and run the official evaluation script with fallback disabled.

Use the configured account region consistently. The supplied client defaults to Zoho's India endpoints; update the account URL and prediction endpoint together for another region.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `No module named predict` | Rename `predict.py` to `predict.py` and keep it beside `app.py`. |
| Homepage returns 404 | Include `static/index.html` and its referenced assets. |
| Health works but forecasting fails | Health does not call QuickML. Check endpoint access, credentials, headers, and feature schema. |
| Missing OAuth credentials | Set the full refresh-token credential set or a valid `QUICKML_OAUTH_TOKEN`. |
| Missing endpoint key | Set `QUICKML_ENDPOINT_KEY`. |
| QuickML timeout or HTTP error | Check endpoint availability, region, organization/environment settings, and the reported error. |
| `source` is `fallback` | QuickML failed. Read the warning and repeat with `ALLOW_FALLBACK=false` to verify the model path. |
| SDK inference fails | Verify SDK availability and its expected input schema; the REST and SDK payloads differ. |
| Fewer dashboard rows than expected | Check invalid timestamps, duplicate hours, and the 24-row backend limit. |
| Battery is empty in storage mode | The mode follows the challenge's threshold/time rules; inspect the separate battery shortfall warning. |

## HackSphere 3.0 submission

The official challenge weights QuickML accuracy at 35%, deployment and functionality at 35%, transition-controller logic at 20%, and UI/UX at 10%.

Before submission, confirm:

- The public Catalyst application is reachable and its main workflow runs.
- The published QuickML model returns predictions successfully with fallback disabled.
- `predict.py` passes the official starter contract check.
- The repository includes the full frontend and backend, dependency setup, and this README.
- Required environment variables are documented without exposing credentials.
- Switching boundaries and overload behavior match the official rules.
- The source repository or submission ZIP and live application URL are included in the submission.

## Documentation scope

This README reflects the supplied `app.py`, prediction client, AppSail configuration, the observed public dashboard, and the official HackSphere 3.0 problem statement. The frontend source and QuickML training pipeline were not supplied for code review. Frontend behavior above describes the visible website; it is not a verification of its internal implementation.
