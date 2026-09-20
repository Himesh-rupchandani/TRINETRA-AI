"""Deployment preparation tests. No Render account, network or package installs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'TRINETRAAI/backend'
sys.path.insert(0, str(BACKEND))


def load_script(name):
    spec = importlib.util.spec_from_file_location('test_' + name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forced_api_only_reports_the_flag_not_missing_packages():
    env = {**os.environ, 'TRINETRA_API_ONLY': '1', 'RENDER': 'true', 'PYTHONPATH': str(BACKEND)}
    proc = subprocess.run([sys.executable, '-c',
        'import json; from app.core.vision import vision_status; print(json.dumps(vision_status()))'],
        env=env, capture_output=True, text=True, check=True)
    result = json.loads(proc.stdout)
    assert result['available'] is False and result['forced_api_only'] is True
    assert result['deployment'] == 'render'
    assert 'TRINETRA_API_ONLY' in result['reason']
    assert 'not installed' not in result['reason']


def test_broken_native_import_is_not_called_an_absent_package(monkeypatch):
    import builtins
    monkeypatch.delenv('TRINETRA_API_ONLY', raising=False)
    original = builtins.__import__
    def broken(name, *args, **kwargs):
        if name == 'cv2':
            raise OSError('private filesystem path / secret-value must not reach public health')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', broken)
    spec = importlib.util.spec_from_file_location('vision_failure_probe', BACKEND / 'app/core/vision.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.vision_status()
    assert result['numpy'] is True and result['cv2'] is False
    assert result['import_error_types']['cv2'] == 'OSError'
    assert 'could not be imported' in result['reason']
    assert 'secret-value' not in json.dumps(result)
    with pytest.raises(Exception) as error:
        module.require_vision()
    assert error.value.status_code == 503
    assert error.value.detail['error'] == 'VISION_STACK_UNAVAILABLE'


def test_healthy_headless_install_is_left_alone(monkeypatch):
    module = load_script('ensure_headless_opencv')
    monkeypatch.setattr(module, 'installed', lambda name: name == module.HEADLESS)
    monkeypatch.setattr(module, 'import_works', lambda: True)
    monkeypatch.setattr(module, 'pip', lambda *args: pytest.fail('must not reinstall healthy OpenCV'))
    module.main()


def test_installed_but_broken_headless_gets_repaired(monkeypatch):
    module = load_script('ensure_headless_opencv')
    monkeypatch.setattr(module, 'installed', lambda name: name == module.HEADLESS)
    results = iter([False, True])
    monkeypatch.setattr(module, 'import_works', lambda: next(results))
    calls = []
    monkeypatch.setattr(module, 'pip', lambda *args: calls.append(args))
    module.main()
    assert calls == [('install', '--force-reinstall', '--no-deps', 'opencv-python-headless>=4.9.0')]


def test_repair_does_not_claim_success_if_import_is_still_broken(monkeypatch):
    module = load_script('ensure_headless_opencv')
    monkeypatch.setattr(module, 'installed', lambda name: False)
    monkeypatch.setattr(module, 'pip', lambda *args: None)
    monkeypatch.setattr(module, 'import_works', lambda: False)
    with pytest.raises(SystemExit, match='still cannot be imported'):
        module.main()


def test_render_startup_refuses_forced_api_only(monkeypatch, capsys):
    module = load_script('render_preflight')
    monkeypatch.setenv('TRINETRA_API_ONLY','true')
    monkeypatch.setattr(module, 'import_checks', lambda: pytest.fail('flag check should fail before heavy imports'))
    assert module.main(['--imports-only']) == 1
    assert 'Unset' in capsys.readouterr().err


def test_preflight_missing_dependencies_fail_without_camera_or_db_access(monkeypatch):
    module = load_script('render_preflight')
    monkeypatch.delenv('TRINETRA_API_ONLY', raising=False)
    monkeypatch.setattr(module, 'import_checks', lambda: ({'cv2': {'available': False}}, ['cv2']))
    assert module.main(['--imports-only']) == 1


def test_weights_check_rejects_lfs_pointers_and_missing_files(tmp_path):
    module = load_script('render_preflight')
    assert not module.is_weight_file(tmp_path / 'missing.pt')
    pointer = tmp_path / 'pointer.pt'
    pointer.write_bytes(b'version https://git-lfs.github.com/spec/v1\n' + b'0'*2048)
    assert not module.is_weight_file(pointer)
    actual = tmp_path / 'actual.pt'
    actual.write_bytes(b'PK' + b'0'*2048)
    assert module.is_weight_file(actual)


def test_cors_exposes_whep_resource_location_to_vercel():
    from app.main import app
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import Response
    middleware = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert {'Location','ETag'} <= set(middleware.kwargs['expose_headers'])
    isolated = FastAPI()
    isolated.add_middleware(CORSMiddleware, **{**middleware.kwargs, 'allow_origins': ['https://ui.example.test']})
    @isolated.post('/signal')
    def signal():
        return Response('v=0',status_code=201,headers={'Location':'/sentinel/stream/cam1/whep/session'})
    with TestClient(isolated) as client:
        response=client.post('/signal',headers={'Origin':'https://ui.example.test'})
    assert response.headers['access-control-allow-origin'] == 'https://ui.example.test'
    assert 'Location' in response.headers['access-control-expose-headers']


def test_render_scripts_are_root_scoped_single_worker_and_non_destructive():
    build=(ROOT/'scripts/render_build.sh').read_text()
    start=(ROOT/'scripts/render_start.sh').read_text()
    assert 'requirements-ml.txt' in build and 'ensure_headless_opencv.py' in build
    assert 'download.pytorch.org/whl/cpu' in build
    assert '--workers 1' in start and '${PORT:-10000}' in start
    assert 'render_preflight.py' in start
    assert 'seed_demo' not in start and 'rm -' not in start
    subprocess.run(['bash','-n', str(ROOT/'scripts/render_build.sh'), str(ROOT/'scripts/render_start.sh')], check=True)
