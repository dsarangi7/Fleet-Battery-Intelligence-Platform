"""Transactional ingestion and transparent analytical transforms."""
import csv
import hashlib
import math
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fleet.synthetic import FIELDS

BASELINE_DAYS = 10
MIN_PEERS = 20


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
    return db


def validate(row: dict) -> tuple:
    if set(row) != set(FIELDS) or any(value is None for value in row.values()):
        raise ValueError('incorrect field count')
    if not re.fullmatch(r'SYN-\d{3}', row['pack']):
        raise ValueError('pack must be a synthetic SYN-nnn identifier')
    ints = [int(row[k]) for k in ['module', 'cell', 'day', 'step']]
    if not (1 <= ints[0] <= 2 and 1 <= ints[1] <= 6 and 0 <= ints[2] <= 365 and 0 <= ints[3] <= 10):
        raise ValueError('invalid hierarchy or session index')
    stamp = datetime.fromisoformat(row['timestamp'])
    if stamp.utcoffset() is None:
        raise ValueError('timestamp must include timezone')
    numbers = [float(row[k]) for k in FIELDS[6:]]
    if not all(math.isfinite(n) for n in numbers):
        raise ValueError('non-finite measurement')
    voltage, current, temp, soc, nominal = numbers
    if not (2 <= voltage <= 4.5 and 0 < current <= 100 and -20 <= temp <= 60
            and 0 <= soc <= 100 and 0 < nominal <= 1000):
        raise ValueError('measurement out of demo operating bounds')
    return (row['pack'], *ints, stamp.astimezone(timezone.utc).isoformat(), *numbers)


