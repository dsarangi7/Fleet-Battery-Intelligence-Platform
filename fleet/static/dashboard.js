'use strict';
const $ = (id) => document.getElementById(id);
let store = null;
const number = (value, digits = 1, unit = '') => Number.isFinite(value) ? value.toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits}) + unit : '--';
const sum = (rows, field) => rows.reduce((total, row) => total + (row[field] ?? 0), 0);
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function badge(text, mode = '') { return node('span', text, `badge ${mode}`); }
function tableRow(values) {
  const row = node('tr');
  values.forEach(value => { const cell = node('td'); cell.append(value instanceof Node ? value : document.createTextNode(String(value))); row.append(cell); });
  return row;
}
function emptyRow(columns, message) {
  const row = node('tr'); const cell = node('td', message, 'empty'); cell.colSpan = columns; row.append(cell); return row;
}
function svgNode(tag, attrs, text) {
  const item = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => item.setAttribute(key, value));
  if (text !== undefined) item.textContent = text;
  return item;
}
function drawTrend() {
  const selected = $('pack').value;
  const windowDays = $('window').value;
  const lastDay = Math.max(...store.pack_daily.map(row => row.day));
  const rows = store.pack_daily.filter(row => (selected === 'all' || row.pack === selected) &&
    (windowDays === 'all' || row.day > lastDay - Number(windowDays)) && Number.isFinite(row.soh_pct));
  $('fleet-chart').replaceChildren(); $('legend').replaceChildren();
  if (!rows.length) { $('fleet-chart').append(node('p', 'No capacity observations in this window.', 'empty')); return; }
  const packs = [...new Set(rows.map(row => row.pack))].sort();
  const allPacks = [...new Set(store.pack_daily.map(row => row.pack))].sort();
  const width = Math.max(300, $('fleet-chart').clientWidth), height = $('fleet-chart').clientHeight;
  const left = 46, right = width - 12, top = 18, bottom = height - 28;
  const minDay = Math.min(...rows.map(row => row.day)), maxDay = Math.max(...rows.map(row => row.day));
  const lo = Math.floor(Math.min(...rows.map(row => row.soh_pct)) - 0.3), hi = Math.ceil(Math.max(...rows.map(row => row.soh_pct)) + 0.1);
  const x = day => left + (day - minDay) / Math.max(1, maxDay - minDay) * (right - left);
  const y = soh => bottom - (soh - lo) / Math.max(1, hi - lo) * (bottom - top);
  const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-labelledby': 'chart-title chart-description'});
  svg.append(svgNode('title', {id: 'chart-title'}, 'Observed pack capacity SOH'));
  svg.append(svgNode('desc', {id: 'chart-description'}, `Days ${minDay} to ${maxDay}. ${packs.map(pack => { const series = rows.filter(r => r.pack === pack).sort((a,b) => a.day-b.day); return `${pack}: ${number(series[0].soh_pct)} to ${number(series.at(-1).soh_pct)} percent`; }).join('. ')}.`));
  for (let i = 0; i <= 4; i++) {
    const value = lo + (hi - lo) * i / 4;
    svg.append(svgNode('line', {x1:left, x2:right, y1:y(value), y2:y(value), class:'grid-line'}));
    svg.append(svgNode('text', {x:left-8, y:y(value)+4, 'text-anchor':'end'}, `${value.toFixed(0)}%`));
    const day = Math.round(minDay + (maxDay - minDay) * i / 4);
    svg.append(svgNode('text', {x:x(day), y:height-5, 'text-anchor':'middle'}, `D${day}`));
  }
  packs.forEach(pack => {
    const series = rows.filter(row => row.pack === pack).sort((a,b) => a.day - b.day);
    const color = allPacks.indexOf(pack) % 6;
    const line = svgNode('polyline', {points:series.map(row => `${x(row.day)},${y(row.soh_pct)}`).join(' '), class:`series-${color}`});
    line.append(svgNode('title', {}, `${pack}: ${number(series.at(-1).soh_pct, 2, '%')} at D${series.at(-1).day}`)); svg.append(line);
    const label = node('span', undefined, `color-${color}`); label.append(node('i'), document.createTextNode(pack)); $('legend').append(label);
  });
  $('fleet-chart').append(svg);
}
function renderDetails() {
  const selected = $('pack').value, mode = $('session-filter').value;
  const latest = Math.max(...store.pack_daily.map(row => row.day));
  const packs = store.pack_daily.filter(row => row.day === latest && (selected === 'all' || row.pack === selected));
  $('pack-rows').replaceChildren();
  packs.forEach(pack => {
    const trend = store.degradation.find(row => row.pack === pack.pack);
    const quality = store.quality_summary.find(row => row.pack === pack.pack && row.day === pack.day);
    const asset = node('div'); const button = node('button', pack.pack); button.type = 'button'; button.setAttribute('aria-label', `Filter details to ${pack.pack}`);
    button.addEventListener('click', () => { $('pack').value = pack.pack; renderDetails(); });
    asset.append(button, node('small', `${pack.cells} observed cells / 2 modules`));
    const status = (quality?.missing_cells || quality?.invalid_sessions) ? badge('Quality review') :
      pack.anomalies > 0 ? badge('Voltage alert') : trend?.slope_pp_per_day < -0.1 ? badge('Capacity review') :
      quality?.scored_sessions < 12 ? badge('Unscored', 'neutral') : badge('No voltage alert', 'ok');
    $('pack-rows').append(tableRow([asset, status, number(pack.soh_pct, 1, '%'), number(pack.weakest_soh_pct, 1, '%'), number(pack.soc_pct, 1, '%'), number(pack.voltage_spread_mv, 1, ' mV'), number(trend?.slope_pp_per_day, 3, ' pp/day')]));
  });
  const cells = store.cell_metrics.filter(row => (selected === 'all' || row.pack === selected) &&
    (mode === 'all' || (mode === 'alerts' ? row.anomaly === 1 : row.anomaly === null)))
    .sort((a,b) => b.day-a.day || a.pack.localeCompare(b.pack) || a.module-b.module || a.cell-b.cell).slice(0,50);
  $('diagnostic-rows').replaceChildren();
  cells.forEach(row => $('diagnostic-rows').append(tableRow([`${row.pack} / M${row.module} / C${row.cell}`, `D${row.day}`, number(row.voltage_residual_mv, 1, ' mV'), number(row.baseline_count, 0), number(row.soh_pct, 1, '%'), row.anomaly === 1 ? badge('Voltage alert') : badge(row.status.replaceAll('_',' '), row.anomaly === 0 ? 'ok' : 'neutral')])));
  if (!cells.length) $('diagnostic-rows').append(emptyRow(6, 'No sessions match the selected pack and status.'));
  if (!packs.length) $('pack-rows').append(emptyRow(7, 'No packs observed on the latest fleet day.'));
  drawTrend();
}
function render() {
  const latestDay = Math.max(...store.pack_daily.map(row => row.day));
  const latest = store.pack_daily.filter(row => row.day === latestDay);
  const quality = store.quality_summary.filter(row => row.day === latestDay);
  const fleet = store.fleet_daily.find(row => row.day === latestDay);
  $('pack-count').textContent = number(latest.length, 0);
  $('cell-count').textContent = `${number(sum(latest,'cells'), 0)} observed cells / latest day`;
  $('fleet-soh').textContent = number(fleet?.mean_soh_pct, 1, '%');
  $('alert-count').textContent = latest.some(row => row.anomalies !== null) ? number(sum(latest,'anomalies'), 0) : '--';
  const observed = sum(quality,'observed_cells');
  $('coverage').textContent = observed ? number(100 * sum(quality,'scored_sessions') / observed, 0, '%') : '--';
  const selected = $('pack').value;
  $('pack').replaceChildren(new Option('All packs','all'));
  [...new Set(store.pack_daily.map(row => row.pack))].sort().forEach(pack => $('pack').add(new Option(pack,pack)));
  if ([...$('pack').options].some(option => option.value === selected)) $('pack').value = selected;
  $('signals').replaceChildren();
  function signal(pack, label, description) {
    const item = node('a', undefined, 'signal'); item.href = '#assets';
    item.addEventListener('click', () => { $('pack').value = pack; renderDetails(); });
    const head = node('div', undefined, 'signal-top'); head.append(node('strong',pack),badge(label));
    item.append(head,node('p',description)); $('signals').append(item);
  }
  latest.filter(row => row.anomalies > 0).forEach(row => signal(row.pack,'Voltage deviation',`${row.anomalies} cell session flagged on D${latestDay}. Inspect residuals and matched baseline evidence.`));
  store.degradation.filter(row => row.slope_pp_per_day < -0.1).forEach(row => signal(row.pack,'Capacity trend',`${number(row.soh_change_pp, 1)} pp observed change. Review-queue cutoff: slope below -0.100 pp/day (demo rule).`));
  if (!$('signals').children.length) $('signals').append(node('p','No signals meet the demo review rules. Check coverage before interpreting this result.','section-description'));
  $('accepted').textContent = number(sum(store.ingestion_runs,'accepted'),0);
  $('rejected').textContent = number(sum(store.ingestion_runs,'rejected'),0);
  $('invalid').textContent = number(sum(store.quality_summary,'invalid_sessions'),0);
  $('missing').textContent = number(sum(store.quality_summary,'missing_cells'),0);
  const firstDay = Math.min(...store.pack_daily.map(row => row.day));
  $('run-status').textContent = `Warehouse connected / D${firstDay}-D${latestDay} / ${store.ingestion_runs.length} processed batch${store.ingestion_runs.length === 1 ? '' : 'es'}`;
  renderDetails();
}
async function load() {
  $('refresh').disabled = true;
  $('run-status').textContent = 'Refreshing warehouse snapshot...';
  $('error').hidden = true;
  try {
    const names = ['fleet_daily','pack_daily','cell_metrics','degradation','quality_summary','ingestion_runs'];
    const entries = await Promise.all(names.map(async name => {
      const response = await fetch(`/api/${name}?limit=10000`);
      if (!response.ok) throw new Error(`Warehouse query failed (${response.status}).`);
      const body = await response.json();
      if (!Array.isArray(body.rows)) throw new Error('Unexpected warehouse response.');
      if (body.rows.length === 10000) throw new Error('Result limit reached. This dashboard requires a complete demo dataset.');
      return [name,body.rows];
    }));
    const next = Object.fromEntries(entries);
    if (!next.pack_daily.length) throw new Error('No pack observations available. Run the demo ingestion first.');
    store = next; render();
  } catch (error) {
    $('error').hidden = false;
    $('error').textContent = `${error.message} Use Refresh data to retry.`;
    $('run-status').textContent = store ? 'Refresh failed / previous snapshot shown' : 'Warehouse unavailable';
  } finally { $('refresh').disabled = false; }
}
$('refresh').addEventListener('click', load);
$('pack').addEventListener('change', () => { if(store) renderDetails(); });
$('session-filter').addEventListener('change', () => { if(store) renderDetails(); });
$('window').addEventListener('change', () => { if(store) drawTrend(); });
new ResizeObserver(() => { if(store) drawTrend(); }).observe($('fleet-chart'));
load();
