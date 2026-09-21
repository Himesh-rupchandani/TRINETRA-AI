"""Restore the old camera directory without restoring synthetic demo activity."""
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.database.camera_directory import restore_sentinel_directory
from app.database.database import get_db
from app.database.models import Base, Camera, Watchlist, VehicleEvent, Alert, CameraTrafficConfig
from app.services import sentinel_catalogue_service as catalogue


@pytest.fixture
def registry(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'registry.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, 'SENTINEL_HLS_BASE_URL', 'https://cctv.corp8.cloud')
    with factory() as db:
        for i in range(1,5):
            db.add(Camera(camera_id=f'CAM{i:02}', name=f'Existing {i}', stream_url=f'https://custom.invalid/{i}.m3u8', latitude=10+i, longitude=40+i, status='OFFLINE'))
        db.add(Camera(camera_id='CAMLIVE', name='Live slot', stream_url=''))
        db.add(Watchlist(plate_number='GJ01AB1234', category='operator entry', active=True))
        db.add(VehicleEvent(camera_id='CAM01', plate_number='GJ01AB1234', evidence_ref='real/existing.jpg'))
        db.add(CameraTrafficConfig(camera_id='CAM01', config_json='{"mode":"off"}', revision='existing'))
        db.commit()
    yield factory
    engine.dispose()


def test_five_to_thirty_one_preserves_existing_records_and_never_seeds_events(registry):
    with registry() as db:
        before = db.query(Camera).filter_by(camera_id='CAM01').one()
        identity = (before.name, before.stream_url, before.latitude, before.longitude, before.status)
        result = restore_sentinel_directory(db)
        db.commit()
        assert result['added_count'] == 26
        assert result['grid_cameras'] == 30 and result['total_cameras'] == 31
        assert result['availability_checked'] is False
        after = db.query(Camera).filter_by(camera_id='CAM01').one()
        assert (after.name, after.stream_url, after.latitude, after.longitude, after.status) == identity
        assert db.query(Watchlist).count() == 1
        assert db.query(VehicleEvent).count() == 1
        assert db.query(Alert).count() == 0
        assert db.query(CameraTrafficConfig).one().revision == 'existing'
        added = db.query(Camera).filter_by(camera_id='CAM06').one()
        assert added.name == 'Timbavadi gate-Junagadh'
        assert added.latitude is None and added.longitude is None
        assert added.fps is None and added.status == 'OFFLINE'


def test_restore_is_idempotent_and_case_insensitive(registry):
    with registry() as db:
        db.query(Camera).filter_by(camera_id='CAM01').one().camera_id = 'cam01'
        db.commit()
        first = restore_sentinel_directory(db); db.commit()
        second = restore_sentinel_directory(db); db.commit()
        assert first['added_count'] == 26 and second['added_count'] == 0
        assert db.query(Camera).count() == 31
        assert db.query(Camera).filter_by(camera_id='cam01').one().name == 'Existing 1'


def test_custom_provider_does_not_get_an_unrelated_directory(registry, monkeypatch):
    monkeypatch.setattr(settings, 'SENTINEL_HLS_BASE_URL', 'https://another-provider.invalid')
    with registry() as db:
        result=restore_sentinel_directory(db)
        assert result['status']=='warning' and result['added_count']==0
        assert db.query(Camera).count()==5


def test_restore_endpoint_registers_only_new_metadata_without_starting_streams(registry, monkeypatch):
    from app.api import ingest
    calls=[]
    monkeypatch.setattr(ingest, 'vision_available', lambda:True)
    monkeypatch.setattr(ingest.camera_manager, 'add_camera', lambda **kwargs:calls.append(kwargs))
    app=FastAPI()
    app.include_router(ingest.router,prefix='/api')
    app.include_router(ingest.router,prefix='/api/v1')
    def session():
        with registry() as db: yield db
    app.dependency_overrides[get_db]=session
    with TestClient(app) as client:
        first=client.post('/api/ingest/restore-camera-list')
        assert first.status_code==200 and first.json()['total_cameras']==31
        assert len(calls)==26 and all(c['auto_start'] is False for c in calls)
        again=client.post('/api/v1/ingest/restore-camera-list')
        assert again.json()['added_count']==0 and len(calls)==26


def test_login_page_is_reported_as_failed_sync_not_a_camera(registry, monkeypatch):
    original=httpx.Client
    def reply(request):
        assert 'authorization' not in request.headers
        if request.url.path.endswith('cameras.json'):
            return httpx.Response(302,headers={'Location':'/auth/login'})
        return httpx.Response(200,text='<html>Sign in</html>',headers={'Content-Type':'text/html'})
    monkeypatch.setattr(catalogue.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(reply),**kwargs))
    with registry() as db:
        result=catalogue.sync_sentinel_catalogue(db)
        assert result['status']=='warning' and result['synced_count']==0
        assert 'sign-in' in result['message']
        assert db.query(Camera).count()==5
        assert db.query(Camera).filter_by(camera_id='CAM_UNKNOWN').first() is None


