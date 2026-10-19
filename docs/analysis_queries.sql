-- Run against data/warehouse.sqlite using any SQLite client.

-- Latest available pack snapshot, with data coverage.
SELECT p.*, q.missing_cells, q.invalid_sessions, q.scored_sessions
FROM pack_daily p JOIN quality_summary q USING(pack,day)
WHERE p.day = (SELECT max(day) FROM pack_daily)
ORDER BY p.weakest_soh_pct;

-- Trace an anomaly to its cell/session and measurement evidence.
SELECT pack,module,cell,day,voltage_residual_mv,baseline_count,status
FROM cell_metrics WHERE anomaly=1
ORDER BY day,pack,module,cell;

-- Prioritize observed capacity fade without forecasting remaining life.
SELECT * FROM degradation ORDER BY slope_pp_per_day;

-- Review data quality before interpreting fleet trends.
SELECT * FROM quality_summary
WHERE missing_cells>0 OR invalid_sessions>0 OR unmatched_sessions>0;

-- Demonstrate lineage and rejection accounting.
SELECT source,processed_at,accepted,rejected,duplicates FROM ingestion_runs;
