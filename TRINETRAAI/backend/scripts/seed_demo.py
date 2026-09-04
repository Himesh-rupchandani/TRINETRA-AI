"""
TRINETRA AI Demo Seed Script
============================
Seeds the database with:
  - 30 realistic CCTV cameras across Ahmedabad/Gujarat
  - 10 watchlist entries (including GJ01AB1234 as STOLEN / CRITICAL)
  - 20+ vehicle events including the primary demo journey:
      GJ01AB1234: CAM04 â†’ CAM08 â†’ CAM12 â†’ CAM17
  - 5 realistic alerts

Usage:
    cd backend
    python -m scripts.seed_demo
"""
import sys
import io
from pathlib import Path

# Force UTF-8 on Windows stdout/stderr to prevent charmap encoding errors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend root is in sys.path when running as script
backend_root = Path(__file__).resolve().parents[1]
project_root = Path(__file__).resolve().parents[2]
for p in [str(project_root), str(backend_root)]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from datetime import datetime, timezone, timedelta
from app.database.database import SessionLocal, engine
from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert

# Create tables if not yet created
Base.metadata.create_all(bind=engine)


def seed_cameras(db):
    if db.query(Camera).count() > 0:
        print("  â†’ Cameras already seeded, skipping.")
        return

    cameras = [
        Camera(camera_id="CAM01", name="Central Expressway Toll Plaza",
               stream_url="https://cctv.corp8.cloud/cam01/index.m3u8", stream_type="hls",
               latitude=23.0225, longitude=72.5714, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM02", name="Metro Station Interchange Cam",
               stream_url="https://cctv.corp8.cloud/cam02/index.m3u8", stream_type="hls",
               latitude=23.0410, longitude=72.5620, status="OFFLINE", department="Metro Security"),
        Camera(camera_id="CAM03", name="SG Highway Ring Road West",
               stream_url="https://cctv.corp8.cloud/cam03/index.m3u8", stream_type="hls",
               latitude=23.0150, longitude=72.5110, status="OFFLINE", department="Highway Patrol"),
        Camera(camera_id="CAM04", name="North Gate Junction",
               stream_url="https://cctv.corp8.cloud/cam04/index.m3u8", stream_type="hls",
               latitude=23.0338, longitude=72.5850, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM05", name="Satellite Road Junction",
               stream_url="https://cctv.corp8.cloud/cam05/index.m3u8", stream_type="hls",
               latitude=23.0295, longitude=72.5360, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM06", name="Vastrapur Lake Entry",
               stream_url="https://cctv.corp8.cloud/cam06/index.m3u8", stream_type="hls",
               latitude=23.0412, longitude=72.5264, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM07", name="Prahladnagar Square",
               stream_url="https://cctv.corp8.cloud/cam07/index.m3u8", stream_type="hls",
               latitude=23.0218, longitude=72.5124, status="OFFLINE", department="Municipal Corporation"),
        Camera(camera_id="CAM08", name="ISCON Crossroads CCTV",
               stream_url="https://cctv.corp8.cloud/cam08/index.m3u8", stream_type="hls",
               latitude=23.0295, longitude=72.5054, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM09", name="Bodakdev Police Chowki Cam",
               stream_url="https://cctv.corp8.cloud/cam09/index.m3u8", stream_type="hls",
               latitude=23.0450, longitude=72.5169, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM10", name="S G Highway Overbridge Cam",
               stream_url="https://cctv.corp8.cloud/cam10/index.m3u8", stream_type="hls",
               latitude=23.0362, longitude=72.5052, status="OFFLINE", department="Highway Patrol"),
        Camera(camera_id="CAM11", name="Maninagar Station Gate",
               stream_url="https://cctv.corp8.cloud/cam11/index.m3u8", stream_type="hls",
               latitude=22.9915, longitude=72.6085, status="OFFLINE", department="Municipal Corporation"),
        Camera(camera_id="CAM12", name="Naranpura Octroi Post",
               stream_url="https://cctv.corp8.cloud/cam12/index.m3u8", stream_type="hls",
               latitude=23.0622, longitude=72.5659, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM13", name="Gota Crossroad Junction",
               stream_url="https://cctv.corp8.cloud/cam13/index.m3u8", stream_type="hls",
               latitude=23.1006, longitude=72.5789, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM14", name="Chandkheda Highway Entry",
               stream_url="https://cctv.corp8.cloud/cam14/index.m3u8", stream_type="hls",
               latitude=23.1168, longitude=72.5918, status="OFFLINE", department="Metro Security"),
        Camera(camera_id="CAM15", name="Airport Road Junction",
               stream_url="https://cctv.corp8.cloud/cam15/index.m3u8", stream_type="hls",
               latitude=23.0728, longitude=72.6268, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM16", name="Kalupur Railway Station Cam",
               stream_url="https://cctv.corp8.cloud/cam16/index.m3u8", stream_type="hls",
               latitude=23.0289, longitude=72.6120, status="OFFLINE", department="Highway Patrol"),
        Camera(camera_id="CAM17", name="Bapunagar Industrial Zone",
               stream_url="https://cctv.corp8.cloud/cam17/index.m3u8", stream_type="hls",
               latitude=23.0487, longitude=72.6303, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM18", name="Odhav GIDC Entry Gate",
               stream_url="https://cctv.corp8.cloud/cam18/index.m3u8", stream_type="hls",
               latitude=23.0175, longitude=72.6726, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM19", name="Vastral Highway Bypass",
               stream_url="https://cctv.corp8.cloud/cam19/index.m3u8", stream_type="hls",
               latitude=23.0019, longitude=72.6834, status="OFFLINE", department="Municipal Corporation"),
        Camera(camera_id="CAM20", name="Naroda Main Gate Cam",
               stream_url="https://cctv.corp8.cloud/cam20/index.m3u8", stream_type="hls",
               latitude=23.0703, longitude=72.6548, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM21", name="Nikol Junction",
               stream_url="https://cctv.corp8.cloud/cam21/index.m3u8", stream_type="hls",
               latitude=23.0469, longitude=72.6620, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM22", name="Thaltej Signal Cam",
               stream_url="https://cctv.corp8.cloud/cam22/index.m3u8", stream_type="hls",
               latitude=23.0591, longitude=72.5091, status="OFFLINE", department="Highway Patrol"),
        Camera(camera_id="CAM23", name="Science City Road Junction",
               stream_url="https://cctv.corp8.cloud/cam23/index.m3u8", stream_type="hls",
               latitude=23.0752, longitude=72.5311, status="OFFLINE", department="Metro Security"),
        Camera(camera_id="CAM24", name="Sola Road Crossroads",
               stream_url="https://cctv.corp8.cloud/cam24/index.m3u8", stream_type="hls",
               latitude=23.0776, longitude=72.5542, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM25", name="Nava Vadaj Crossroad",
               stream_url="https://cctv.corp8.cloud/cam25/index.m3u8", stream_type="hls",
               latitude=23.0540, longitude=72.5734, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM26", name="Paldi Bridge Camera",
               stream_url="https://cctv.corp8.cloud/cam26/index.m3u8", stream_type="hls",
               latitude=23.0098, longitude=72.5798, status="OFFLINE", department="Municipal Corporation"),
        Camera(camera_id="CAM27", name="Akhbarnagar Junction",
               stream_url="https://cctv.corp8.cloud/cam27/index.m3u8", stream_type="hls",
               latitude=23.0659, longitude=72.5813, status="OFFLINE", department="Police"),
        Camera(camera_id="CAM28", name="Bopal Crossroads East",
               stream_url="https://cctv.corp8.cloud/cam28/index.m3u8", stream_type="hls",
               latitude=23.0012, longitude=72.4713, status="OFFLINE", department="Highway Patrol"),
        Camera(camera_id="CAM29", name="Manipur Highway Camera",
               stream_url="https://cctv.corp8.cloud/cam29/index.m3u8", stream_type="hls",
               latitude=23.0881, longitude=72.4951, status="OFFLINE", department="Traffic Police"),
        Camera(camera_id="CAM30", name="Bavla Highway Entry Cam",
               stream_url="https://cctv.corp8.cloud/cam30/index.m3u8", stream_type="hls",
               latitude=22.9614, longitude=72.3729, status="OFFLINE", department="Police"),
    ]
    db.add_all(cameras)
    db.commit()
    print(f"  → Seeded {len(cameras)} cameras.")