@pytest.mark.parametrize('payload',[{'detail':'login required'}, {'data':{'error':'unauthorized'}}, [], [None, 3, {'name':'not a camera'}]])
def test_malformed_catalogue_cannot_invent_registry_entries(registry,payload):
    with registry() as db:
        result=catalogue.sync_sentinel_catalogue(db,raw_payload=payload)
        assert result['status']=='warning'
        assert db.query(Camera).count()==5


def test_sync_endpoint_does_not_claim_success_for_warning(registry,monkeypatch):
    from app.api import ingest
    monkeypatch.setattr(ingest,'sync_sentinel_catalogue',lambda db:{'status':'warning','message':'Login required','synced_count':0,'total_cameras':5,'cameras':[]})
    with registry() as db:
        result=ingest.get_catalogue(sync=True,db=db)
    assert result['synced'] is False and result['source']=='database'


def test_production_boot_does_not_add_demo_watchlist(registry,monkeypatch):
    from app.database import database
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'AUTO_SEED_DEMO',False)
    with registry() as db:
        db.query(Watchlist).delete(); db.commit()
        engine=db.get_bind()
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'SessionLocal',registry)
    database.init_db()
    with registry() as db:
        assert db.query(Watchlist).count()==0
        assert db.query(Camera).count()==5
        assert db.query(VehicleEvent).count()==1


def test_render_enables_only_camera_directory_not_synthetic_dataset():
    root=Path(__file__).resolve().parents[3]
    docker=(root/'deploy/render.Dockerfile').read_text()
    assert 'AUTO_REGISTER_SENTINEL_GRID=true' in docker
    assert 'AUTO_SEED_DEMO=false' in docker and 'AUTO_START_CAMERAS=false' in docker


@pytest.mark.asyncio
async def test_render_startup_repairs_five_camera_registry_without_opening_streams(registry, monkeypatch, tmp_path):
    import app.main as main
    from app.database import database
    from types import SimpleNamespace
    with registry() as db:
        engine=db.get_bind()
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'SessionLocal',registry)
    monkeypatch.setattr(main,'SessionLocal',registry)
    monkeypatch.setattr(main,'vision_available',lambda:False)
    monkeypatch.setattr(settings,'AUTO_REGISTER_SENTINEL_GRID',True)
    monkeypatch.setattr(settings,'AUTO_SEED_DEMO',False)
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    monkeypatch.setattr(settings,'DEMO_ALERTS_ENABLED',False)
    monkeypatch.setattr(settings,'AUTO_START_CAMERAS',False)
    monkeypatch.setattr(settings,'EVIDENCE_ROOT',str(tmp_path/'evidence'))
    calls=[]
    monkeypatch.setattr(main,'camera_manager',SimpleNamespace(
        list_cameras=lambda:[],set_pipeline_callback=lambda value:None,
        add_camera=lambda **kw:calls.append(kw), stop_camera=lambda key:None))
    monkeypatch.setattr(main,'live_anpr_service',SimpleNamespace(stop=lambda:None))
    async with main.lifespan(main.app):
        with registry() as db:
            assert db.query(Camera).count()==31
            assert db.query(VehicleEvent).count()==1
            assert db.query(Alert).count()==0
        assert main._camera_registry_report['grid_cameras']==30
        assert main._camera_registry_report['added_count']==26
        assert calls==[]  # registration never requires a running CV decoder


def test_restore_caller_can_roll_back_all_new_rows(registry):
    with registry() as db:
        assert restore_sentinel_directory(db)['added_count']==26
        db.rollback()
    with registry() as db:
        assert db.query(Camera).count()==5
        assert db.query(VehicleEvent).count()==1
