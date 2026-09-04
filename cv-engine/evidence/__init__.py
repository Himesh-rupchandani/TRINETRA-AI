"""Evidence capture package (JPEG frame + plate crop writer)."""
from .evidence_writer import EvidenceWriter, sanitize

__all__ = ["EvidenceWriter", "sanitize"]
