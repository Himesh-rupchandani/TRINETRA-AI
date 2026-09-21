"""
TRINETRA AI - Evidence Vault with BSA 2023 & Section 65B Compliance
Superior Feature for Gujarat Police Hackathon

Implements:
- SHA256 hash chain for tamper-proof evidence (stored per record, recomputed on
  verification — never asserted)
- BSA 2023 Section 63 digital evidence certificate
- Section 65B Indian Evidence Act compliance
- Chain of custody tracking
- Tamper detection (modified sighting, modified record, broken chain)
- Court-admissible certificate generation

How verification actually works
------------------------------
Every sealed sighting gets one :class:`EvidenceRecord` row holding

* ``payload_json``  — the canonical snapshot of the immutable fields, and
* ``hash``          — SHA-256 over that snapshot *and* the previous link's hash,
* ``previous_hash`` — the hash of ``chain_index - 1`` (``GENESIS`` for the first).

``verify()`` then performs three independent checks and reports each finding:

1. **record integrity** — recompute the hash from the stored payload; a doctored
   ``hash``/``payload_json``/``previous_hash`` column no longer reproduces it;
2. **evidence integrity** — recompute the canonical payload from the live
   ``vehicle_events`` row and compare it field-by-field with the sealed
   snapshot, so an edited plate, timestamp, GPS fix or evidence path is named;
3. **chain integrity** — the stored ``previous_hash`` must equal the hash of the
   preceding link.

Nothing is asserted: ``court_admissible`` is only true when all three pass.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.models import EvidenceRecord, VehicleEvent
from ..utils.timestamps import iso_utc

# First link of the chain has no predecessor.
GENESIS = "GENESIS"

# Fields frozen into the seal. Anything here that changes after sealing is
# reported as tampering; anything *not* here (e.g. operator annotations) is
# deliberately excluded so lawful enrichment does not look like tampering.
IMMUTABLE_EVENT_FIELDS = (
    "event_id",
    "camera_id",
    "plate_number",
    "plate_raw",
    "plate_confidence",
    "vehicle_class",
    "event_time",
    "latitude",
    "longitude",
    "evidence_ref",
    "video_file",
    "video_offset_sec",
    "watchlist_match",
)

# Canonical API locations. The certificate used to advertise
# "/api/evidence/{id}/verify", which is not a route this backend serves — the
# real one lives under the /reports router.
VERIFY_URL_TEMPLATE = "/api/reports/evidence/{event_id}/verify"
CERTIFICATE_URL_TEMPLATE = "/api/reports/evidence/{event_id}/certificate"


def evidence_verify_url(event_id: Any) -> str:
    """Public verification endpoint for one sealed sighting."""
    return VERIFY_URL_TEMPLATE.format(event_id=event_id)


def evidence_certificate_url(event_id: Any) -> str:
    """Public BSA 2023 certificate endpoint for one sealed sighting."""
    return CERTIFICATE_URL_TEMPLATE.format(event_id=event_id)


class EvidenceStatus:
    """Verification outcomes (kept as plain strings for the wire contract)."""

    VALID = "VALID"
    TAMPERED = "TAMPERED"
    CHAIN_BROKEN = "CHAIN_BROKEN"
    NOT_SEALED = "NOT_SEALED"


def canonical_payload(event: VehicleEvent) -> Dict[str, Any]:
    """Canonical, hash-stable snapshot of one sighting's immutable fields.

    Timestamps are serialized as UTC with a ``Z`` suffix (``iso_utc``) so the
    hash does not depend on the server's local timezone or on SQLite returning
    naive datetimes.
    """
    return {
        "event_id": event.id,
        "camera_id": event.camera_id,
        "plate_number": event.plate_number,
        "plate_raw": event.plate_raw,
        "plate_confidence": (
            round(float(event.plate_confidence), 6)
            if event.plate_confidence is not None
            else None
        ),
        "vehicle_class": event.vehicle_class,
        "event_time": iso_utc(event.event_time) if event.event_time else None,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "evidence_ref": event.evidence_ref,
        "video_file": event.video_file,
        "video_offset_sec": (
            round(float(event.video_offset_sec), 3)
            if event.video_offset_sec is not None
            else None
        ),
        "watchlist_match": bool(event.watchlist_match),
    }


class EvidenceVault:
    """
    Tamper-proof evidence vault with BSA 2023 compliance.
    Every sealed sighting gets a SHA-256 hash linked to the previous hash
    (blockchain-style), stored in the database next to the snapshot it covers.
    """

    # ------------------------------------------------------------------ hashing
    @staticmethod
    def compute_hash(data: Dict[str, Any]) -> str:
        """Compute SHA256 over a canonicalized JSON payload."""
        canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_evidence_hash(
        payload: Dict[str, Any],
        previous_hash: Optional[str] = None,
    ) -> str:
        """Hash one link: the immutable snapshot plus its predecessor's hash."""
        linked = dict(payload)
        linked["previous_hash"] = previous_hash or GENESIS
        return EvidenceVault.compute_hash(linked)

    # ------------------------------------------------------------------- sealing
    def seal(
        self,
        db: Session,
        event: VehicleEvent,
        source: str = "CAPTURE",
    ) -> Optional[EvidenceRecord]:
        """Append one sighting to the hash chain. Idempotent per event.

        Returns the existing record when the event is already sealed, so calling
        this from both the ingestion pipeline and the certificate endpoint is
        safe. Failures are logged and swallowed by the caller — sealing must
        never break evidence ingestion.
        """
        existing = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.event_id == event.id)
            .first()
        )
        if existing is not None:
            return existing

        payload = canonical_payload(event)
        chain_index = int(
            db.query(func.count(EvidenceRecord.id)).scalar() or 0
        )
        previous = (
            db.query(EvidenceRecord)
            .order_by(EvidenceRecord.chain_index.desc())
            .first()
        )
        previous_hash = previous.hash if previous else None

        record = EvidenceRecord(
            event_id=event.id,
            camera_id=event.camera_id,
            chain_index=chain_index,
            payload_json=json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")),
            hash=self.compute_evidence_hash(payload, previous_hash),
            previous_hash=previous_hash,
            seal_source=source,
            sealed_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def record_for(
        self,
        db: Session,
        event_id: int,
    ) -> Optional[EvidenceRecord]:
        """Sealed record for an event, sealing it on demand when missing.

        Sightings created before the vault existed have no baseline; they are
        sealed lazily and marked ``BACKFILL`` so the certificate states plainly
        from which moment the chain covers them.
        """
        record = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.event_id == event_id)
            .first()
        )
        if record is not None:
            return record
        event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
        if event is None:
            return None
        try:
            return self.seal(db, event, source="BACKFILL")
        except Exception as exc:  # pragma: no cover - defensive
            db.rollback()
            logger.error(f"[EVIDENCE] backfill seal failed for event {event_id}: {exc}")
            return None

    # -------------------------------------------------------------- verification
    @staticmethod
    def _diff_fields(sealed: Dict[str, Any], current: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Field-level differences between the sealed snapshot and the live row."""
        diffs: List[Dict[str, Any]] = []
        for field in IMMUTABLE_EVENT_FIELDS:
            before = sealed.get(field)
            after = current.get(field)
            if before != after:
                diffs.append({"field": field, "sealed": before, "current": after})
        return diffs

    def verify(self, db: Session, event_id: int) -> Dict[str, Any]:
        """Verify one sealed sighting: record, evidence and chain integrity."""
        record = self.record_for(db, event_id)
        event = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
        if event is None:
            return {
                "event_id": event_id,
                "status": EvidenceStatus.NOT_SEALED,
                "tampered": False,
                "findings": ["EVENT_NOT_FOUND"],
                "court_admissible": False,
            }
        if record is None:
            return {
                "event_id": event_id,
                "status": EvidenceStatus.NOT_SEALED,
                "tampered": False,
                "findings": ["NO_EVIDENCE_RECORD"],
                "court_admissible": False,
                "detail": "Evidence could not be sealed; integrity is unproven.",
            }

        findings: List[str] = []
        sealed_payload = record.payload()
        current_payload = canonical_payload(event)

        # 1. Record integrity — does the stored hash still follow from the
        #    stored snapshot + stored predecessor?
        recomputed_from_record = self.compute_evidence_hash(
            sealed_payload, record.previous_hash
        )
        record_intact = recomputed_from_record == record.hash
        if not record_intact:
            findings.append("RECORD_HASH_MISMATCH")

        # 2. Evidence integrity — does the live row still match the seal?
        modified_fields = self._diff_fields(sealed_payload, current_payload)
        recomputed_from_evidence = self.compute_evidence_hash(
            current_payload, record.previous_hash
        )
        evidence_intact = recomputed_from_evidence == record.hash
        if modified_fields:
            findings.append("EVIDENCE_MODIFIED")

        # 3. Chain integrity — is the predecessor link the one recorded?
        predecessor = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.chain_index == record.chain_index - 1)
            .first()
            if record.chain_index > 0
            else None
        )
        expected_previous = predecessor.hash if predecessor else None
        chain_intact = (record.previous_hash or None) == expected_previous
        if not chain_intact:
            findings.append("CHAIN_BROKEN")

        if not findings:
            status = EvidenceStatus.VALID
        elif not chain_intact:
            # A re-pointed predecessor necessarily changes this link's own hash
            # too (previous_hash is hashed in), so check the chain first: the
            # meaningful verdict is "the chain no longer holds", not a generic
            # tamper flag.
            status = EvidenceStatus.CHAIN_BROKEN
        else:
            status = EvidenceStatus.TAMPERED

        return {
            "event_id": event_id,
            "evidence_hash": record.hash,
            "recomputed_hash": recomputed_from_evidence,
            "previous_hash": record.previous_hash or GENESIS,
            "chain_index": record.chain_index,
            "hash_algorithm": "SHA-256",
            "status": status,
            "tampered": status != EvidenceStatus.VALID,
            "findings": findings,
            "modified_fields": modified_fields,
            "checks": {
                "record_integrity": record_intact,
                "evidence_integrity": evidence_intact,
                "chain_integrity": chain_intact,
            },
            "chain_integrity": "INTACT" if chain_intact else "BROKEN",
            "sealed_at": iso_utc(record.sealed_at) if record.sealed_at else None,
            "seal_source": record.seal_source,
            "verified_at": iso_utc(),
            # Only an untampered, correctly-chained record is admissible.
            "court_admissible": status == EvidenceStatus.VALID,
            "bsa_2023_compliant": status == EvidenceStatus.VALID,
            "verification_method": (
                "SHA-256 recomputed from the sealed snapshot and the live record, "
                "then linked to the previous chain entry"
            ),
            "verification_url": evidence_verify_url(event_id),
        }

    def verify_chain(self, db: Session, limit: Optional[int] = None) -> Dict[str, Any]:
        """Walk the whole chain, recomputing every link.

        Unlike the previous implementation — which only compared each record's
        ``previous_hash`` with the hash handed to it in the same request — this
        reads the stored chain and recomputes each hash from its own snapshot,
        so a rewritten payload, a rewritten hash and a re-linked predecessor are
        all detected.
        """
        query = db.query(EvidenceRecord).order_by(EvidenceRecord.chain_index.asc())
        if limit:
            query = query.limit(limit)
        records = query.all()

        if not records:
            return {
                "valid": True,
                "status": EvidenceStatus.VALID,
                "total_records": 0,
                "tampered_indices": [],
                "broken_links": [],
                "verified_at": iso_utc(),
            }

        tampered_indices: List[int] = []
        broken_links: List[int] = []
        previous_hash: Optional[str] = None
        for position, record in enumerate(records):
            payload = record.payload()
            recomputed = self.compute_evidence_hash(payload, record.previous_hash)
            if recomputed != record.hash:
                tampered_indices.append(record.chain_index)
            expected_previous = previous_hash if position > 0 else None
            if (record.previous_hash or None) != expected_previous:
                broken_links.append(record.chain_index)
            previous_hash = record.hash

        valid = not tampered_indices and not broken_links
        return {
            "valid": valid,
            "status": (
                EvidenceStatus.VALID
                if valid
                else (
                    EvidenceStatus.CHAIN_BROKEN
                    if broken_links and not tampered_indices
                    else EvidenceStatus.TAMPERED
                )
            ),
            "total_records": len(records),
            "tampered_indices": tampered_indices,
            "broken_links": broken_links,
            "head_hash": records[-1].hash,
            "verified_at": iso_utc(),
        }


# One vault for the whole process; the chain lives in the database, not in
# memory (the previous revision kept a `self.chain` list that was never
# populated and never read — dead code next to a verify endpoint that could not
# actually detect anything).
evidence_vault = EvidenceVault()


def generate_bsa_certificate(
    event_data: Dict[str, Any],
    officer_name: str = "System Operator",
    officer_id: str = "TRINETRA-AI",
    case_number: Optional[str] = None,
    chain: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate BSA 2023 Section 63 compliant digital evidence certificate.
    Also compliant with Section 65B of Indian Evidence Act.

    ``chain`` is the live :meth:`EvidenceVault.verify` result for this event.
    When supplied, the certificate carries the *sealed* hash and reports the
    real integrity verdict instead of asserting ``tamper_proof: True`` and
    ``court_admissible: True`` for evidence nobody checked.
    """
    now = datetime.now(timezone.utc)
    event_id = event_data.get("id")

    # Fallback payload (only used when no sealed record was supplied).
    evidence_payload = {
        "event_id": event_id,
        "camera_id": event_data.get("camera_id"),
        "plate": event_data.get("plate_number"),
        "timestamp": iso_utc(event_data.get("event_time"))
        if isinstance(event_data.get("event_time"), datetime)
        else str(event_data.get("event_time")),
        "evidence_ref": event_data.get("evidence_ref"),
        "location": event_data.get("location")
        or f"{event_data.get('latitude')}, {event_data.get('longitude')}",
    }
    fallback_hash = hashlib.sha256(
        json.dumps(evidence_payload, sort_keys=True, default=str).encode()
    ).hexdigest()

    verification = chain or {}
    evidence_hash = verification.get("evidence_hash") or fallback_hash
    previous_hash = verification.get("previous_hash") or event_data.get("previous_hash") or GENESIS
    status = verification.get("status") or EvidenceStatus.NOT_SEALED
    verified = status == EvidenceStatus.VALID

    # Generate certificate ID
    cert_id = f"BSA-{now.strftime('%Y%m%d')}-{evidence_hash[:8].upper()}"

    certificate = {
        "certificate_id": cert_id,
        "certificate_type": "BSA 2023 Section 63 - Digital Evidence Certificate",
        "compliance": {
            "bsa_2023_section_63": True,
            "section_65b_indian_evidence_act": True,
            # Reported from the actual verification, never asserted.
            "court_admissible": verified,
            "tamper_proof": verified,
        },
        "evidence_details": {
            "event_id": event_id,
            "camera_id": event_data.get("camera_id"),
            "camera_name": event_data.get("camera_name", event_data.get("camera_id")),
            "plate_number": event_data.get("plate_number"),
            "plate_confidence": event_data.get("plate_confidence"),
            "vehicle_class": event_data.get("vehicle_class"),
            "timestamp": iso_utc(event_data.get("event_time"))
            if isinstance(event_data.get("event_time"), datetime)
            else str(event_data.get("event_time")),
            "location": evidence_payload["location"],
            "latitude": event_data.get("latitude"),
            "longitude": event_data.get("longitude"),
            "evidence_ref": event_data.get("evidence_ref"),
            "evidence_hash_sha256": evidence_hash,
            "hash_algorithm": "SHA-256",
            "previous_hash": previous_hash,
            "chain_index": verification.get("chain_index"),
            "sealed_at": verification.get("sealed_at"),
            "seal_source": verification.get("seal_source"),
            "video_file": event_data.get("video_file"),
            "video_offset_sec": event_data.get("video_offset_sec"),
        },
        "technical_details": {
            "capture_method": "Automated CCTV ANPR - YOLO11 + OCR",
            "system": "TRINETRA AI - Intelligent Vision. Faster Response.",
            "version": "1.0.0",
            "ai_model": "YOLO11s + RapidOCR",
            "confidence_threshold": 0.45,
            "pts_based_timing": True,
            "chain_of_custody_maintained": verified,
            "original_untampered": verified,
        },
        "certification": {
            "certified_by": officer_name,
            "officer_id": officer_id,
            "designation": "Control Room Operator - TRINETRA AI",
            "certified_at": iso_utc(now),
            "certificate_valid_till": "Perpetual - Evidence hash immutable",
            "digital_signature": hashlib.sha256(
                f"{cert_id}{officer_id}{now.isoformat()}".encode()
            ).hexdigest()[:32],
            "case_number": case_number or f"CASE-{now.strftime('%Y%m%d')}-{event_id or '0000'}",
            "jurisdiction": "Gujarat Police - Statewide CCTV Network",
            "issuing_authority": "TRINETRA AI Evidence Vault",
        },
        "legal_statements": {
            "bsa_2023_section_63": (
                "This certificate is issued under Section 63 of Bharatiya Sakshya Adhiniyam, 2023 "
                "which deals with admissibility of electronic records. The electronic record herein "
                "was produced by a computer in regular use, with information regularly fed in ordinary course, "
                "and the computer was operating properly throughout."
            ),
            "section_65b": (
                "This certificate complies with Section 65B of Indian Evidence Act, 1872 (as amended) "
                "for secondary evidence of electronic records. The conditions under Section 65B(2) are satisfied: "
                "(a) computer output produced in regular use, (b) information regularly fed, "
                "(c) computer operating properly, (d) information reproduced from regular activity."
            ),
            "tamper_proof": (
                f"Evidence integrity verified by recomputing SHA-256 {evidence_hash} from the sealed "
                "snapshot and the stored record, then re-linking it to the previous chain entry. "
                "Any alteration to the electronic record changes the hash and is reported as TAMPERED."
                if verified
                else f"Integrity check returned {status}: "
                f"{', '.join(verification.get('findings') or ['evidence not sealed'])}. "
                "This certificate is issued for record only and must not be tendered as untampered evidence."
            ),
            "court_admissible": (
                "This evidence is court-admissible under BSA 2023 and is accompanied by this certificate "
                "as required by law. The hash chain provides proof of no tampering since capture."
                if verified
                else "Integrity could NOT be established for this record; admissibility is not asserted."
            ),
        },
        "verification": {
            "status": status,
            "findings": verification.get("findings") or [],
            "modified_fields": verification.get("modified_fields") or [],
            "can_verify_online": True,
            # Real, served routes (the certificate used to print
            # "/api/evidence/{id}/verify", which does not exist).
            "verification_url": evidence_verify_url(event_id),
            "certificate_url": evidence_certificate_url(event_id),
            "verified_at": verification.get("verified_at") or iso_utc(now),
            "qr_code_data": f"TRINETRA:{cert_id}:{evidence_hash}",
            "public_key_fingerprint": hashlib.sha256(
                b"TRINETRA_AI_GUJARAT_POLICE_2026"
            ).hexdigest()[:16],
        },
    }

    return certificate


def generate_printable_report_data(
    alert_or_vehicle: Dict[str, Any],
    report_type: str = "ALERT",
    generated_by: str = "TRINETRA AI System"
) -> Dict[str, Any]:
    """Generate data for printable report (PDF-ready)."""
    now = datetime.now(timezone.utc)

    return {
        "report_id": f"RPT-{now.strftime('%Y%m%d%H%M%S')}-{hashlib.sha256(str(now).encode()).hexdigest()[:6].upper()}",
        "report_type": report_type,
        "generated_at": iso_utc(now),
        "generated_by": generated_by,
        "system": "TRINETRA AI - Gujarat Police Innovation Hackathon 2026",
        "classification": "RESTRICTED - Law Enforcement Use Only",
        "data": alert_or_vehicle,
        "footer": {
            "disclaimer": "This report is system-generated and contains sensitive law enforcement data. Handle as per Gujarat Police data handling guidelines.",
            "validity": "Valid at time of generation. Real-time data may have changed.",
            "contact": "TRINETRA AI Control Room - Gujarat Police"
        }
    }
