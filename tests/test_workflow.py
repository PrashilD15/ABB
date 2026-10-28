import asyncio
import io
import time
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.controller import MicroLogixAdapter
from backend.store import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, delay=.02)) as c:
        yield c



def check_and_review(client):
    response = client.post('/api/controller/check')
    if response.status_code == 200 and response.json()['pass']:
        client.post('/api/controller/review-contacts', json={'operator': 'Engineer', 'check_timestamp': response.json()['timestamp']})
    return response
def approved(client):
    p = client.post('/api/demo').json()
    p = client.post(f'/api/profiles/{p["id"]}/approve', json={'operator': 'Test engineer', 'mapping_confirmed': True}).json()
    assert p['approved']
    return p


def armed(client):
    p = approved(client)
    assert client.post('/api/controller/connect').status_code == 200
    assert client.post('/api/controller/load/' + p['id']).json()['verified']
    assert client.post('/api/controller/arm', json={'connected_to_tb': True, 'isolation_confirmed': True, 'permissives_confirmed': True}).json()['armed']
    return p


def wait_run(client):
    for _ in range(100):
        runs = client.get('/api/runs').json()
        if runs and runs[0]['status'] != 'RUNNING':
            return runs[0]
        time.sleep(.01)
    pytest.fail('Run did not finish')


def test_complete_sequence_and_reports(client):
    armed(client)
    assert check_and_review(client).json()['pass']
    assert client.post('/api/controller/start', json={'operator': 'Engineer'}).status_code == 200
    run = wait_run(client)
    assert run['status'] == 'PASSED'
    assert [s['command'] for s in run['steps']] == ['CLOSE', 'TRIP1', 'CLOSE', 'TRIP2']
    csv = client.get(f'/api/runs/{run["id"]}/csv').text
    assert 'SIMULATION' in csv and 'TRIP1' in csv and 'TRIP2' in csv and 'Prashil' in csv
    pdf = client.get(f'/api/runs/{run["id"]}/pdf')
    assert pdf.content.startswith(b'%PDF')
    from pypdf import PdfReader
    text = ''.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert all(s in text for s in ['SIMULATION ONLY', 'Amruthvahini', 'Prashil Dalvi', 'TRIP1', 'TRIP2'])


@pytest.mark.parametrize('change', [
    {'terminal_a': ''}, {'terminal_b': 'DEMO:1'}, {'probe': 2},
    {'open_state': None}, {'closed_state': False}, {'uncertain': True}, {'evidence': ''}])
def test_invalid_profile_cannot_approve(client, change):
    p = client.post('/api/demo').json()
    p['contacts'][0].update(change)
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    response = client.post(f'/api/profiles/{p["id"]}/approve', json={'operator': 'Engineer', 'mapping_confirmed': True})
    assert response.status_code == 422


def test_draft_cannot_load_and_checklist_required(client):
    p = client.post('/api/demo').json()
    client.post('/api/controller/connect')
    assert client.post('/api/controller/load/' + p['id']).status_code == 409
    p = approved(client)
    client.post('/api/controller/load/' + p['id'])
    assert client.post('/api/controller/arm', json={'connected_to_tb': False, 'isolation_confirmed': True, 'permissives_confirmed': True}).status_code == 409


def test_mismatch_and_retest_history(client):
    armed(client)
    client.post('/api/controller/scenario', json={'name': 'wrong_no_nc'})
    check = check_and_review(client).json()
    assert not check['pass'] and not check['rows'][0]['pass']
    assert check['rows'][0]['terminal_a'] and check['rows'][0]['probe'] == 1
    assert client.post('/api/controller/start', json={'operator': 'Engineer'}).status_code == 409
    client.post('/api/controller/scenario', json={'name': 'healthy'})
    assert check_and_review(client).json()['pass']
    client.post('/api/controller/start', json={'operator': 'Engineer'})
    run = wait_run(client)
    assert run['status'] == 'PASSED'
    assert [c['pass'] for c in run['checks']] == [False, True]