def seed_watchlist(db):
    existing_plates = {w.plate_number for w in db.query(Watchlist).all()}
    new_entries = [
        Watchlist(plate_number="GJ01AB1234", category="stolen vehicle",
                  description="Silver Sedan - Reported stolen FIR #4812", active=True),
        Watchlist(plate_number="MH02CD5678", category="wanted vehicle",
                  description="Black SUV - Suspect in inter-state logistics theft", active=True),
        Watchlist(plate_number="DL08EF9012", category="suspicious vehicle",
                  description="White Hatchback - Multiple toll avoidance flags", active=True),
        Watchlist(plate_number="RJ14GH3456", category="stolen vehicle",
                  description="Red Pickup Truck - FIR #7021 Jaipur", active=True),
        Watchlist(plate_number="KA05XY9999", category="wanted vehicle",
                  description="Grey Sedan - Wanted for hit-and-run Bengaluru", active=True),
        Watchlist(plate_number="UP32MN7890", category="suspicious vehicle",
                  description="Repeated sightings near sensitive areas", active=True),
        Watchlist(plate_number="TN09PQ2345", category="stolen vehicle",
                  description="Blue Hatchback - Missing since March 2026", active=True),
        Watchlist(plate_number="MP04RS6789", category="wanted vehicle",
                  description="Narcotics surveillance vehicle", active=True),
        Watchlist(plate_number="GJ06UV1010", category="suspicious vehicle",
                  description="Flagged during election monitoring", active=True),
        Watchlist(plate_number="HR26WX5050", category="stolen vehicle",
                  description="Commercial vehicle chassis mismatch", active=True),
    ]
    to_add = [e for e in new_entries if e.plate_number not in existing_plates]
    if not to_add:
        print("  → Watchlist already seeded, skipping.")
        return
    db.add_all(to_add)
    db.commit()
    print(f"  → Seeded {len(to_add)} new watchlist entries.")


