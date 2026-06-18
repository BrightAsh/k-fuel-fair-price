# gas_station_prices_by_region

This folder stores the final station-level daily price matrix from Opinet.

Only `final/` is tracked in Git. The original `raw/` folder is intentionally
not included because it is too large for the repository.

Most region/fuel files are stored as regular CSV files:

```text
final/{region}/gasoline.csv
final/{region}/diesel.csv
```

Files that exceed GitHub's 100 MB single-file limit are split by station-id
columns and stored as parts:

```text
final/{region}/gasoline.parts/
  manifest.json
  part-000.csv
  part-001.csv
```

Each part keeps the `date` column and a disjoint subset of station-id columns.
To reconstruct the original wide matrix, read the parts in `manifest.json`
order and join them by `date`.

At the time this dataset was added, the split files were:

- `final/경기/gasoline.parts/`
- `final/경기/diesel.parts/`