@pytest.mark.parametrize('scenario,expected', [('trip1_failure', 'FAILED'), ('trip2_failure', 'FAILED'), ('communications_loss', 'INTERRUPTED'), ('stuck_contact', 'FAILED'), ('disconnected_probe', 'FAILED')])
def test_faults_and_disarming(client, scenario, expected):
    armed(client)
    client.post('/api/controller/scenario', json={'name': scenario})
    check_and_review(client)
    assert client.post('/api/controller/start', json={'operator': 'Engineer'}).status_code == 200
    run = wait_run(client)
    assert run['status'] == expected
    state = client.get('/api/status').json()
    assert not state['armed'] and not state['outputs_active']
    assert client.post('/api/controller/start', json={'operator': 'Engineer'}).status_code == 409


def test_duplicate_start_profile_change_and_abort(client):
    p = armed(client)
    client.app.state.engine.delay = .5
    check_and_review(client)
    client.post('/api/controller/start', json={'operator': 'Engineer'})
    assert client.post('/api/controller/start', json={'operator': 'Engineer'}).status_code == 409
    assert client.put('/api/profiles/' + p['id'], json=p).status_code == 409
    assert client.post('/api/controller/scenario', json={'name': 'healthy'}).status_code == 409
    client.post('/api/controller/abort')
    assert wait_run(client)['status'] == 'ABORTED'
    assert not client.get('/api/status').json()['outputs_active']


def test_edit_invalidates_approval_and_loaded_profile(client):
    p = armed(client)
    p['contacts'][0]['label'] = 'Corrected label'
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    assert not p['approved'] and p['revision'] == 2
    state = client.get('/api/status').json()
    assert not state['armed'] and not state['profile_digest']
    assert client.post('/api/controller/load/' + p['id']).status_code == 409


def test_restart_interruption(tmp_path):
    store = Store(tmp_path)
    store.put('run', 'old', {'id': 'old', 'status': 'RUNNING'})
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/runs').json()[0]['status'] == 'INTERRUPTED'
        assert not c.get('/api/status').json()['connected']
        assert not c.get('/api/status').json()['armed']


