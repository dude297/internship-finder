"""Automated opportunity ingestion (ADR-008).

adapters/   fetch-URL construction, top-level validation, item normalization (no database)
http.py     the only network client: allowlisted HTTPS hosts, timeouts, size and retry limits
normalize.py the typed adapter output and shared helpers (HTML to text, identities)
pipeline.py the only writer: dedupe, persist, evaluate, close, run summary
"""
