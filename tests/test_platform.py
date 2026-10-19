import csv
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fleet.api import server
from fleet.pipeline import connect, ingest, validate, records
from fleet.report import evaluate
from fleet.synthetic import FIELDS, generate
from fleet.__main__ import main


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        generate(cls.root)
        cls.db_path = cls.root / 'warehouse.sqlite'
        cls.db = connect(cls.db_path)
        cls.addClassCleanup(cls.db.close)
        cls.result = ingest(cls.db, cls.root / 'synthetic.csv')

    def test_ingestion_count_and_idempotency(self):
        self.assertEqual(self.result['accepted'], 45 * 6 * 12 * 11)
        self.assertEqual(ingest(self.db, self.root / 'synthetic.csv')['status'], 'already_processed')
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_runs').fetchone()[0], 1)

    def test_metric_hierarchy_and_series_throughput(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM fleet_daily').fetchone()[0], 45)
        self.assertEqual(self.db.execute('SELECT count(*) FROM module_daily').fetchone()[0], 540)
        row = self.db.execute("SELECT * FROM pack_daily WHERE pack='SYN-001' AND day=0").fetchone()
        self.assertEqual(row['cells'], 12)
        self.assertAlmostEqual(row['throughput_ah'], 60, places=5)
        self.assertAlmostEqual(row['soh_pct'], 100, places=5)
        self.assertAlmostEqual(row['soc_pct'], 20, places=5)

    def test_aging_slope(self):
        row = self.db.execute("SELECT * FROM degradation WHERE pack='SYN-005'").fetchone()
        self.assertAlmostEqual(row['slope_pp_per_day'], -0.15, places=5)
        self.assertAlmostEqual(row['soh_change_pp'], -6.6, places=5)

    def test_fault_evaluation(self):
        result = evaluate(self.db, self.root / 'truth.json')
        self.assertEqual(result['tp'], 15)
        self.assertEqual(result['fn'], 0)
        self.assertEqual(result['fp'], 0)
        self.assertEqual(result['unscored'], 0)

    def test_no_alerts_in_training(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM cell_metrics WHERE day < 10 AND anomaly IS NOT NULL').fetchone()[0], 0)

    def test_scheduler_ticks_and_recovers(self):
        with patch('fleet.__main__.threading.Event') as event, patch('fleet.__main__.signal.signal'), \
             patch('fleet.__main__.process', side_effect=[RuntimeError('batch failed'), []]) as batch, \
             patch('sys.argv', ['fleet', 'schedule', '--interval', '1']), \
             self.assertLogs(level='INFO'):
            event.return_value.is_set.side_effect = [False, False, True]
            main()
            self.assertEqual(batch.call_count, 2)
            self.assertEqual(event.return_value.wait.call_count, 2)

    def test_unknown_conditions_abstain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'unknown.csv'
            with (self.root / 'synthetic.csv').open() as source:
                rows = [r for r in csv.DictReader(source) if r['pack'] == 'SYN-001'
                        and r['module'] == '1' and r['cell'] == '1' and r['day'] == '12']
            for row in rows:
                row['temperature'] = '55'
            with path.open('w', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            db = connect(root / 'test.sqlite')
            try:
                ingest(db, path)
                metric = db.execute('SELECT * FROM cell_metrics').fetchone()
                self.assertEqual(metric['status'], 'insufficient_peers')
                self.assertIsNone(metric['anomaly'])
                quality = db.execute('SELECT * FROM quality_summary').fetchone()
                self.assertEqual(quality['missing_cells'], 11)
            finally:
                db.close()

    def test_query_allowlist(self):
        with self.assertRaises(ValueError):
            records(self.db, 'telemetry; DROP TABLE telemetry')

    def first_row(self):
        with (self.root / 'synthetic.csv').open() as source:
            return next(csv.DictReader(source))

    def test_nonfinite_private_id_and_timezone_rejected(self):
        for key, value in [('voltage', 'NaN'), ('current', 'inf'), ('reference_soc', '101'),
                           ('pack', 'CUSTOMER-1'), ('timestamp', '2026-01-01T00:00:00')]:
            with self.subTest(key=key):
                row = self.first_row()
                row[key] = value
                with self.assertRaises(ValueError):
                    validate(row)

    def test_quality_and_incomplete_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'input.csv'
            good = self.first_row()
            bad = dict(good, voltage='NaN')
            conflict = dict(good, voltage='3.5')
            with path.open('w', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows([good, good, conflict, bad])
            db = connect(root / 'test.sqlite')
            try:
                result = ingest(db, path)
                self.assertEqual((result['accepted'], result['rejected'], result['duplicates']), (1, 2, 1))
                metric = db.execute('SELECT * FROM cell_metrics').fetchone()
                self.assertEqual(metric['status'], 'invalid_session')
                self.assertIsNone(metric['soh_pct'])
                self.assertIsNone(metric['anomaly'])
            finally:
                db.close()

    def test_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(Path(tmp) / 'test.sqlite')
            try:
                with patch('fleet.pipeline.recompute', side_effect=RuntimeError('test failure')):
                    with self.assertRaises(RuntimeError):
                        ingest(db, self.root / 'synthetic.csv')
                self.assertEqual(db.execute('SELECT count(*) FROM telemetry').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT count(*) FROM ingestion_runs').fetchone()[0], 0)
            finally:
                db.close()

    def test_api(self):
        httpd = server(self.db_path, '127.0.0.1', 0)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        try:
            for endpoint, content_type, marker in [('/', 'text/html', b'Fleet Battery Intelligence'),
                ('/dashboard.css', 'text/css', b'@media'),
                ('/dashboard.js', 'text/javascript', b'async function load')]:
                with urllib.request.urlopen(base + endpoint) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(content_type, response.headers['Content-Type'])
                    self.assertIn(marker, response.read())
                    self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
            with urllib.request.urlopen(base + '/api') as response:
                self.assertEqual(json.load(response)['project'], 'Fleet Battery Intelligence Platform')
            for endpoint in ['/health', '/api/fleet_daily?limit=2', '/api/degradation']:
                with urllib.request.urlopen(base + endpoint) as response:
                    self.assertEqual(response.status, 200)
                    json.load(response)
            for endpoint, status in [('/missing', 404), ('/api/fleet_daily?limit=0', 400),
                                      ('/api/fleet_daily?limit=oops', 400)]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + endpoint)
                self.assertEqual(error.exception.code, status)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
