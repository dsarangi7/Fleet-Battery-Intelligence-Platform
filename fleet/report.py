import json
from pathlib import Path


def evaluate(db, truth_path: Path) -> dict:
    truth = {(r['pack'], r['module'], r['cell'], r['day']): r['voltage_fault']
             for r in json.loads(truth_path.read_text(encoding='utf-8'))}
    counts = dict(tp=0, fp=0, tn=0, fn=0, unscored=0)
    for row in db.execute('SELECT * FROM cell_metrics'):
        key = (row['pack'], row['module'], row['cell'], row['day'])
        if key not in truth or row['day'] < 10:
            continue
        if row['anomaly'] is None:
            counts['unscored'] += 1
            continue
        expected, predicted = truth[key], bool(row['anomaly'])
        counts['tp' if expected and predicted else 'fn' if expected else 'fp' if predicted else 'tn'] += 1
    counts['precision'] = counts['tp'] / (counts['tp'] + counts['fp']) if counts['tp'] + counts['fp'] else None
    counts['recall'] = counts['tp'] / (counts['tp'] + counts['fn']) if counts['tp'] + counts['fn'] else None
    counts['scope'] = 'Synthetic injected voltage fault; held-out days >=10; excludes baseline and unscored rows'
    return counts


def report(db, directory: Path) -> None:
    result = evaluate(db, directory / 'truth.json')
    (directory / 'evaluation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    aging = [dict(row) for row in db.execute('SELECT * FROM degradation ORDER BY slope_pp_per_day')]
    summary = f'''# Synthetic Run Evidence

This report is generated from the local synthetic dataset. It is not evidence of
commercial performance, safety validation, or customer savings.

## Held-out voltage anomaly evaluation

```json
{json.dumps(result, indent=2)}
```

## Observed degradation

Slope is SOH percentage points per synthetic day, measured over the observed
window only. Do not extrapolate to remaining useful life.

```json
{json.dumps(aging, indent=2)}
```

## Business interpretation

Condition matching groups similar SOC, discharge C-rate, and temperature before
comparing voltage. Sustained deviations become investigation candidates.
Capacity fade is reported separately so gradual aging is not confused with
an instantaneous voltage fault. Engineers can trace either result to session
measurements and ingestion quality evidence.

The next validation step is a consented dataset with independently established
fault labels and capacity reference tests. No financial return is claimed here.
'''
    (directory / 'RUN_REPORT.md').write_text(summary, encoding='utf-8')

