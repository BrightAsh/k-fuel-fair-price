# gas_station_prices_by_region

This folder stores the station-level daily price matrix from Opinet.

Only the final usable files are tracked in Git. The original `raw/` folder is
intentionally not included because it is too large for the repository.

Most region/fuel files are stored as regular CSV files:

```text
{region}/gasoline.csv
{region}/diesel.csv
```

Files that exceed GitHub's 100 MB single-file limit are split by station-id
columns and stored as parts:

```text
{region}/gasoline.parts/
  manifest.json
  part-000.csv
  part-001.csv
```

Each part keeps the `date` column and a disjoint subset of station-id columns.
To reconstruct the original wide matrix, read the parts in `manifest.json`
order and join them by `date`.

At the time this dataset was added, the split files were:

- `경기/gasoline.parts/`
- `경기/diesel.parts/`
