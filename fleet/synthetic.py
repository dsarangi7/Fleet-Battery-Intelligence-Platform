"""Deterministic generic discharge experiments; no company-derived parameters."""
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = ['pack', 'module', 'cell', 'day', 'step', 'timestamp', 'voltage',
          'current', 'temperature', 'reference_soc', 'nominal_ah']


def generate(directory: Path, days: int = 45, seed: int = 17) -> dict:
    if days < 15 or days > 365:
        raise ValueError('days must be between 15 and 365')
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    truth = []
    rows = 0
    path = directory / 'synthetic.csv'
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for day in range(days):
            for pack_index in range(6):
                pack = f'SYN-{pack_index + 1:03}'
                current = [10., 20., 30.][day % 3]
                temperature = [15., 25., 35.][(day // 3) % 3]
                # Accelerated illustrative aging, not a real battery lifetime model.
                capacity = 100 * (1 - day * (0.0015 if pack_index == 4 else 0.00025))
                interval_seconds = capacity * 0.06 / current * 3600
                start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
                for module in range(1, 3):
                    for cell in range(1, 7):
                        fault = day >= 30 and pack_index == 2 and module == 2 and cell == 4
                        truth.append({'pack': pack, 'module': module, 'cell': cell,
                                      'day': day, 'voltage_fault': fault})
                        for step in range(11):
                            soc = 80 - step * 6
                            voltage = (3.1 + soc * 0.008 - current * 0.001
                                       + (temperature - 25) * 0.0005
                                       + rng.gauss(0, 0.0015) - (0.075 if fault else 0))
                            writer.writerow(dict(zip(FIELDS, [pack, module, cell, day, step,
                                (start + timedelta(seconds=interval_seconds * step)).isoformat(),
                                round(voltage, 6), current, temperature, soc, 100.])))
                            rows += 1
    (directory / 'truth.json').write_text(json.dumps(truth), encoding='utf-8')
    manifest = {'source': 'fully synthetic', 'seed': seed, 'days': days,
                'rows': rows, 'packs': 6, 'cells_per_pack': 12,
                'topology': '2 modules x 6 series cells; single series string per pack',
                'injected_fault': 'SYN-003 module 2 cell 4, days >=30: -75 mV',
                'aging': 'SYN-005 accelerated linear capacity fade',
                'notice': 'Original generic simulation; no real customers, assets or telemetry.'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

