"""Export a reproducible synthetic snapshot for GitHub Pages."""
import json
import shutil
from pathlib import Path
from fleet.pipeline import connect, records, ALLOWED_TABLES


def main():
    output = Path('_site')
    output.mkdir(exist_ok=True)
    (output / 'api').mkdir(exist_ok=True)
    source = Path(__file__).with_name('static')
    html = (source / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<html lang="en">', '<html lang="en" data-static="true">')
    html = html.replace('href="/dashboard.css"', 'href="dashboard.css"').replace('src="/dashboard.js"', 'src="dashboard.js"')
    html = html.replace('href="/"', 'href="./"').replace('href="/api"', 'href="api/index.json"').replace('href="/api/quality_issues"', 'href="api/quality_issues.json"')
    html = html.replace('Original synthetic telemetry', 'Published synthetic snapshot')
    (output / 'index.html').write_text(html, encoding='utf-8')
    for name in ['dashboard.css', 'dashboard.js']:
        shutil.copyfile(source / name, output / name)
    db = connect(Path('data/warehouse.sqlite'))
    try:
        for table in sorted(ALLOWED_TABLES):
            rows = records(db, table, 10000)
            (output / 'api' / f'{table}.json').write_text(json.dumps({'rows': rows, 'data_source': 'synthetic snapshot'}), encoding='utf-8')
    finally:
        db.close()
    (output / 'api/index.json').write_text(json.dumps({'resources': [f'{t}.json' for t in sorted(ALLOWED_TABLES)], 'mode': 'Static synthetic snapshot; Python processing runs during deployment.'}), encoding='utf-8')


if __name__ == '__main__':
    main()
