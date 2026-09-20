"""OCR retry/diagnostic logic tests. Fixture strings are not accuracy claims."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.services import anpr_pipeline as anpr
from app.services.ocr_service import OcrService
from app.services.plate_detector_service import PlateBox
from .test_live_anpr import rig, rows
from app.services import live_anpr_service as live


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr(type(anpr.ocr_service), 'available', property(lambda self: True))
    monkeypatch.setattr(anpr.ocr_service._read_context, 'error', None, raising=False)
    monkeypatch.setattr(settings, 'OCR_MIN_CONFIDENCE', .6)
    monkeypatch.setattr(settings, 'OCR_LOW_CONFIDENCE_MARK', .8)
    monkeypatch.setattr(anpr, 'preprocess_variants', lambda crop, **kwargs: [crop, crop, crop])
    monkeypatch.setattr(anpr.plate_detector_service, 'detect', lambda *args, **kw: [PlateBox(10,20,55,35,.9,'model')])
    monkeypatch.setattr(anpr.plate_detector_service, 'fallback_region', lambda *args: PlateBox(0,100,300,200,.05,'heuristic'))
    return np.full((200,300,3),127,np.uint8)


def test_bad_localization_does_not_block_lower_vehicle_rescue(reader, monkeypatch):
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image: [('GJ11S1234',.97)] if image.shape[1]>100 else [])
    diagnostic=anpr.PlateAttempt()
    result=anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic)
    assert result.normalized=='GJ11S1234'  # one-letter series already valid
    assert result.requires_review and result.status=='LOW_CONFIDENCE'
    assert diagnostic.fallback_used and diagnostic.state=='READ'
    assert diagnostic.ocr_calls==4
    votes=anpr.TrackPlateAccumulator();votes.add(result);votes.add(result)
    assert votes.status()=='LOW_CONFIDENCE'  # rescue cannot raise a watchlist alarm


def test_localized_success_does_not_run_rescue(reader,monkeypatch):
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image:[('GJ01AB1234',.97)])
    monkeypatch.setattr(anpr.plate_detector_service,'fallback_region',lambda *args:pytest.fail('unneeded fallback'))
    diagnostic=anpr.PlateAttempt()
    result=anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic)
    assert result.normalized=='GJ01AB1234' and not result.requires_review
    assert diagnostic.ocr_calls==1 and not diagnostic.fallback_used
    assert result.plate_box.x1 < 10 and result.plate_box.y1 < 20  # stroke-safe padding


def test_ocr_call_budget_is_bounded_and_rescue_does_not_guess_characters(reader,monkeypatch):
    monkeypatch.setattr(anpr.plate_detector_service,'detect',lambda *a,**kw:[PlateBox(10,20,55,35,.9,'model'),PlateBox(70,20,120,35,.8,'model')])
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image:[('GJ11S7A24',.99)] if image.shape[1]>150 else [])
    diagnostic=anpr.PlateAttempt()
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200],max_regions=99,diagnostics=diagnostic) is None
    assert diagnostic.ocr_calls==8
    assert diagnostic.state=='NO_PLATE_TEXT'


def test_low_confidence_is_not_increased_to_make_an_event(reader,monkeypatch):
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image:[('GJ01AB1234',.5)])
    diagnostic=anpr.PlateAttempt()
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic) is None
    assert diagnostic.state=='LOW_CONFIDENCE'


def test_ocr_engine_failure_is_explicit_and_stops_retries(reader,monkeypatch):
    def fail(image):
        anpr.ocr_service._read_context.error='RuntimeError'
        return []
    monkeypatch.setattr(anpr.ocr_service,'read_lines',fail)
    diagnostic=anpr.PlateAttempt()
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic) is None
    assert diagnostic.state=='ERROR' and diagnostic.ocr_calls==1


def test_missing_ocr_and_tiny_crop_have_distinct_states(reader,monkeypatch):
    monkeypatch.setattr(type(anpr.ocr_service),'available',property(lambda self:False))
    diagnostic=anpr.PlateAttempt()
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic) is None
    assert diagnostic.state=='UNAVAILABLE'
    monkeypatch.setattr(type(anpr.ocr_service),'available',property(lambda self:True))
    monkeypatch.setattr(anpr.plate_detector_service,'detect',lambda *a,**kw:[PlateBox(1,1,12,5,.05,'heuristic')])
    diagnostic=anpr.PlateAttempt()
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200],diagnostics=diagnostic) is None
    assert diagnostic.state=='TOO_SMALL' and diagnostic.ocr_calls==0


def test_nonfinite_scores_are_never_promoted_to_a_plate(reader,monkeypatch):
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image:[('GJ01AB1234',float('nan')),('MH02CD5678',float('inf'))])
    assert anpr.read_plate_for_vehicle(reader,[0,0,300,200]) is None


def test_runtime_status_does_not_start_ocr(monkeypatch):
    service=OcrService()
    monkeypatch.setattr(service,'_ensure_engine',lambda:pytest.fail('health must not load models'))
    monkeypatch.setattr(settings,'OCR_ENABLED',True)
    assert service.runtime_status()['state']=='NOT_STARTED'
    service._attempted=True
    assert service.runtime_status()['state']=='UNAVAILABLE'
    monkeypatch.setattr(settings,'OCR_ENABLED',False)
    assert service.runtime_status()['state']=='DISABLED'


def test_first_read_is_pending_not_failed_and_two_reads_still_save(rig):
    _,factory,_,_,process=rig
    first=process()
    assert all(p['ocr_state']=='CONFIRMING' for p in first['photos'])
    assert all(p['ocr_agreement_reads']==1 and p['ocr_required_reads']==2 for p in first['photos'])
    assert all(p['plate_number'] is None for p in first['photos']) and not rows(factory)
    second=process()
    assert all(p['ocr_state']=='CONFIRMED' and p['plate_number'] for p in second['photos'])
    assert len(rows(factory))==3


def test_failed_read_can_show_actual_scanned_area_without_creating_a_plate(rig,monkeypatch):
    service,factory,_,messages,process=rig
    def unreadable(frame, bbox, vehicle_class, *, diagnostics):
        diagnostics.state='LOW_CONFIDENCE'
        diagnostics.region=PlateBox(int(bbox[0])+5,40,int(bbox[0])+70,70,.8,'model')
        return None
    monkeypatch.setattr(live,'read_plate_for_vehicle',unreadable)
    result=process()
    assert all(p['ocr_state']=='LOW_CONFIDENCE' and p['plate_image_path'] for p in result['photos'])
    photo=result['photos'][0]
    capture,track=photo['id'].split(':')
    assert service.photo('CAM1',capture,int(track),'plate').startswith(b'\xff\xd8')
    assert not rows(factory) and not messages


def test_queued_reading_and_engine_unavailable_are_not_plate_not_read(rig,monkeypatch):
    service,_,_,_,process=rig
    states=[]
    def reader(*args, diagnostics):
        states.append([p['ocr_state'] for p in service.snapshot('cam1')['photos']])
        diagnostics.state='NO_TEXT'
        return None
    monkeypatch.setattr(live,'read_plate_for_vehicle',reader)
    process()
    assert states[0]==['READING','QUEUED','QUEUED']
    assert states[1]==['NO_TEXT','READING','QUEUED']
    monkeypatch.setattr(type(live.ocr_service),'available',property(lambda self:False))
    result=process()
    assert all(p['ocr_state']=='UNAVAILABLE' for p in result['photos'])


def test_padding_preserves_character_scale(reader,monkeypatch):
    requested=[]
    monkeypatch.setattr(anpr,'preprocess_variants',lambda crop, target_height=128: requested.append(target_height) or [crop])
    monkeypatch.setattr(anpr.ocr_service,'read_lines',lambda image:[('GJ01AB1234',.97)])
    anpr.read_plate_for_vehicle(reader,[0,0,300,200])
    assert requested[0]>128  # margin is not allowed to shrink glyphs below the old scale