def ingest(db: sqlite3.Connection, path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if db.execute('SELECT 1 FROM ingestion_runs WHERE digest=?', (digest,)).fetchone():
        return {'source': path.name, 'status': 'already_processed'}
    accepted = rejected = duplicates = 0
    # A transaction includes quality evidence, samples, aggregates and the run record.
    with db:
        with path.open(newline='', encoding='utf-8') as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != FIELDS:
                raise ValueError('CSV header must match documented synthetic contract')
            for line, row in enumerate(reader, 2):
                try:
                    values = validate(row)
                except (ValueError, TypeError, KeyError):
                    # Never persist arbitrary raw input or exception strings.
                    db.execute('INSERT INTO quality_issues VALUES (?,?,?)',
                               (digest, line, 'invalid row: schema, range or timestamp'))
                    rejected += 1
                    continue
                existing = db.execute('SELECT * FROM telemetry WHERE pack=? AND module=? AND cell=? AND day=? AND step=?', values[:5]).fetchone()
                if existing:
                    if tuple(existing) == values:
                        duplicates += 1
                    else:
                        rejected += 1
                        db.execute('INSERT INTO quality_issues VALUES (?,?,?)',
                                   (digest, line, 'conflicting existing sample'))
                    continue
                db.execute('INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)', values)
                accepted += 1
        recompute(db)
        db.execute('INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?)',
                   (digest, 'synthetic CSV', datetime.now(timezone.utc).isoformat(), accepted, rejected, duplicates))
    return {'status': 'processed', 'accepted': accepted, 'rejected': rejected, 'duplicates': duplicates}


def condition(row: sqlite3.Row) -> tuple:
    return (round(row['reference_soc'] / 10), round(row['current'] / row['nominal_ah'] / 0.1),
            round(row['temperature'] / 10))


def recompute(db: sqlite3.Connection) -> None:
    rows = db.execute('SELECT * FROM telemetry ORDER BY pack,module,cell,day,step').fetchall()
    groups = defaultdict(list)
    for row in rows:
        groups[(row['pack'], row['module'], row['cell'], row['day'])].append(row)
    baseline = defaultdict(list)
    valid = {}
    for key, samples in groups.items():
        times = [datetime.fromisoformat(r['timestamp']).timestamp() for r in samples]
        valid[key] = (len(samples) == 11 and [r['step'] for r in samples] == list(range(11))
                      and all(0 < b - a <= 3600 for a, b in zip(times, times[1:]))
                      and len({r['nominal_ah'] for r in samples}) == 1
                      and all(a['reference_soc'] > b['reference_soc'] for a, b in zip(samples, samples[1:])))
        if valid[key] and key[3] < BASELINE_DAYS:
            for row in samples:
                baseline[condition(row)].append(row['voltage'])
    models = {}
    for key, values in baseline.items():
        center = statistics.median(values)
        sigma = max(1.4826 * statistics.median(abs(v - center) for v in values), 0.003)
        models[key] = (center, sigma, len(values))
    db.execute('DELETE FROM cell_metrics')
    for key, samples in groups.items():
        if not valid[key]:
            db.execute('INSERT INTO cell_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (*key, None, None, None, None, None, 0, None, 'invalid_session'))
            continue
        ah = sum((a['current'] + b['current']) / 2 *
                 (datetime.fromisoformat(b['timestamp']) - datetime.fromisoformat(a['timestamp'])).total_seconds() / 3600
                 for a, b in zip(samples, samples[1:]))
        delta_soc = (samples[0]['reference_soc'] - samples[-1]['reference_soc']) / 100
        capacity = ah / delta_soc if delta_soc >= 0.5 else None
        soh = 100 * capacity / samples[0]['nominal_ah'] if capacity else None
        # SOC uses nominal capacity, deliberately independent of estimated SOH.
        soc_end = samples[0]['reference_soc'] - ah / samples[0]['nominal_ah'] * 100
        residuals, flags, counts = [], [], []
        for row in samples:
            model = models.get(condition(row))
            if model and model[2] >= MIN_PEERS:
                center, sigma, count = model
                residuals.append(abs(row['voltage'] - center) * 1000)
                flags.append(abs(row['voltage'] - center) > max(6 * sigma, 0.025))
                counts.append(count)
        eligible = len(flags) == len(samples) and key[3] >= BASELINE_DAYS
        status = 'baseline' if key[3] < BASELINE_DAYS else ('scored' if eligible else 'insufficient_peers')
        if capacity is None:
            status = 'insufficient_soc_span'
        db.execute('INSERT INTO cell_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (*key, capacity, soh, ah, soc_end,
                    statistics.median(residuals) if residuals else None,
                    min(counts) if counts else 0, int(sum(flags) >= 3) if eligible else None, status))
    db.execute('DELETE FROM pack_daily')
    # For a single series string, charge throughput is averaged, never summed across cells.
    db.execute('''INSERT INTO pack_daily
      SELECT c.pack,c.day,count(*),avg(c.soh_pct),min(c.soh_pct),avg(c.soc_end_pct),
        (SELECT max(spread)*1000 FROM
          (SELECT max(voltage)-min(voltage) AS spread FROM telemetry t
           WHERE t.pack=c.pack AND t.day=c.day GROUP BY step)),
        sum(c.anomaly),avg(c.throughput_ah)
      FROM cell_metrics c GROUP BY c.pack,c.day''')
    db.execute('DELETE FROM degradation')
    for pack in sorted({key[0] for key in groups}):
        points = db.execute('SELECT day,soh_pct FROM pack_daily WHERE pack=? AND soh_pct IS NOT NULL ORDER BY day', (pack,)).fetchall()
        if len(points) < 2:
            continue
        xbar = statistics.mean(p[0] for p in points)
        ybar = statistics.mean(p[1] for p in points)
        slope = sum((p[0]-xbar)*(p[1]-ybar) for p in points) / sum((p[0]-xbar)**2 for p in points)
        db.execute('INSERT INTO degradation VALUES (?,?,?,?)',
                   (pack, len(points), points[-1][1]-points[0][1], slope))


ALLOWED_TABLES = {'fleet_daily', 'pack_daily', 'module_daily', 'cell_metrics',
                  'degradation', 'ingestion_runs', 'quality_issues', 'quality_summary'}


def records(db: sqlite3.Connection, table: str, limit: int = 1000) -> list:
    if table not in ALLOWED_TABLES:
        raise ValueError('unknown resource')
    return [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1,2 LIMIT ?', (limit,))]
