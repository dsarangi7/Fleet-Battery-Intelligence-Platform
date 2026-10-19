PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS ingestion_runs (
  digest TEXT PRIMARY KEY, source TEXT NOT NULL, processed_at TEXT NOT NULL,
  accepted INTEGER NOT NULL, rejected INTEGER NOT NULL, duplicates INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS quality_issues (
  digest TEXT NOT NULL, row_number INTEGER NOT NULL, reason TEXT NOT NULL,
  PRIMARY KEY(digest,row_number)
);
CREATE TABLE IF NOT EXISTS telemetry (
  pack TEXT NOT NULL, module INTEGER NOT NULL, cell INTEGER NOT NULL,
  day INTEGER NOT NULL, step INTEGER NOT NULL, timestamp TEXT NOT NULL,
  voltage REAL NOT NULL, current REAL NOT NULL, temperature REAL NOT NULL,
  reference_soc REAL NOT NULL, nominal_ah REAL NOT NULL,
  PRIMARY KEY(pack,module,cell,day,step)
);
CREATE INDEX IF NOT EXISTS telemetry_day ON telemetry(day,pack);
CREATE TABLE IF NOT EXISTS cell_metrics (
  pack TEXT, module INTEGER, cell INTEGER, day INTEGER,
  capacity_ah REAL, soh_pct REAL, throughput_ah REAL, soc_end_pct REAL,
  voltage_residual_mv REAL, baseline_count INTEGER, anomaly INTEGER,
  status TEXT, PRIMARY KEY(pack,module,cell,day)
);
CREATE TABLE IF NOT EXISTS pack_daily (
  pack TEXT, day INTEGER, cells INTEGER, soh_pct REAL, weakest_soh_pct REAL,
  soc_pct REAL, voltage_spread_mv REAL, anomalies INTEGER, throughput_ah REAL,
  PRIMARY KEY(pack,day)
);
CREATE TABLE IF NOT EXISTS degradation (
  pack TEXT PRIMARY KEY, observed_days INTEGER, soh_change_pp REAL,
  slope_pp_per_day REAL
);
CREATE VIEW IF NOT EXISTS module_daily AS
SELECT pack,module,day,count(*) AS cells,avg(soh_pct) AS mean_soh_pct,
 min(soh_pct) AS weakest_soh_pct,sum(anomaly) AS anomalies
FROM cell_metrics GROUP BY pack,module,day;
CREATE VIEW IF NOT EXISTS fleet_daily AS
SELECT day,count(*) AS packs,avg(soh_pct) AS mean_soh_pct,
 min(weakest_soh_pct) AS weakest_soh_pct,sum(anomalies) AS anomalies
FROM pack_daily GROUP BY day;
CREATE VIEW IF NOT EXISTS quality_summary AS
SELECT pack,day,count(*) AS observed_cells,12-count(*) AS missing_cells,
 sum(CASE WHEN status='invalid_session' THEN 1 ELSE 0 END) AS invalid_sessions,
 sum(CASE WHEN status='scored' THEN 1 ELSE 0 END) AS scored_sessions,
 sum(CASE WHEN status='insufficient_peers' THEN 1 ELSE 0 END) AS unmatched_sessions,
 sum(CASE WHEN soh_pct IS NOT NULL THEN 1 ELSE 0 END) AS capacity_estimates
FROM cell_metrics GROUP BY pack,day;
