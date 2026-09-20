"""
TRINETRA AI — 60-Second Real-Time Alert & Notification Scheduler.
Broadcasts a new vehicle alert every 60 seconds.
Guarantees that every notification features:
  1. A DIFFERENT vehicle (unique plate number, vehicle class, and category).
  2. A DIFFERENT camera location across Gujarat on the map.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from ..database.database import SessionLocal
from ..database.models import Camera, Watchlist, VehicleEvent, Alert
from ..services.ws_manager import ws_manager
from ..utils.timestamps import iso_utc
from ..core.logging_config import logger

ALERT_ROTATION_ITEMS: List[Dict[str, Any]] = [
    {
        "plate": "GJ01AB1234",
        "vehicle_class": "car",
        "vehicle_model": "White Toyota Fortuner",
        "camera_id": "CAM04",
        "camera_name": "CAM04",
        "location": "Paldi Circle, Ahmedabad",
        "latitude": 23.0126,
        "longitude": 72.5647,
        "category": "STOLEN VEHICLE",
        "severity": "CRITICAL",
        "reason": "Reported stolen from Paldi residential parking. FIR filed.",
    },
    {
        "plate": "GJ05XY4321",
        "vehicle_class": "suv",
        "vehicle_model": "Black Mahindra Scorpio",
        "camera_id": "CAM17",
        "camera_name": "CAM17",
        "location": "Rajkot Bus Port CCTV, Rajkot",
        "latitude": 22.2908,
        "longitude": 70.7990,
        "category": "WANTED SUSPECT",
        "severity": "CRITICAL",
        "reason": "Linked to armed robbery investigation. Immediate intercept.",
    },
    {
        "plate": "GJ27CJ7788",
        "vehicle_class": "van",
        "vehicle_model": "Silver Maruti Omni",
        "camera_id": "CAM08",
        "camera_name": "CAM08",
        "location": "Majewadi Gate, Junagadh",
        "latitude": 21.5300,
        "longitude": 70.4620,
        "category": "AMBER ALERT",
        "severity": "CRITICAL",
        "reason": "Suspected vehicle in active abduction investigation.",
    },
    {
        "plate": "GJ12PQ8899",
        "vehicle_class": "car",
        "vehicle_model": "Red Hyundai Creta",
        "camera_id": "CAM30",
        "camera_name": "CAM30",
        "location": "Gandhidham Rambaugh p2, Kutch",
        "latitude": 23.0759,
        "longitude": 70.1310,
        "category": "SUSPICIOUS ACTIVITY",
        "severity": "HIGH",
        "reason": "Suspicious perimeter movement near cargo port corridor.",
    },
    {
        "plate": "GJ06KL2211",
        "vehicle_class": "motorcycle",
        "vehicle_model": "Black Royal Enfield Classic",
        "camera_id": "CAM12",
        "camera_name": "CAM12",
        "location": "Tri Mandir Adalaj Tollnaka, Gandhinagar",
        "latitude": 23.1662,
        "longitude": 72.5807,
        "category": "PERSON OF INTEREST",
        "severity": "HIGH",
        "reason": "Special Branch surveillance request — logged movement.",
    },
    {
        "plate": "GJ03DT5566",
        "vehicle_class": "truck",
        "vehicle_model": "Tata 1109 Heavy Truck",
        "camera_id": "CAM21",
        "camera_name": "CAM21",
        "location": "Patan Dethali Char Rasta, Patan",
        "latitude": 23.9167,
        "longitude": 72.3500,
        "category": "COMMERCIAL VIOLATION",
        "severity": "MEDIUM",
        "reason": "Goods carrier operating with lapsed fitness certificate.",
    },
    {
        "plate": "GJ19BX9021",
        "vehicle_class": "car",
        "vehicle_model": "Grey Honda City",
        "camera_id": "CAM19",
        "camera_name": "CAM19",
        "location": "Khaparia Gram Panchayat, Navsari",
        "latitude": 20.8136,
        "longitude": 72.9900,
        "category": "STOLEN VEHICLE",
        "severity": "HIGH",
        "reason": "Stolen vehicle lookout circular dispatched statewide.",
    },
    {
        "plate": "GJ07MK4412",
        "vehicle_class": "suv",
        "vehicle_model": "Blue Tata Harrier",
        "camera_id": "CAM07",
        "camera_name": "CAM07",
        "location": "Hero Showroom, Gir Somnath",
        "latitude": 20.9097,
        "longitude": 70.3666,
        "category": "WANTED SUSPECT",
        "severity": "CRITICAL",
        "reason": "Non-bailable warrant suspect vehicle flagged on coastal road.",
    },
    {
        "plate": "GJ21RS3344",
        "vehicle_class": "auto_rickshaw",
        "vehicle_model": "Bajaj Compact Auto Rickshaw",
        "camera_id": "CAM01",
        "camera_name": "CAM01",
        "location": "Chiman bhai Bridge, Ahmedabad",
        "latitude": 23.0730,
        "longitude": 72.5920,
        "category": "BLACKLISTED",
        "severity": "MEDIUM",
        "reason": "Unauthorised commercial operation inside restricted traffic zone.",
    },
    {
        "plate": "GJ16TU9090",
        "vehicle_class": "car",
        "vehicle_model": "White Maruti Swift",
        "camera_id": "CAM24",
        "camera_name": "CAM24",
        "location": "Dehgam Circle, Gandhinagar",
        "latitude": 23.1691,
        "longitude": 72.8066,
        "category": "TRAFFIC OFFENDER",
        "severity": "HIGH",
        "reason": "Reckless driving & repeated toll barrier evasion.",
    },
    {
        "plate": "GJ09VW1212",
        "vehicle_class": "car",
        "vehicle_model": "Dark Grey Kia Seltos",
        "camera_id": "CAM11",
        "camera_name": "CAM11",
        "location": "Dolatpara, Junagadh",
        "latitude": 21.5255,
        "longitude": 70.4560,
        "category": "UNREGISTERED VEHICLE",
        "severity": "HIGH",
        "reason": "Tampered registration plate format detected by ANPR scanner.",
    },
    {
        "plate": "GJ18MH0099",
        "vehicle_class": "bus",
        "vehicle_model": "Volvo Multi-axle Intercity Bus",
        "camera_id": "CAM18",
        "camera_name": "CAM18",
        "location": "Rajkot CCTV Junction, Rajkot",
        "latitude": 22.3039,
        "longitude": 70.8022,
        "category": "SPEED VIOLATION",
        "severity": "MEDIUM",
        "reason": "Urban highway speed limit breach: clocked at 98 km/h.",
    },
    {
        "plate": "GJ04EF5522",
        "vehicle_class": "motorcycle",
        "vehicle_model": "Hero Splendor Plus",
        "camera_id": "CAM05",
        "camera_name": "CAM05",
        "location": "Visat Teen Rasta, Ahmedabad",
        "latitude": 23.0870,
        "longitude": 72.5930,
        "category": "STOLEN VEHICLE",
        "severity": "CRITICAL",
        "reason": "Motorcycle stolen from Sabarmati area. Immediate patrol alert.",
    },
    {
        "plate": "GJ14AK8833",
        "vehicle_class": "car",
        "vehicle_model": "Maruti Ertiga Silver",
        "camera_id": "CAM27",
        "camera_name": "CAM27",
        "location": "Bilimora Town, Navsari",
        "latitude": 20.7508,
        "longitude": 72.9510,
        "category": "AMBER ALERT",
        "severity": "CRITICAL",
        "reason": "State child protection advisory; suspect transport vehicle.",
    },
    {
        "plate": "GJ10DR7711",
        "vehicle_class": "suv",
        "vehicle_model": "Mahindra Thar Black 4x4",
        "camera_id": "CAM06",
        "camera_name": "CAM06",
        "location": "Timbavadi Gate, Junagadh",
        "latitude": 21.5236,
        "longitude": 70.4550,
        "category": "WANTED SUSPECT",
        "severity": "CRITICAL",
        "reason": "Armed suspect vehicle reported heading towards bypass.",
    },
    {
        "plate": "GJ02CR3399",
        "vehicle_class": "car",
        "vehicle_model": "Skoda Slavia Red",
        "camera_id": "CAM22",
        "camera_name": "CAM22",
        "location": "BK Mervada Tran Rasta, Patan",
        "latitude": 23.7833,
        "longitude": 72.1167,
        "category": "HIT AND RUN",
        "severity": "CRITICAL",
        "reason": "Vehicle involved in major hit-and-run accident on SH-14.",
    },
    {
        "plate": "GJ11NT6644",
        "vehicle_class": "truck",
        "vehicle_model": "Ashok Leyland 1616 Tipper",
        "camera_id": "CAM09",
        "camera_name": "CAM09",
        "location": "New Bypass Circle 2, Junagadh",
        "latitude": 21.5355,
        "longitude": 70.4780,
        "category": "ILLEGAL TRANSPORT",
        "severity": "HIGH",
        "reason": "Overloaded mineral transport bypassing statutory weighbridge.",
    },
    {
        "plate": "GJ23QA7788",
        "vehicle_class": "car",
        "vehicle_model": "Volkswagen Virtus Blue",
        "camera_id": "CAM02",
        "camera_name": "CAM02",
        "location": "Janpath Junction, Ahmedabad",
        "latitude": 23.0225,
        "longitude": 72.5625,
        "category": "SUSPICIOUS ACTIVITY",
        "severity": "HIGH",
        "reason": "Multiple erratic movements logged across sensitive city sectors.",
    },
    {
        "plate": "GJ17PZ2211",
        "vehicle_class": "motorcycle",
        "vehicle_model": "Yamaha FZ Dark Knight",
        "camera_id": "CAM25",
        "camera_name": "CAM25",
        "location": "Dhanori, Navsari",
        "latitude": 20.7880,
        "longitude": 72.9770,
        "category": "STOLEN VEHICLE",
        "severity": "HIGH",
        "reason": "Two-wheeler theft FIR registered at Gandevi Police Station.",
    },
    {
        "plate": "GJ25LK8800",
        "vehicle_class": "suv",
        "vehicle_model": "MG Hector White",
        "camera_id": "CAM15",
        "camera_name": "CAM15",
        "location": "Suvidha Park, Ahmedabad",
        "latitude": 23.0389,
        "longitude": 72.6608,
        "category": "WANTED SUSPECT",
        "severity": "CRITICAL",
        "reason": "Suspect vehicle tracked moving towards Sardar Patel Ring Road.",
    },
]

_scheduler_running = False
_rotation_index = 0
_scheduler_task: asyncio.Task | None = None


async def run_alert_tick() -> Dict[str, Any]:
    """
    Executes one alert tick:
      - Picks next item from ROTATION_ITEMS (ensuring different vehicle & location)
      - Creates VehicleEvent & Alert in the DB
      - Broadcasts ALERT_CREATED and EVENT over SSE & WebSocket
    """
    global _rotation_index
    item = ALERT_ROTATION_ITEMS[_rotation_index % len(ALERT_ROTATION_ITEMS)]
    _rotation_index += 1

    db: Session = SessionLocal()
    try:
        # Resolve camera coordinates from DB if present, else use item defaults
        cam = db.query(Camera).filter(Camera.camera_id == item["camera_id"].upper()).first()
        lat = cam.latitude if (cam and cam.latitude) else item["latitude"]
        lng = cam.longitude if (cam and cam.longitude) else item["longitude"]
        cam_id = cam.camera_id if cam else item["camera_id"].upper()
        cam_name = cam.name if cam else item["camera_name"]
        location = cam.location if cam else item["location"]

        # Ensure watchlist record exists so the plate is recognized as a watchlist hit
        wl = db.query(Watchlist).filter(Watchlist.plate_number == item["plate"]).first()
        if not wl:
            wl = Watchlist(
                plate_number=item["plate"],
                category=item["category"].upper(),
                description=item["reason"],
                active=True,
            )
            db.add(wl)
            db.commit()
            db.refresh(wl)

        now = datetime.now(timezone.utc)

        # Create VehicleEvent
        event = VehicleEvent(
            camera_id=cam_id,
            vehicle_track_id=100 + (_rotation_index % 899),
            plate_raw=item["plate"],
            plate_number=item["plate"],
            plate_confidence=0.96,
            vehicle_class=item["vehicle_class"].lower(),
            event_time=now,
            latitude=lat,
            longitude=lng,
            watchlist_match=True,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        # Create Alert
        alert = Alert(
            event_id=event.id,
            watchlist_id=wl.id,
            confidence=96.0,
            camera_id=cam_id,
            track_id=event.vehicle_track_id,
            plate_number=item["plate"],
            alert_type="WATCHLIST_MATCH",
            severity=item["severity"],
            message=(
                f"WATCHLIST HIT: Plate {item['plate']} ({item['vehicle_model']}) detected on "
                f"{cam_id} ({location}). Category: {item['category']}."
            ),
            status="NEW",
            timestamp=now,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        ws_payload = {
            "event_id": event.id,
            "id": alert.id,
            "alert_id": alert.id,
            "alert_ref": f"AL-{alert.id}",
            "camera_id": cam_id,
            "camera_name": cam_name,
            "location": location,
            "plate": item["plate"],
            "plate_number": item["plate"],
            "plate_raw": item["plate"],
            "vehicle_class": item["vehicle_class"].upper(),
            "confidence": 96.0,
            "plate_confidence": 0.96,
            "event_time": iso_utc(now),
            "timestamp": iso_utc(now),
            "latitude": lat,
            "longitude": lng,
            "watchlist_match": True,
            "alert_type": "WATCHLIST_MATCH",
            "category": item["category"],
            "severity": item["severity"],
            "message": alert.message,
            "status": "NEW",
        }

        # Fan-out to all SSE & WebSocket subscribers
        await ws_manager.broadcast("ALERT_CREATED", ws_payload)
        logger.info(
            f"[60s ALERT] Broadcasted alert: {item['plate']} ({item['vehicle_model']}) "
            f"on {cam_id} - {location} (lat: {lat}, lng: {lng})"
        )
        return ws_payload
    except Exception as exc:
        db.rollback()
        logger.error(f"[60s ALERT] Failed to emit alert tick: {exc}")
        return {"error": str(exc)}
    finally:
        db.close()


async def start_alert_scheduler(interval_seconds: int = 60) -> None:
    """Runs a periodic loop that emits a new alert every `interval_seconds` (default: 60s)."""
    global _scheduler_running
    _scheduler_running = True
    logger.info(f"🚀 TRINETRA AI Alert Scheduler started — new alert every {interval_seconds}s")

    try:
        while _scheduler_running:
            await asyncio.sleep(interval_seconds)
            if not _scheduler_running:
                break
            await run_alert_tick()
    except asyncio.CancelledError:
        logger.info("🛑 TRINETRA AI Alert Scheduler cancelled.")
    except Exception as exc:
        logger.error(f"⚠️ TRINETRA AI Alert Scheduler encountered an error: {exc}")
    finally:
        _scheduler_running = False


def stop_alert_scheduler() -> None:
    """Stops the running alert scheduler."""
    global _scheduler_running, _scheduler_task
    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    logger.info("🛑 TRINETRA AI Alert Scheduler stopped.")
