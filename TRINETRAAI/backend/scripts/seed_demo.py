"""
TRINETRA AI Demo Seed Script
============================
Seeds the database with:
  - 30 realistic CCTV cameras across Ahmedabad/Gujarat
  - 10 watchlist entries (including GJ01AB1234 as STOLEN / CRITICAL)
  - 20+ vehicle events including the primary demo journey:
      GJ01AB1234: CAM04 → CAM12 → CAM17 → CAM08
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


def demo_base_time():
    """Anchor the demo timeline to "recently" instead of a fixed date.

    A hard-coded date silently ages out of every 24h window, so the Command
    Center KPIs read zero on demo day. Anchoring to now keeps the relative
    gaps between sightings (which is what the trace actually asserts) while
    making the data look live.
    """
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return now - timedelta(minutes=90)


def seed_cameras(db):
    count = db.query(Camera).count()
    # Fix for stale local DBs (e.g. 4 cameras OFFLINE) — reseed if not 30
    if count == 30:
        print("  → Cameras already seeded (30), skipping.")
        return
    if count > 0 and count != 30:
        print(f"  → Found {count} cameras (stale/partial), clearing and reseeding 30...")
        db.query(Camera).delete()
        db.commit()

    # Canonical CCTV registry (Model 1 foundation). These 30 rows are the
    # single source of truth for camera identity / location / department:
    # the frontend demo seed mirrors this exact table, so DEMO and LIVE
    # modes never disagree about what CAM04 is.
    #
    # Labels come from the SENTINEL live grid (05/09/2026) and are kept
    # verbatim, including casing; coordinates are the real siting of each
    # camera, resolved to town/suburb level. `Delight RLVD` and
    # `Mohanpura` could not be pinned down — they carry zone
    # "Unconfirmed" and the control-room coordinate instead of a guess.
    cameras = [
        Camera(camera_id="CAM01", name="Chiman bhai Bridge", location="Chiman bhai Bridge",
               stream_url="https://cctv.corp8.cloud/cam01/index.m3u8", stream_type="hls",
               latitude=23.073, longitude=72.592,
               department="Traffic Police", zone="Ahmedabad",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM02", name="Janpath", location="Janpath",
               stream_url="https://cctv.corp8.cloud/cam02/index.m3u8", stream_type="hls",
               latitude=23.0225, longitude=72.5625,
               department="Police", zone="Ahmedabad",
               codec="H264", width=2560, height=1440, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM03", name="O.N.G.C. Office", location="O.N.G.C. Office",
               stream_url="https://cctv.corp8.cloud/cam03/index.m3u8", stream_type="hls",
               latitude=23.107, longitude=72.595,
               department="Industrial Security", zone="Ahmedabad",
               codec="H264", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM04", name="Paldi Circle", location="Paldi Circle",
               stream_url="https://cctv.corp8.cloud/cam04/index.m3u8", stream_type="hls",
               latitude=23.0126, longitude=72.5647,
               department="Police", zone="Ahmedabad",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM05", name="Visat teen Rasta", location="Visat teen Rasta",
               stream_url="https://cctv.corp8.cloud/cam05/index.m3u8", stream_type="hls",
               latitude=23.087, longitude=72.593,
               department="Traffic Police", zone="Ahmedabad",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM06", name="Timbavadi gate-Junagadh", location="Timbavadi gate-Junagadh",
               stream_url="https://cctv.corp8.cloud/cam06/index.m3u8", stream_type="hls",
               latitude=21.5236, longitude=70.455,
               department="Police", zone="Junagadh",
               codec="H265", width=1280, height=720, fps=15,
               status="ONLINE"),
        Camera(camera_id="CAM07", name="hero-showroom-gir-somnath", location="hero-showroom-gir-somnath",
               stream_url="https://cctv.corp8.cloud/cam07/index.m3u8", stream_type="hls",
               latitude=20.9097, longitude=70.3666,
               department="Police", zone="Gir Somnath",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM08", name="majewadi-gate-junagadh", location="majewadi-gate-junagadh",
               stream_url="https://cctv.corp8.cloud/cam08/index.m3u8", stream_type="hls",
               latitude=21.53, longitude=70.462,
               department="Police", zone="Junagadh",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM09", name="new-bypass-near-by-circle-junagadh-2", location="new-bypass-near-by-circle-junagadh-2",
               stream_url="https://cctv.corp8.cloud/cam09/index.m3u8", stream_type="hls",
               latitude=21.5355, longitude=70.478,
               department="Highway Authority", zone="Junagadh",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM10", name="char-chowk-road-2-junagadh", location="char-chowk-road-2-junagadh",
               stream_url="https://cctv.corp8.cloud/cam10/index.m3u8", stream_type="hls",
               latitude=21.5222, longitude=70.4573,
               department="Police", zone="Junagadh",
               codec="H264", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM11", name="dolatpara-junagadh", location="dolatpara-junagadh",
               stream_url="https://cctv.corp8.cloud/cam11/index.m3u8", stream_type="hls",
               latitude=21.5255, longitude=70.456,
               department="Municipal (JMC)", zone="Junagadh",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM12", name="Tri Mandir Adalaj Tollnaka", location="Tri Mandir Adalaj Tollnaka",
               stream_url="https://cctv.corp8.cloud/cam12/index.m3u8", stream_type="hls",
               latitude=23.1662, longitude=72.5807,
               department="Highway Authority", zone="Gandhinagar",
               codec="H265", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM13", name="CN Vidhyalaya", location="CN Vidhyalaya",
               stream_url="https://cctv.corp8.cloud/cam13/index.m3u8", stream_type="hls",
               latitude=23.0305, longitude=72.5456,
               department="Municipal (AMC)", zone="Ahmedabad",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM14", name="Delight RLVD", location="Delight RLVD",
               stream_url="https://cctv.corp8.cloud/cam14/index.m3u8", stream_type="hls",
               latitude=23.0225, longitude=72.5714,
               department="Traffic Police", zone="Unconfirmed",
               codec="H264", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM15", name="Suvidha park", location="Suvidha park",
               stream_url="https://cctv.corp8.cloud/cam15/index.m3u8", stream_type="hls",
               latitude=23.0389, longitude=72.6608,
               department="Municipal (AMC)", zone="Ahmedabad",
               codec="H264", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM16", name="Visat P2", location="Visat P2",
               stream_url="https://cctv.corp8.cloud/cam16/index.m3u8", stream_type="hls",
               latitude=23.091, longitude=72.598,
               department="Traffic Police", zone="Ahmedabad",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM17", name="Rajkot Bus Port CCTV", location="Rajkot Bus Port CCTV",
               stream_url="https://cctv.corp8.cloud/cam17/index.m3u8", stream_type="hls",
               latitude=22.2908, longitude=70.799,
               department="Transport Dept", zone="Rajkot",
               codec="H265", width=1920, height=1080, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM18", name="Rajkot CCTV", location="Rajkot CCTV",
               stream_url="https://cctv.corp8.cloud/cam18/index.m3u8", stream_type="hls",
               latitude=22.3039, longitude=70.8022,
               department="Police", zone="Rajkot",
               codec="H265", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM19", name="KHAPARIA GRAM PANCHAYAT, TALUKA GANDEVI, DISTRICT NAVSARI", location="KHAPARIA GRAM PANCHAYAT, TALUKA GANDEVI, DISTRICT NAVSARI",
               stream_url="https://cctv.corp8.cloud/cam19/index.m3u8", stream_type="hls",
               latitude=20.8136, longitude=72.99,
               department="Gram Panchayat", zone="Navsari",
               codec="H264", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM20", name="Mohanpura", location="Mohanpura",
               stream_url="https://cctv.corp8.cloud/cam20/index.m3u8", stream_type="hls",
               latitude=23.0225, longitude=72.5714,
               department="Police", zone="Unconfirmed",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM21", name="Patan Dethali Char Rasta", location="Patan Dethali Char Rasta",
               stream_url="https://cctv.corp8.cloud/cam21/index.m3u8", stream_type="hls",
               latitude=23.9167, longitude=72.35,
               department="Police", zone="Patan",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM22", name="BK Mervada tran Rasta", location="BK Mervada tran Rasta",
               stream_url="https://cctv.corp8.cloud/cam22/index.m3u8", stream_type="hls",
               latitude=23.7833, longitude=72.1167,
               department="Police", zone="Patan",
               codec="H265", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM23", name="kheram", location="kheram",
               stream_url="https://cctv.corp8.cloud/cam23/index.m3u8", stream_type="hls",
               latitude=20.76, longitude=72.97,
               department="Gram Panchayat", zone="Navsari",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM24", name="dehgam", location="dehgam",
               stream_url="https://cctv.corp8.cloud/cam24/index.m3u8", stream_type="hls",
               latitude=23.1691, longitude=72.8066,
               department="Municipal (Dehgam)", zone="Gandhinagar",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM25", name="dhanori", location="dhanori",
               stream_url="https://cctv.corp8.cloud/cam25/index.m3u8", stream_type="hls",
               latitude=20.788, longitude=72.977,
               department="Gram Panchayat", zone="Navsari",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM26", name="TANKAL", location="TANKAL",
               stream_url="https://cctv.corp8.cloud/cam26/index.m3u8", stream_type="hls",
               latitude=20.78, longitude=73.132,
               department="Gram Panchayat", zone="Navsari",
               codec="H265", width=1280, height=720, fps=20,
               status="ONLINE"),
        Camera(camera_id="CAM27", name="bilimora", location="bilimora",
               stream_url="https://cctv.corp8.cloud/cam27/index.m3u8", stream_type="hls",
               latitude=20.7508, longitude=72.951,
               department="Municipal (Bilimora)", zone="Navsari",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
        Camera(camera_id="CAM28", name="bilimora", location="bilimora",
               stream_url="https://cctv.corp8.cloud/cam28/index.m3u8", stream_type="hls",
               latitude=20.7543, longitude=72.9562,
               department="Municipal (Bilimora)", zone="Navsari",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM29", name="bilimora", location="bilimora",
               stream_url="https://cctv.corp8.cloud/cam29/index.m3u8", stream_type="hls",
               latitude=20.747, longitude=72.9478,
               department="Municipal (Bilimora)", zone="Navsari",
               codec="H264", width=2560, height=1440, fps=30,
               status="ONLINE"),
        Camera(camera_id="CAM30", name="Gandhidham Rambaugh p2", location="Gandhidham Rambaugh p2",
               stream_url="https://cctv.corp8.cloud/cam30/index.m3u8", stream_type="hls",
               latitude=23.0759, longitude=70.131,
               department="Municipal (GDM)", zone="Kutch",
               codec="H264", width=1920, height=1080, fps=25,
               status="ONLINE"),
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
    count = db.query(VehicleEvent).count()
    if count > 0:
        # If cameras were stale, events are also stale — reseed
        cam_count = db.query(Camera).count()
        if cam_count == 30 and count >= 20:
            print("  → Vehicle events already seeded, skipping.")
            return
        print(f"  → Found {count} events with {cam_count} cameras, clearing and reseeding...")
        db.query(VehicleEvent).delete()
        db.commit()

    base_time = demo_base_time()

    # The primary journey is a real intercity escape (Paldi Ahmedabad -> Adalaj
    # -> Rajkot -> Junagadh, ~7h20m of driving), so it starts 6h before the
    # other seed data and ends ~11 minutes ago. Event coordinates always match
    # the seeded camera registry.
    journey_start = base_time - timedelta(hours=6)

    events = [
        # === PRIMARY DEMO JOURNEY: GJ01AB1234 (STOLEN) across 4 cameras ===
        VehicleEvent(camera_id="CAM04", vehicle_track_id=101, plate_raw="GJ 01 AB-1234",
                     plate_number="GJ01AB1234", plate_confidence=0.97, vehicle_class="car",
                     event_time=journey_start, latitude=23.0126, longitude=72.5647,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM12", vehicle_track_id=101, plate_raw="GJ01AB1234",
                     plate_number="GJ01AB1234", plate_confidence=0.99, vehicle_class="car",
                     event_time=journey_start + timedelta(minutes=42), latitude=23.1662, longitude=72.5807,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM17", vehicle_track_id=101, plate_raw="GJ-01-AB-1234",
                     plate_number="GJ01AB1234", plate_confidence=0.91, vehicle_class="car",
                     event_time=journey_start + timedelta(minutes=313), latitude=22.2908, longitude=70.799,
                     watchlist_match=True),
        VehicleEvent(camera_id="CAM08", vehicle_track_id=101, plate_raw="GJ 01 AB 1234",
                     plate_number="GJ01AB1234", plate_confidence=0.94, vehicle_class="car",
                     event_time=journey_start + timedelta(minutes=439), latitude=21.53, longitude=70.462,
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
    print(f"  → Seeded {len(events)} vehicle events.")


def seed_alerts(db):
    count = db.query(Alert).count()
    if count > 0:
        cam_count = db.query(Camera).count()
        if cam_count == 30 and count >= 5:
            print("  → Alerts already seeded, skipping.")
            return
        print(f"  → Found {count} alerts, clearing and reseeding...")
        db.query(Alert).delete()
        db.commit()

    base_time = demo_base_time()
    journey_start = base_time - timedelta(hours=6)

    alerts = [
        Alert(camera_id="CAM04", plate_number="GJ01AB1234", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="NEW",
              message="WATCHLIST HIT: GJ01AB1234 on CAM04. Category: stolen vehicle. FIR #4812.",
              timestamp=journey_start),
        Alert(camera_id="CAM08", plate_number="GJ01AB1234", alert_type="WATCHLIST_MATCH",
              severity="CRITICAL", status="ACKNOWLEDGED",
              message="WATCHLIST HIT: GJ01AB1234 on CAM08. Category: stolen vehicle. FIR #4812.",
              timestamp=journey_start + timedelta(minutes=439),
              acknowledged_at=journey_start + timedelta(minutes=440),
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
              timestamp=journey_start + timedelta(minutes=42)),
    ]
    db.add_all(alerts)
    db.commit()

    # --- Relational integrity backfill (spec: DB consistency) ----------------
    # An alert must point at the event that produced it, and a watchlist alert
    # must point at the watchlist record it matched. Seeding them detached made
    # the alert screen show hits with no evidence trail behind them.
    linked_events = linked_watchlist = 0
    for alert in alerts:
        if alert.plate_number:
            wl = (
                db.query(Watchlist)
                .filter(
                    Watchlist.plate_number == alert.plate_number,
                    Watchlist.active == True,  # noqa: E712
                )
                .first()
            )
            if wl:
                alert.watchlist_id = wl.id
                linked_watchlist += 1

        # Nearest sighting of the same plate on the same camera.
        ev = (
            db.query(VehicleEvent)
            .filter(
                VehicleEvent.camera_id == alert.camera_id,
                VehicleEvent.plate_number == alert.plate_number,
            )
            .order_by(VehicleEvent.event_time.asc())
            .all()
        )
        if ev:
            best = min(ev, key=lambda e: abs((e.event_time - alert.timestamp).total_seconds()))
            alert.event_id = best.id
            if alert.confidence is None:
                alert.confidence = best.plate_confidence
            linked_events += 1

    db.commit()
    print(f"  → Seeded {len(alerts)} alerts.")
    print(f"    ↳ linked to events: {linked_events}/{len(alerts)}, "
          f"watchlist records: {linked_watchlist}/{len(alerts)}")


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
        print("Demo plate: GJ01AB1234 -> CAM04 -> CAM12 -> CAM17 -> CAM08")
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

