# Synthetic CSV Contract

Exact header order:

```csv
pack,module,cell,day,step,timestamp,voltage,current,temperature,reference_soc,nominal_ah
```

| Field | Contract |
| --- | --- |
| pack | SYN- followed by three digits |
| module / cell | Integers 1..2 / 1..6 |
| day / step | Integers 0..365 / 0..10 |
| timestamp | ISO-8601 with explicit timezone |
| voltage | Finite volts, 2..4.5 |
| current | Finite discharge amperes, >0..100 |
| temperature | Finite Celsius, -20..60 |
| reference_soc | Independent synthetic SOC %, 0..100 |
| nominal_ah | Finite rated capacity Ah, >0..1000 |

Rows failing validation are counted and quarantined by digest/line number.
Malformed file headers fail the whole transaction. Extra fields are rejected.
Session validation requires 11 ordered steps, strictly increasing timestamps,
intervals <=3600 seconds, constant rated capacity and decreasing reference SOC.
Missing steps or nonmonotonic time invalidate the complete session. No interpolation
is performed. A narrow SOC span leaves capacity and SOH null.

The allowed ranges are synthetic demo boundaries, not cell safety limits. Schema
checks do not establish physical plausibility or data provenance. Complete real
data ingestion would additionally need a trusted source identity, per-channel
calibration, asset calendar, clock synchronization and independent quality rules.