def seed_events(db):
    if db.query(VehicleEvent).count() > 0:
        print("  → Vehicle events already seeded, skipping.")
        return

    base_time = datetime(2026, 9, 2, 8, 0, 0, tzinfo=timezone.utc)

    events = [
        # === PRIMARY DEMO JOURNEY: GJ01AB1234 (STOLEN) across 4 cameras ===
        VehicleEvent(camera_id="CAM04", vehicle_track_id=101, plate_raw="GJ 01 AB-1234",
                     plate_number="GJ01AB1234", plate_confidence=0.97, vehicle_class="car",
                     event_time=base_time, latitude=23.0338, longitude=72.5850,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM08", vehicle_track_id=101, plate_raw="GJ 01 AB 1234",
                     plate_number="GJ01AB1234", plate_confidence=0.94, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=8), latitude=23.0295, longitude=72.5054,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM12", vehicle_track_id=101, plate_raw="GJ01AB1234",
                     plate_number="GJ01AB1234", plate_confidence=0.99, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=19), latitude=23.0622, longitude=72.5659,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM17", vehicle_track_id=101, plate_raw="GJ-01-AB-1234",
                     plate_number="GJ01AB1234", plate_confidence=0.91, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=31), latitude=23.0487, longitude=72.6303,
                     watchlist_match=True),

        # === MH02CD5678 Journey (WANTED) ===
        VehicleEvent(camera_id="CAM01", vehicle_track_id=202, plate_raw="MH 02 CD-5678",
                     plate_number="MH02CD5678", plate_confidence=0.88, vehicle_class="suv",
                     event_time=base_time + timedelta(minutes=2), latitude=23.0225, longitude=72.5714,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM05", vehicle_track_id=202, plate_raw="MH02CD5678",
                     plate_number="MH02CD5678", plate_confidence=0.92, vehicle_class="suv",
                     event_time=base_time + timedelta(minutes=14), latitude=23.0295, longitude=72.5360,
                     watchlist_match=True),

        # === Normal (non-watchlist) vehicles ===
        VehicleEvent(camera_id="CAM01", vehicle_track_id=303, plate_raw="GJ 01 ZZ 0001",
                     plate_number="GJ01ZZ0001", plate_confidence=0.82, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=1), latitude=23.0225, longitude=72.5714,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM02", vehicle_track_id=304, plate_raw="GJ 18 BK 4521",
                     plate_number="GJ18BK4521", plate_confidence=0.79, vehicle_class="motorcycle",
                     event_time=base_time + timedelta(minutes=3), latitude=23.0410, longitude=72.5620,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM03", vehicle_track_id=305, plate_raw="GJ 06 SS 1111",
                     plate_number="GJ06SS1111", plate_confidence=0.85, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=4), latitude=23.0150, longitude=72.5110,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM06", vehicle_track_id=306, plate_raw="GJ 01 QQ 9988",
                     plate_number="GJ01QQ9988", plate_confidence=0.91, vehicle_class="truck",
                     event_time=base_time + timedelta(minutes=6), latitude=23.0412, longitude=72.5264,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM07", vehicle_track_id=307, plate_raw="MH 12 AB 3344",
                     plate_number="MH12AB3344", plate_confidence=0.88, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=7), latitude=23.0218, longitude=72.5124,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM09", vehicle_track_id=308, plate_raw="DL 7C XY 5522",
                     plate_number="DL7CXY5522", plate_confidence=0.76, vehicle_class="bus",
                     event_time=base_time + timedelta(minutes=9), latitude=23.0450, longitude=72.5169,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM10", vehicle_track_id=309, plate_raw="GJ 01 XX 2233",
                     plate_number="GJ01XX2233", plate_confidence=0.84, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=10), latitude=23.0362, longitude=72.5052,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM11", vehicle_track_id=310, plate_raw="RJ 14 CK 6677",
                     plate_number="RJ14CK6677", plate_confidence=0.80, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=11), latitude=22.9915, longitude=72.6085,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM13", vehicle_track_id=311, plate_raw="GJ 01 NN 8899",
                     plate_number="GJ01NN8899", plate_confidence=0.93, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=12), latitude=23.1006, longitude=72.5789,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM14", vehicle_track_id=312, plate_raw="UP 32 GH 1122",
                     plate_number="UP32GH1122", plate_confidence=0.87, vehicle_class="truck",
                     event_time=base_time + timedelta(minutes=13), latitude=23.1168, longitude=72.5918,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM15", vehicle_track_id=313, plate_raw="GJ 07 KL 3344",
                     plate_number="GJ07KL3344", plate_confidence=0.81, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=15), latitude=23.0728, longitude=72.6268,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM16", vehicle_track_id=314, plate_raw="GJ 01 MM 5566",
                     plate_number="GJ01MM5566", plate_confidence=0.78, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=16), latitude=23.0289, longitude=72.6120,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM18", vehicle_track_id=315, plate_raw="GJ 06 TT 7890",
                     plate_number="GJ06TT7890", plate_confidence=0.90, vehicle_class="motorcycle",
                     event_time=base_time + timedelta(minutes=18), latitude=23.0175, longitude=72.6726,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM20", vehicle_track_id=316, plate_raw="GJ 01 VV 4455",
                     plate_number="GJ01VV4455", plate_confidence=0.86, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=20), latitude=23.0703, longitude=72.6548,
                     watchlist_match=False),
        VehicleEvent(camera_id="CAM22", vehicle_track_id=317, plate_raw="GJ 05 WW 6688",
                     plate_number="GJ05WW6688", plate_confidence=0.83, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=22), latitude=23.0591, longitude=72.5091,
                     watchlist_match=False),
        # === DL08EF9012 (Suspicious) ===
        VehicleEvent(camera_id="CAM25", vehicle_track_id=401, plate_raw="DL 08 EF 9012",
                     plate_number="DL08EF9012", plate_confidence=0.87, vehicle_class="car",
                     event_time=base_time + timedelta(minutes=25), latitude=23.0540, longitude=72.5734,
                     watchlist_match=True),
    ]
    db.add_all(events)
    db.commit()
    print(f"  â†’ Seeded {len(events)} vehicle events.")


