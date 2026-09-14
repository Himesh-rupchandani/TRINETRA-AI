"""Evidence capture package (spec §20).

Writes JPEG evidence artifacts for *significant* sighting events only — never
per frame. The pipeline decides when to capture; this package only knows how to
store a frame deterministically and safely.
"""
from .evidence_writer import EvidenceWriter, sanitize

__all__ = ["EvidenceWriter", "sanitize"]
