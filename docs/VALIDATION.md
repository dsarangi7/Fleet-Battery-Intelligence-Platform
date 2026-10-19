# Validation Evidence

Validated locally on 2026-10-19.

Dashboard follow-up: verified rendering in the in-app browser at a narrow viewport,
pack filtering, seven-day trend selection, and the no-alert empty state. Tests now
also verify HTML/CSS/JavaScript delivery and the relocated `/api` index. Desktop
breakpoints are implemented but were not separately viewport-tested.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 12 tests passed |
| `python -m compileall -q fleet tests` | Passed |
| `python -m fleet demo` | 35,640 rows accepted, 0 rejected |
| Repeat demo ingestion | already_processed; one ingestion run retained |
| Live API `/health` | HTTP 200, ready=true, runs=1 |
| Live API `/api/quality_summary?limit=1` | HTTP 200; 12 cells, 0 missing, 0 invalid |
| API invalid resource / invalid limit tests | HTTP 404 / 400 |
| Docker runtime | Not executed: Docker is not installed on this host |
| GitHub CI | Workflow supplied; remote execution has not been performed |

The tests cover deterministic fault recovery, observed aging slope, series-string
throughput, hierarchy counts, file idempotency, duplicate/conflicting samples,
invalid numbers and identifiers, incomplete sessions, transactional rollback,
unsupported-condition abstention, scheduler retry and API responses.

## Seed-17 evaluation

Days 0-9 form the baseline. Days 10-44 yield 2,520 held-out cell sessions:

| Result | Count |
| --- | --- |
| True positives | 15 |
| False positives | 0 |
| True negatives | 2,505 |
| False negatives | 0 |
| Unscored held-out sessions | 0 |

Precision and recall are both 1.0 for this intentionally simple injected scenario.
The simulated accelerated-aging pack recovers a -0.15 SOH percentage-point/day
slope and -6.6 percentage points across 45 observations. These are simulation
verification results, not estimates of field performance.

## Boundaries of verification

Docker configuration and GitHub CI must still run on a Docker-capable host.
The scheduler's interval and retry behavior are tested with a controlled clock;
no multi-day soak or concurrent multi-writer test has been performed. The API is
a local read-only demonstration server. No real battery/customer data, production
network, operational controls or external publication was accessed.

