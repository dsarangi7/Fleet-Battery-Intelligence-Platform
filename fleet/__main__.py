import argparse
import json
import logging
import signal
import threading
from pathlib import Path

from fleet.api import server
from fleet.pipeline import connect, ingest
from fleet.report import report
from fleet.synthetic import generate


def process(directory: Path, db_path: Path):
    db = connect(db_path)
    try:
        results = [ingest(db, path) for path in sorted(directory.glob('*.csv'))]
    finally:
        db.close()
    return results


def main():
    parser = argparse.ArgumentParser(description='Synthetic Fleet Battery Intelligence Platform')
    parser.add_argument('command', choices=['demo', 'ingest', 'schedule', 'serve', 'report'])
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--db', type=Path, default=None)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--interval', type=int, default=3600)
    args = parser.parse_args()
    db_path = args.db or args.data / 'warehouse.sqlite'
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.command == 'demo':
        if (args.data / 'synthetic.csv').exists():
            logging.info('Using existing synthetic.csv; generation skipped')
        else:
            generate(args.data)
        print(json.dumps(process(args.data, db_path), indent=2))
        db = connect(db_path)
        try:
            report(db, args.data)
        finally:
            db.close()
    elif args.command == 'ingest':
        print(json.dumps(process(args.data, db_path), indent=2))
    elif args.command == 'report':
        db = connect(db_path)
        try:
            report(db, args.data)
        finally:
            db.close()
    elif args.command == 'schedule':
        if args.interval < 1:
            parser.error('--interval must be positive')
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            try:
                logging.info('batch=%s', json.dumps(process(args.data, db_path)))
            except Exception:
                logging.exception('Batch failed; transaction rolled back; retry on next interval')
            stop.wait(args.interval)
    else:
        httpd = server(db_path, args.host, args.port)
        logging.info('API listening at http://%s:%s', args.host, args.port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()


if __name__ == '__main__':
    main()