def test_upload_validation_and_analysis_missing_key(client, monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    assert client.post('/api/documents', data={'breaker': 'B', 'drawing_revision': 'R'}, files={'file': ('bad.pdf', b'not pdf', 'application/pdf')}).status_code == 422
    from PIL import Image
    b = io.BytesIO()
    Image.new('RGB', (50, 50), 'white').save(b, format='PNG')
    p = client.post('/api/documents', data={'breaker': 'B', 'drawing_revision': 'R'}, files={'file': ('drawing.png', b.getvalue(), 'image/png')}).json()
    assert p['document_id']
    assert client.get('/api/documents/' + p['document_id'] + '/file').status_code == 200
    res = client.post('/api/profiles/' + p['id'] + '/analyze')
    assert res.status_code == 409 and 'GOOGLE_API_KEY' in res.json()['detail']


def test_upload_ai_review_and_approval(client, monkeypatch):
    from backend.models import Extraction, Contact
    async def fake_analysis(*args):
        return Extraction(contacts=[Contact(probe=1, terminal_a='TB:1', terminal_b='TB:2', open_state=False, closed_state=True, evidence='Auxiliary diagram on page 1', uncertain=False)])
    monkeypatch.setattr('backend.main.analyze_document', fake_analysis)
    from PIL import Image
    b = io.BytesIO()
    Image.new('RGB', (50, 50)).save(b, format='PNG')
    p = client.post('/api/documents', data={'breaker': 'B', 'drawing_revision': 'R'}, files={'file': ('drawing.png', b.getvalue(), 'image/png')}).json()
    p = client.post('/api/profiles/' + p['id'] + '/analyze').json()
    assert p['contacts'][0]['uncertain']  # AI cannot approve its own extraction.
    p['contacts'][0]['uncertain'] = False
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    assert client.post('/api/profiles/' + p['id'] + '/approve', json={'operator': 'Engineer', 'mapping_confirmed': True}).json()['approved']


def test_network_origin_and_physical_driver_blocked(client):
    assert client.post('/api/demo', headers={'origin': 'https://untrusted.example'}).status_code == 403
    assert client.get('/api/status').json()['hardware_enabled'] is False
    with pytest.raises(RuntimeError, match='disabled'):
        MicroLogixAdapter()


def test_disconnect_cancels_and_requires_rearm(client):
    armed(client)
    client.app.state.engine.delay = .5
    check_and_review(client)
    client.post('/api/controller/start', json={'operator': 'Engineer'})
    client.post('/api/controller/disconnect')
    assert wait_run(client)['status'] == 'ABORTED'
    state = client.get('/api/status').json()
    assert not state['connected'] and not state['armed']


def test_guided_preparation_and_capacity(client):
    p = client.post('/api/demo').json()
    cap = client.get(f'/api/profiles/{p["id"]}/capacity').json()
    assert cap['sufficient'] and cap['required_inputs'] == 6
    assert not cap['hardware_capacity_verified']
    assert client.post(f'/api/profiles/{p["id"]}/prepare', json={'operator': 'Engineer', 'mapping_confirmed': False}).status_code == 409
    assert client.post(f'/api/profiles/{p["id"]}/prepare', json={'operator': 'Engineer', 'mapping_confirmed': True}).json()['approved']
    assert client.get('/api/status').json()['armed']


def test_capacity_overflow_is_not_truncated(client):
    p = client.post('/api/demo').json()
    p['contacts'] = [{**p['contacts'][0], 'probe': i+1, 'terminal_a': f'TB:{i*2}', 'terminal_b': f'TB:{i*2+1}'} for i in range(21)]
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    cap = client.get(f'/api/profiles/{p["id"]}/capacity').json()
    assert cap['required_inputs'] == 21 and not cap['sufficient']
    assert client.post(f'/api/profiles/{p["id"]}/prepare', json={'operator': 'Engineer', 'mapping_confirmed': True}).status_code == 422


def test_real_programming_blocked_and_ip_validation(client):
    assert client.post('/api/hardware/program').status_code == 409
    assert client.post('/api/hardware/check', json={'ip': '127.0.0.1'}).status_code == 409
    assert client.post('/api/hardware/check', json={'ip': '8.8.8.8'}).status_code == 409


def test_cip_identity_parser():
    import struct
    from backend.hardware import parse_identity
    name = b'MicroLogix 1400'
    item = struct.pack('<H', 1) + bytes(16) + struct.pack('<HHHBBHI', 1, 14, 100, 21, 3, 0, 123456) + bytes([len(name)]) + name + bytes([3])
    payload = struct.pack('<HHH', 1, 12, len(item)) + item
    identity = parse_identity(payload)
    assert identity['target_family_matches']
    assert identity['revision'] == '21.3'
    with pytest.raises(ValueError):
        parse_identity(b'')


def test_component_pin_numbers_do_not_pass_as_external_tb(client):
    p = client.post('/api/demo').json()
    p['contacts'][0].update(terminal_a='1', terminal_b='2', label='-BB1 internal pins')
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    response = client.post('/api/profiles/' + p['id'] + '/approve', json={'operator':'Engineer', 'mapping_confirmed':True})
    assert response.status_code == 422
    assert any('Bare auxiliary-switch' in issue for issue in response.json()['detail'])


def test_functional_sequence_needs_second_approval(client):
    armed(client)
    check = client.request('POST', '/api/controller/check').json()
    assert check['pass']
    for endpoint in ('start', 'start-functional'):
        assert client.post('/api/controller/'+endpoint, json={'operator':'Engineer'}).status_code == 409
    assert client.post('/api/controller/review-contacts',json={'operator':'Engineer','check_timestamp':check['timestamp']}).status_code == 200
    assert client.post('/api/controller/start-functional',json={'operator':'Someone else'}).status_code == 409
    assert client.post('/api/controller/start-functional',json={'operator':'Engineer'}).status_code == 200
    run=wait_run(client)
    assert run['status']=='PASSED'
    assert run['functional_approval']['check_timestamp']==check['timestamp']


def test_rechecking_revokes_functional_approval(client):
    armed(client)
    first=client.request('POST', '/api/controller/check').json()
    client.post('/api/controller/review-contacts',json={'operator':'Engineer','check_timestamp':first['timestamp']})
    client.request('POST', '/api/controller/check')
    assert client.post('/api/controller/start-functional',json={'operator':'Engineer'}).status_code == 409
    assert client.post('/api/controller/review-contacts',json={'operator':'Engineer','check_timestamp':first['timestamp']}).status_code == 409
