# Metric Definitions

The topology is a single series string per pack: two modules with six cells each.
Positive current means discharge. Session timestamps are timezone-aware and
normalized to UTC. Each session contains steps 0 through 10.

## SOC, capacity and SOH

Discharged charge uses trapezoidal integration:

`Q_Ah = sum((I[k] + I[k-1]) / 2 * dt_seconds / 3600)`

`SOC_end_pct = reference_SOC_start_pct - 100 * Q_Ah / nominal_capacity_Ah`

This SOC estimate assumes known initial SOC and nominal capacity, and accumulates
error as capacity fades. It is not an EKF, OCV-calibrated estimator or production
BMS replacement. Estimates are not silently clamped, so inconsistent inputs stay
visible. Charging/regeneration and rest periods are outside this input contract.

`capacity_Ah = Q_Ah / ((reference_SOC_start - reference_SOC_end) / 100)`

`SOH_pct = 100 * capacity_Ah / nominal_capacity_Ah`

Capacity estimates require at least a 50-percentage-point reference SOC span.
Here reference SOC is independently known from the synthetic experiment. Using
BMS SOC derived from the same current integral as the denominator would be
circular. Real validation needs an independent reference capacity/SOC procedure.
The simulation changes discharge duration to encode capacity fade; the metric
recovery test verifies that encoding, not real-world estimator accuracy.

## Hierarchy

Cell metrics retain capacity, SOH, nominal-capacity SOC, throughput and alert
evidence. Module SOH is an arithmetic mean plus weakest-cell SOH. Pack SOH is
also a descriptive mean plus weakest cell, not a certified usable-pack capacity.
Pack charge throughput is the **mean** cell integral for this series topology;
summing across series cells would overcount it. Fleet SOH equally weights packs
because all demo packs have the same nominal capacity. Heterogeneous fleets need
capacity-weighted aggregation. Maximum same-step cell voltage spread is in mV.

Invalid sessions retain null metrics and a reason status. SQL averages exclude
nulls. Always read `quality_summary` alongside aggregates: partial data must not
be mistaken for a complete pack. Entirely absent pack/day records cannot be
detected without an expected asset/session calendar; this is a documented gap.

## Condition-matched voltage detection

1. Build baselines from complete sessions on days 0-9 only.
2. Group voltage by rounded SOC/10, discharge C-rate/0.1 and temperature/10.
   Python's round uses ties-to-even; these are explicitly demo bin definitions.
3. Store median voltage and robust scale `max(1.4826 * MAD, 3 mV)` per bin.
4. On days >=10, require all 11 samples to have >=20 baseline peers.
5. A sample deviates when absolute residual exceeds `max(6 * scale, 25 mV)`.
6. Alert a cell session when at least three samples deviate.

The output preserves median absolute residual, minimum peer count and status.
Baseline sessions are not scored. Unknown conditions are marked insufficient_peers
with null alert status, never reported as healthy. Training is chronologically
separate from evaluation; injected labels never enter ingestion or transforms.

The 10-day early window is assumed nominal in this simulation. Contaminated
baselines, condition-bin boundaries, sensor drift, correlated peer faults and
unseen chemistry can invalidate results. Coarse matching can absorb real faults;
no universal diagnostic threshold is claimed. Alerts indicate investigation
candidates, not root-cause classifications or protection commands.

## Degradation

An ordinary least-squares slope of pack SOH against observed day is reported in
percentage points/day, along with total observed change. At least two observations
are required. The simulation includes accelerated linear fading for one pack.
There is no remaining-useful-life forecast, chemistry aging model or causal claim.

