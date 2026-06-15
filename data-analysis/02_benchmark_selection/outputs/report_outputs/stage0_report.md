# 02 Benchmark Selection Report

## Input
- integrated file: `/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/preprocessed_data/분석용_일별_통합데이터.csv`
- integrated rows: 6,630
- integrated date range: 2008-04-15 ~ 2026-06-09
- weekly refinery rows: 868

## Selected Benchmarks
### gasoline
- group: product
- candidate: mogas92_krw_l
- ok: False
- p/q: 8 / 8
- OOS RMSE(level): 16.359567418349318
- BIC: 712.2475619950449
- full Ljung-Box p: 0.012321627534950858
- full block p: 5.256224440065466e-130

### diesel
- group: product
- candidate: gasoil_0001_krw_l
- ok: False
- p/q: 6 / 5
- OOS RMSE(level): 18.22274122967514
- BIC: 831.3258654058525
- full Ljung-Box p: 0.0016205416889258307
- full block p: 6.762722316590228e-97

## Saved Tables

- `tables/stage0_candidate_grid_all_fuels.csv`: all p/q search results
- `tables/stage0_candidate_rankings.csv`: report ranking with rank_in_fuel
- `tables/stage0_top20_by_fuel.csv`: top 20 rows per fuel
- `tables/stage0_candidate_summary.csv`: candidate-level metric summary
- `tables/stage0_winner_details.csv`: final selected benchmark rows
- `diagnostics/input_profile.csv`: input row/date profile
- `diagnostics/daily_numeric_summary.csv`: daily candidate descriptive statistics
- `diagnostics/weekly_refinery_numeric_summary.csv`: weekly target descriptive statistics