"""
Officer roster — demo/seed data for the Officer Profile section.

Each officer is built from their OWN plate + challan records only; aggregate
figures are derived per officer and never mixed across officers. This mirrors
the frontend mock roster 1:1 so LIVE mode shows the same profiles.
"""
from __future__ import annotations

from typing import Dict, List, Optional

CURRENT_OFFICER_ID = "OFF-02471"


def _build_officer(
    officer_id: str,
    name: str,
    photo_url: str,
    police_id: str,
    department: str,
    designation: str,
    plates: List[str],
    challans: List[dict],
) -> dict:
    unique_plates = list(dict.fromkeys(plates))
    total_challan_amount = sum(c["amount"] for c in challans)
    total_amount_collected = sum(c["amount_paid"] for c in challans)
    net_revenue = sum(c["amount_paid"] for c in challans if c["status"] == "PAID")
    return {
        "officer_id": officer_id,
        "name": name,
        "photo_url": photo_url,
        "police_id": police_id,
        "department": department,
        "designation": designation,
        "vehicles_caught": len(unique_plates),
        "total_challans": len(challans),
        "total_challan_amount": total_challan_amount,
        "total_amount_collected": total_amount_collected,
        "net_revenue": net_revenue,
        "plates": unique_plates,
    }


def _roster() -> List[dict]:
    return [
        _build_officer(
            officer_id="OFF-02471",
            name="Insp. Anjali Deshmukh",
            photo_url="/officer-profile.jpg",
            police_id="GJ-02471",
            department="Gujarat Police · Traffic Control",
            designation="Senior Officer",
            plates=[
                "GJ01AB1234", "GJ05XY4321", "GJ18MH0099", "GJ03JK6671",
                "GJ06RT2210", "MH12QE3344", "GJ12PL8080", "GJ09WD5543",
                "RJ14TU7071", "GJ07BM4412",
            ],
            challans=[
                {"plate": "GJ01AB1234", "amount": 2000, "amount_paid": 2000, "status": "PAID"},
                {"plate": "GJ05XY4321", "amount": 5000, "amount_paid": 5000, "status": "PAID"},
                {"plate": "GJ18MH0099", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ03JK6671", "amount": 1500, "amount_paid": 1500, "status": "PAID"},
                {"plate": "GJ06RT2210", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "MH12QE3344", "amount": 2000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ12PL8080", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "GJ09WD5543", "amount": 2000, "amount_paid": 1000, "status": "PARTIAL"},
                {"plate": "RJ14TU7071", "amount": 5000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ01AB1234", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ05XY4321", "amount": 1500, "amount_paid": 1500, "status": "PAID"},
                {"plate": "GJ03JK6671", "amount": 1000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ07BM4412", "amount": 3000, "amount_paid": 3000, "status": "PAID"},
                {"plate": "GJ06RT2210", "amount": 500, "amount_paid": 500, "status": "PAID"},
            ],
        ),
        _build_officer(
            officer_id="OFF-03318",
            name="SI Priya Sharma",
            photo_url="/officers/priya-sharma.jpg",
            police_id="GJ-03318",
            department="Gujarat Police · Traffic Control",
            designation="Junior Officer",
            plates=[
                "GJ01CD2345", "GJ05LM7788", "GJ27AK9021",
                "MH04TR6610", "GJ11GH3302", "GJ01ZX5570",
            ],
            challans=[
                {"plate": "GJ01CD2345", "amount": 3000, "amount_paid": 3000, "status": "PAID"},
                {"plate": "GJ05LM7788", "amount": 2500, "amount_paid": 2500, "status": "PAID"},
                {"plate": "GJ27AK9021", "amount": 2000, "amount_paid": 2000, "status": "PAID"},
                {"plate": "MH04TR6610", "amount": 2500, "amount_paid": 1000, "status": "PARTIAL"},
                {"plate": "GJ11GH3302", "amount": 2000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ01ZX5570", "amount": 1500, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ05LM7788", "amount": 1500, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ01CD2345", "amount": 1500, "amount_paid": 0, "status": "PENDING"},
            ],
        ),
        _build_officer(
            officer_id="OFF-05342",
            name="SI Rahul Patel",
            photo_url="/officers/rahul-patel.jpg",
            police_id="GJ-05342",
            department="Gujarat Police · Traffic Control",
            designation="Junior Officer",
            plates=[
                "GJ02MN5588", "GJ21CV1190", "MH14KD7788", "GJ08HP3160",
                "GJ16FE2231", "RJ27PQ4410", "GJ03YT8891",
            ],
            challans=[
                {"plate": "GJ02MN5588", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ21CV1190", "amount": 500, "amount_paid": 0, "status": "PENDING"},
                {"plate": "MH14KD7788", "amount": 2000, "amount_paid": 2000, "status": "PAID"},
                {"plate": "GJ08HP3160", "amount": 1500, "amount_paid": 750, "status": "PARTIAL"},
                {"plate": "GJ16FE2231", "amount": 3000, "amount_paid": 3000, "status": "PAID"},
                {"plate": "RJ27PQ4410", "amount": 5000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ03YT8891", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ16FE2231", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "GJ02MN5588", "amount": 2000, "amount_paid": 2000, "status": "PAID"},
            ],
        ),
        _build_officer(
            officer_id="OFF-06077",
            name="ASI Amit Kumar",
            photo_url="/officers/amit-kumar.jpg",
            police_id="GJ-06077",
            department="Gujarat Police · Traffic Control",
            designation="Junior Officer",
            plates=["GJ06KL4412", "GJ18BN7720", "MH02WE9034", "GJ09OP1178", "GJ01QA6655"],
            challans=[
                {"plate": "GJ06KL4412", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "GJ18BN7720", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "MH02WE9034", "amount": 2000, "amount_paid": 1000, "status": "PARTIAL"},
                {"plate": "GJ09OP1178", "amount": 1500, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ01QA6655", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ06KL4412", "amount": 2000, "amount_paid": 2000, "status": "PAID"},
            ],
        ),
        _build_officer(
            officer_id="OFF-06215",
            name="ASI Neha Joshi",
            photo_url="/officers/neha-joshi.jpg",
            police_id="GJ-06215",
            department="Gujarat Police · Traffic Control",
            designation="Junior Officer",
            plates=[
                "GJ05RS9910", "GJ12TY2288", "GJ03UI7734",
                "RJ14ER3306", "GJ07DF5521", "GJ01HJ0087",
            ],
            challans=[
                {"plate": "GJ05RS9910", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ12TY2288", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "GJ03UI7734", "amount": 5000, "amount_paid": 5000, "status": "PAID"},
                {"plate": "RJ14ER3306", "amount": 2000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "GJ07DF5521", "amount": 1500, "amount_paid": 500, "status": "PARTIAL"},
                {"plate": "GJ01HJ0087", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ12TY2288", "amount": 1000, "amount_paid": 0, "status": "PENDING"},
            ],
        ),
        _build_officer(
            officer_id="OFF-07430",
            name="HC Vikram Singh",
            photo_url="/officers/vikram-singh.jpg",
            police_id="GJ-07430",
            department="Gujarat Police · Traffic Control",
            designation="Police Officer",
            plates=["GJ01VB3345", "GJ08NM6612", "GJ15CX8890", "MH12LK2207"],
            challans=[
                {"plate": "GJ01VB3345", "amount": 500, "amount_paid": 500, "status": "PAID"},
                {"plate": "GJ08NM6612", "amount": 1000, "amount_paid": 1000, "status": "PAID"},
                {"plate": "GJ15CX8890", "amount": 2000, "amount_paid": 0, "status": "PENDING"},
                {"plate": "MH12LK2207", "amount": 1500, "amount_paid": 1500, "status": "PAID"},
                {"plate": "GJ01VB3345", "amount": 1000, "amount_paid": 500, "status": "PARTIAL"},
            ],
        ),
    ]


_OFFICERS: Optional[List[dict]] = None
_BY_ID: Optional[Dict[str, dict]] = None


def _ensure_loaded() -> List[dict]:
    global _OFFICERS, _BY_ID
    if _OFFICERS is None:
        _OFFICERS = _roster()
        _BY_ID = {o["officer_id"]: o for o in _OFFICERS}
    return _OFFICERS


def list_officers() -> List[dict]:
    return list(_ensure_loaded())


def get_current_officer() -> dict:
    _ensure_loaded()
    assert _BY_ID is not None
    return _BY_ID[CURRENT_OFFICER_ID]


def get_officer(officer_id: str) -> Optional[dict]:
    _ensure_loaded()
    assert _BY_ID is not None
    return _BY_ID.get((officer_id or "").strip().upper())
