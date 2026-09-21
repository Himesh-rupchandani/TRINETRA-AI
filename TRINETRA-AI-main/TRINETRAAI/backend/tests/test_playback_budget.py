"""Playback protection tests; no real models, network cameras or paid resources."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import resource_budget
from app.services import live_anpr_service as live
from app.camera.manager import CameraManager
from .test_live_anpr import rig, api, rows

MB = 1024 * 1024


def test_small_container_blocks_model_admission_not_the_data_api():
    budget = resource_budget.memory_decision(512*MB, 100*MB)
    assert not budget['allowed'] and budget['state'] == 'INSUFFICIENT_MEMORY'
    assert '512 MB' in budget['reason']
    assert budget['retry_after_ms'] == 5000


def test_runtime_pressure_recovers_and_unknown_capacity_is_not_invented():
    assert not resource_budget.memory_decision(2048*MB, 2000*MB)['allowed']
    assert resource_budget.memory_decision(2048*MB, 500*MB)['allowed']
    unknown = resource_budget.memory_decision(None, None)
    assert unknown['state'] == 'UNKNOWN_LIMIT' and unknown['limit_mb'] is None
    assert resource_budget.memory_decision(512*MB, 500*MB, enabled=False)['state'] == 'UNCHECKED'


def test_cgroup_v2_and_v1_readings_are_bounded_and_account_for_file_cache(tmp_path):
    (tmp_path/'memory.max').write_text(str(2*1024*MB))
    (tmp_path/'memory.current').write_text(str(1700*MB))
    (tmp_path/'memory.stat').write_text(f'inactive_file {300*MB}\n')
    assert resource_budget.container_memory(tmp_path) == (2048*MB, 1400*MB)
    (tmp_path/'memory.max').write_text('max')
    folder=tmp_path/'memory';folder.mkdir()
    (folder/'memory.limit_in_bytes').write_text(str(512*MB))
    (folder/'memory.usage_in_bytes').write_text(str(250*MB))
    assert resource_budget.container_memory(tmp_path) == (512*MB, 250*MB)


def test_memory_refusal_never_allocates_or_decodes_a_posted_image(api, rig, monkeypatch):
    from app.api import live_anpr
    budget=resource_budget.memory_decision(512*MB, 100*MB)
    monkeypatch.setattr(live_anpr,'inference_budget',lambda:budget)
    monkeypatch.setattr(live,'inference_budget',lambda:budget)
    monkeypatch.setattr(live_anpr,'decode_frame',lambda data:pytest.fail('no decode under memory pressure'))
    response=api.post('/api/cameras/cam1/detect-frame',content=b'not allocated as an image',headers={'Content-Type':'image/jpeg'})
    assert response.status_code==200
    data=response.json()
    assert data['accepted'] is False and data['status']=='UNAVAILABLE'
    assert data['resource_budget']['state']=='INSUFFICIENT_MEMORY'
    service,factory,*_=rig
    assert not service._pending and not service._states and not rows(factory)


def test_throttled_camera_does_not_pay_jpeg_decode_cost_twice(api, rig, monkeypatch):
    from app.api import live_anpr
    service,*_=rig
    assert service.submit('CAM1',np.zeros((24,40,3),np.uint8),source_id='browser:one')
    monkeypatch.setattr(live_anpr,'decode_frame',lambda data:pytest.fail('throttled decode'))
    response=api.post('/api/cameras/cam1/detect-frame?client_id=one',content=b'compressed payload',headers={'Content-Type':'image/jpeg'})
    assert response.json()['accepted'] is False
    assert response.json()['retry_after_ms'] > 0


def test_low_memory_preflight_does_not_import_torch_before_starting_the_guard(monkeypatch):
    import importlib.util
    path=Path(__file__).resolve().parents[3]/'scripts/render_preflight.py'
    spec=importlib.util.spec_from_file_location('resource_preflight_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.delenv('TRINETRA_API_ONLY',raising=False)
    monkeypatch.setattr(resource_budget,'inference_budget',lambda:resource_budget.memory_decision(512*MB,100*MB))
    monkeypatch.setattr(module,'import_checks',lambda:pytest.fail('low-memory start must not load ML runtimes'))
    assert module.main([])==0


def test_mjpeg_toggle_keeps_the_same_decoder_and_recording_position(monkeypatch):
    import cv2
    manager=CameraManager()
    controls=[];submitted=[]
    monkeypatch.setattr(live,'live_anpr_service',SimpleNamespace(
        submit=lambda *a,**kw:submitted.append(kw.get('media_time')), annotate=lambda camera,frame,**kw:frame))
    class Capture:
        index=0
        released=False
        def get(self, key):
            return self.index*40 if key==cv2.CAP_PROP_POS_MSEC else 25
        def release(self): self.released=True
    capture=Capture()
    monkeypatch.setattr(manager,'_ondemand_candidates',lambda camera:[('fixture.mp4',True)])
    monkeypatch.setattr(manager,'_open_ondemand_capture',lambda source:controls.append(source) or capture)
    def frame(cap, source):
        cap.index+=1
        return np.zeros((120,200,3),np.uint8)
    monkeypatch.setattr(manager,'_read_ondemand_frame',frame)
    generator=manager.generate_mjpeg_stream('CAM1',detect_vehicles=True,viewer_id='viewer',initial_detection=True)
    try:
        next(generator)
        manager.set_view_detection('cam1','viewer',False,1)
        next(generator)
        manager.set_view_detection('cam1','viewer',True,2)
        next(generator)
        assert controls==['fixture.mp4']
        assert capture.index==3 and not capture.released
        assert submitted==[.04,.12]  # off frame still decoded/played, no inference
    finally:
        generator.close()
    assert capture.released and not manager._view_controls


def test_toggle_is_camera_and_viewer_scoped_and_old_commands_cannot_win():
    manager=CameraManager()
    manager.set_view_detection('CAM1','first',True,3)
    manager.set_view_detection('CAM1','first',False,2)
    manager.set_view_detection('CAM1','second',False,1)
    manager.set_view_detection('CAM2','first',False,1)
    assert manager._view_controls[('CAM1','first')].enabled is True
    assert manager._view_controls[('CAM1','second')].enabled is False
    assert manager._view_controls[('CAM2','first')].enabled is False


def test_abandoned_view_controls_are_bounded_and_expire(monkeypatch):
    import app.camera.manager as module
    manager=CameraManager()
    now=[100.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    for i in range(128):manager.set_view_detection('CAM1',str(i),False)
    with pytest.raises(ValueError):manager.set_view_detection('CAM1','excess',False)
    now[0]+=16
    manager.set_view_detection('CAM1','fresh',True)
    assert len(manager._view_controls)==1


def test_viewer_control_api_validates_camera_and_token_without_opening_a_feed(api, rig, monkeypatch):
    from app.api import cameras
    manager=CameraManager()
    monkeypatch.setattr(cameras,'camera_manager',manager)
    api.app.include_router(cameras.router,prefix='/api')
    response=api.put('/api/cameras/cam1/live/detection',json={'viewer_id':'test-view','enabled':False,'sequence':4})
    assert response.status_code==200 and response.json()['enabled'] is False
    response=api.put('/api/cameras/cam1/live/detection',json={'viewer_id':'test-view','enabled':True,'sequence':3})
    assert response.json()['enabled'] is False
    assert api.put('/api/cameras/missing/live/detection',json={'viewer_id':'v','enabled':True}).status_code==404
    assert api.put('/api/cameras/cam1/live/detection',json={'viewer_id':'../bad','enabled':True}).status_code==422
    assert manager._streams=={}  # a toggle command cannot open a decoder


def test_model_loaders_do_not_import_heavy_engines_when_memory_is_refused(monkeypatch):
    from app.services import vehicle_detection_service as vehicles
    from app.services import ocr_service as ocr
    from app.services import plate_detector_service as plates
    budget=resource_budget.memory_decision(512*MB,100*MB)
    for module in (vehicles,ocr,plates):monkeypatch.setattr(module,'inference_budget',lambda:budget)
    v=vehicles.VehicleDetectionService()
    assert v._ensure_model() is None and not v.enabled
    o=ocr.OcrService();assert o._ensure_engine() is None and not o._attempted
    p=plates.PlateDetectorService();assert p._ensure_model() is None and not p._model_attempted


def test_managed_mjpeg_is_off_without_an_explicit_opt_in(monkeypatch):
    import cv2
    manager=CameraManager()
    calls=[]
    monkeypatch.setattr(live,'live_anpr_service',SimpleNamespace(
        submit=lambda *a,**kw:calls.append('submit'),
        annotate=lambda camera,frame,**kw:calls.append('annotate') or frame))
    capture=SimpleNamespace(get=lambda prop:25,release=lambda:None)
    monkeypatch.setattr(manager,'_ondemand_candidates',lambda camera:[('fixture.mp4',True)])
    monkeypatch.setattr(manager,'_open_ondemand_capture',lambda source:capture)
    monkeypatch.setattr(manager,'_read_ondemand_frame',lambda *a:np.zeros((100,200,3),np.uint8))
    stream=manager.generate_mjpeg_stream('CAM1',detect_vehicles=True,viewer_id='off-default')
    try:
        assert next(stream).startswith(b'--frame')
        assert calls==[]  # video served without even submitting an AI sample
        manager.set_view_detection('CAM1','off-default',True,1)
        next(stream)
        assert calls==['submit','annotate']
    finally:
        stream.close()


def test_resident_decoder_requires_separate_opt_in_but_a_selected_viewer_can_scan(rig,monkeypatch):
    from app.camera.packet import FramePacket
    from app.core.config import settings
    svc,*_=rig
    calls=[]
    monkeypatch.setattr(svc,'submit',lambda *a,**kw:calls.append(kw) or True)
    monkeypatch.setattr(settings,'LIVE_ANPR_RESIDENT_ENABLED',False)
    packet=FramePacket(np.zeros((30,40,3),np.uint8),1000,'CAM1',1,source_type='rtsp')
    assert not svc.submit_packet(packet) and not calls
    assert svc.submit_packet(packet,viewer_requested=True) and len(calls)==1
    monkeypatch.setattr(settings,'LIVE_ANPR_RESIDENT_ENABLED',True)
    assert svc.submit_packet(packet) and len(calls)==2
    packet.source_type='demo'
    assert not svc.submit_packet(packet,viewer_requested=True) and len(calls)==2


def test_selected_mjpeg_view_can_scan_resident_frames_without_background_ai(monkeypatch):
    from app.camera.packet import FramePacket
    manager=CameraManager()
    frame=np.zeros((100,200,3),np.uint8)
    packet=FramePacket(frame,1000,'CAM1',1,source_type='rtsp')
    calls=[]
    monkeypatch.setattr(live,'live_anpr_service',SimpleNamespace(
        submit_packet=lambda packet,**kw:calls.append(kw),
        annotate=lambda camera,frame,**kw:frame))
    monkeypatch.setattr(manager,'get_latest_frame',lambda *a,**kw:frame.copy())
    monkeypatch.setattr(manager,'has_live_signal',lambda *a:True)
    monkeypatch.setattr(manager,'get_latest_packet',lambda *a:packet)
    stream=manager.generate_mjpeg_stream('CAM1',detect_vehicles=True,viewer_id='resident-view',initial_detection=False)
    try:
        next(stream); assert calls==[]
        manager.set_view_detection('CAM1','resident-view',True,1)
        next(stream); assert calls==[{'viewer_requested':True}]
        manager.set_view_detection('CAM1','resident-view',False,2)
        next(stream); assert len(calls)==1
    finally:
        stream.close()
