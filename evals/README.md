# Evaluation Harness

Run the deterministic release checks with:

```bash
.venv/bin/python evals/run_recorded_evals.py
```

The harness verifies the things most likely to create a convincingly wrong output: a causal claim must be time-eligible, cited, bounded by a visible confidence score, and visibly marked `UNCALIBRATED` until held-out calibration is complete.

The recorded BHP case is a regression fixture, not performance evidence. Live cases must be frozen as source snapshots before they enter the evaluation set. Add blind cases to `evals/cases/` only after their expected claims and source locators have been independently adjudicated.