def seed_alerts(db):
    if db.query(Alert).count() > 0:
        print("  â†’ Alerts already seeded, skipping.")
        return

    base_time = datetime(2026, 9, 2, 8, 0, 0, tzinfo=timezone.utc)

    alerts = [
        Alert(camera_id="CAM04", plate_number="GJ01AB1234", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="NEW",
              message="WATCHLIST HIT: GJ01AB1234 on CAM04. Category: stolen vehicle. FIR #4812.",
              timestamp=base_time),
        Alert(camera_id="CAM08", plate_number="GJ01AB1234", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="ACKNOWLEDGED",
              message="WATCHLIST HIT: GJ01AB1234 on CAM08. Category: stolen vehicle. FIR #4812.",
              timestamp=base_time + timedelta(minutes=8),
              acknowledged_at=base_time + timedelta(minutes=9),
              acknowledged_by="operator_raj"),
        Alert(camera_id="CAM01", plate_number="MH02CD5678", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="NEW",
              message="WATCHLIST HIT: MH02CD5678 on CAM01. Category: wanted vehicle. Inter-state theft.",
              timestamp=base_time + timedelta(minutes=2)),
        Alert(camera_id="CAM25", plate_number="DL08EF9012", alert_type="WATCHLIST_MATCH",
              severity="HIGH", status="RESOLVED",
              message="WATCHLIST HIT: DL08EF9012 on CAM25. Category: suspicious vehicle.",
              timestamp=base_time + timedelta(minutes=25),
              resolved_at=base_time + timedelta(minutes=40),
              resolved_by="supervisor_meera"),
        Alert(camera_id="CAM12", plate_number="GJ01AB1234", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="NEW",
              message="WATCHLIST HIT: GJ01AB1234 on CAM12. Category: stolen vehicle. FIR #4812.",
              timestamp=base_time + timedelta(minutes=19)),
    ]
    db.add_all(alerts)
    db.commit()
    print(f"  â†’ Seeded {len(alerts)} alerts.")


def main():
    print("\n[TRINETRA AI] Running Demo Seed Script")
    print("=" * 50)
    db = SessionLocal()
    try:
        print("\n[1/4] Seeding cameras...")
        seed_cameras(db)

        print("\n[2/4] Seeding watchlist...")
        seed_watchlist(db)

        print("\n[3/4] Seeding vehicle events...")
        seed_events(db)

        print("\n[4/4] Seeding alerts...")
        seed_alerts(db)

        print("\n[OK] Demo seed complete!")
        print("=" * 50)
        print("Demo plate: GJ01AB1234 -> CAM04 -> CAM08 -> CAM12 -> CAM17")
        print("API docs:   http://127.0.0.1:8000/docs")
        print("Health:     http://127.0.0.1:8000/health")
        print("WS stream:  ws://127.0.0.1:8000/api/v1/ws/events\n")
    except Exception as e:
        print(f"\n[ERROR] Seed failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

