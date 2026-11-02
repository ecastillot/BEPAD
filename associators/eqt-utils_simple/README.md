# eqt-utils_simple

The simple associator shipped with **EQTransformer**, adapted to BEPAD.

- **Original:** `EQTransformer/utils/associator.py` (`run_associator`) by S. Mostafa Mousavi —
  EQTransformer, Mousavi et al. (2020), *Nature Communications*.
  Code: https://github.com/smousavi05/EQTransformer — MIT License © 2020-2025 S. Mostafa Mousavi.
- This folder re-implements the idea for BEPAD windows; it is not a copy of that code.

## How it works

1. Each station has **detections**, each with a start time.
2. Time is cut into **fixed, non-overlapping windows of 15 s**.
3. Detections starting in the same window form an **event if they come from ≥ 3 stations**; smaller
   groups stay unassociated.
4. The event is placed **at the station of its first detection, 5 km deep**.

**Adaptation.** EQTransformer produces one detection per station and event (P, S and an event start
time). BEPAD gives single picks, so detections are rebuilt: a P and the next S at the same station
within `max_sp_s` form one detection that starts at the P time; a lone P or S is its own detection.
The origin time is the first arrival of the event.

It is fast and simple, and it shows the limits of fixed windows: earthquakes closer than 15 s merge,
and one earthquake whose arrivals span more than 15 s is split.

## Parameters

| Parameter | Meaning |
|---|---|
| `moving_window_s` | window length [s] (15, as in EQTransformer) |
| `pair_n` | minimum stations for an event (3) |
| `depth_km` | fixed depth of every event (5 km) |
| `max_sp_s` | longest S − P time when pairing picks into a detection (BEPAD adaptation) |
