"""Field-data ingestion (Step 1A: outside data).

raw CSV exports (read-only) -> parsed rows -> quality controlled -> canonical 1-min -> canonical 5-min.
The same functions serve batch (re)training datasets and the real-time inference path.
"""
