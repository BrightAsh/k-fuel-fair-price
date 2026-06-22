# 06 Web Operational Dataset Build

This stage creates the small, Git-friendly data package used by the public web page.

The heavy files from stage 03 and 05 are local build artifacts:

- `ai-model/03_target_dataset_build/outputs/grid_target.parquet`
- `ai-model/05_full_grid_prediction_for_web/outputs/**/predictions_by_month/*.parquet`
- `ai-model/05_full_grid_prediction_for_web/outputs/**/*_full.parquet`

Stage 06 reads the stage 05 outputs and writes only the operational data that should be committed.

## Outputs

```text
ai-model/06_web_operational_dataset_build/outputs/
  operational_dataset_manifest.json
  web/
    web_region_today.csv
    web_price_history_region.csv
    web_national_today.csv
    web_latest_grid_predictions.csv
    grid_region_lookup.csv
  inference_state/
    recent_model_input.parquet
    recent_model_input_manifest.json
```

`web_region_today.csv` and `web_price_history_region.csv` are the primary inputs for
`page/scripts/build_page_data.py`. The page builder reads this stage 06 web directory first and
falls back to stage 05 outputs only when stage 06 has not been produced yet.

`recent_model_input.parquet` is a compact recent panel for operational inference experiments. It is
not a replacement for the full training dataset. If it becomes larger than GitHub's practical file
size limit, rerun this stage with fewer state days or keep the file out of Git.

## Daily Operation

`daily_operational_prediction.py` is the GitHub Actions path. It does not need the full
`grid_target.parquet`.

It uses:

- committed AI 04 model files
- `outputs/inference_state/recent_model_input.parquet`
- the latest individual station price CSVs under `data-analysis/00_data_collection/outputs/gas_station_prices_by_region`
- `data-analysis/00_data_collection/outputs/derived_data/station_points.csv`

The script appends newly available station-price dates to the compact inference state, rebuilds the
28-day input sequence per grid, predicts the next-day fair price, and rewrites the web CSVs. In other
words, if the latest station price date is `D`, the web can show fair prices for `D+1`.

The latest source date must also have enough grid coverage. A partial date is held back by default
until its grid count reaches at least 80% of the recent daily median, so the web page does not switch
to a map where many regions are missing.

Important limitation: the current repository can run daily inference automatically once station price
files are updated, but the public automation does not yet guarantee fresh individual station-price
collection by itself. If those source files do not advance, the model cannot honestly create a newer
daily fair-price map.

## Run

```powershell
python ai-model/06_web_operational_dataset_build/06_web_operational_dataset_build.py `
  --history-years 10 `
  --state-days 35
```

Then rebuild the page JSON:

```powershell
python page/scripts/build_page_data.py
```

The full local build flow is:

```text
05 full-grid prediction
  -> 06 operational dataset package
  -> page JSON build
  -> GitHub Pages deploy
```

The daily GitHub Actions flow is:

```text
latest station price files
  -> daily_operational_prediction.py
  -> 06 web CSVs + rolling inference state
  -> page JSON build
  -> GitHub Pages deploy
```
