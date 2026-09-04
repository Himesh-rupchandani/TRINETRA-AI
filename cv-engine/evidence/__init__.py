"""Evidence capture package for the Trinetra CV engine.

Stores the CCTV frame and plate crop backing every vehicle event so the
investigation UI can show real, verifiable evidence instead of a placeholder.
"""
from .evidence_writer import EvidenceWriter, sanitize

__all__ = ["EvidenceWriter", "sanitize"]
