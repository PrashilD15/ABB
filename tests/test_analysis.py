import json
import pytest
from backend.analysis import parse_extraction, validation_summary


def valid():
    return {'contacts':[{'probe':1,'terminal_a':'XDB:124','terminal_b':'XDB:125','open_state':False,'closed_state':True,'evidence':'Page 3, terminals XDB124-125'}]}


@pytest.mark.parametrize('wrapper', ['plain','fenced','extraction','result','profile'])
def test_json_presentation_variants(wrapper):
    body = valid()
    text = json.dumps(body if wrapper in ('plain','fenced') else {wrapper:body})
    if wrapper == 'fenced':
        text = '```json\n' + text + '\n```'
    assert parse_extraction(text).contacts[0].terminal_a == 'XDB:124'


def test_missing_terminal_not_invented():
    body = valid()
    body['contacts'][0].update(terminal_a=None, evidence=None, uncertain=False)
    c = parse_extraction(json.dumps(body)).contacts[0]
    assert c.terminal_a == '' and c.evidence == '' and c.uncertain


@pytest.mark.parametrize('text', ['{}','[]','{"contacts": []}', '{"contacts": [', '{"contacts":null}'])
def test_empty_wrong_shape_or_truncated_responses_rejected(text):
    with pytest.raises(ValueError):
        parse_extraction(text)


def test_unreadable_drawing_requires_explanation():
    assert parse_extraction('{"contacts":[],"warnings":["No readable schematic found"]}').warnings


def test_bad_state_is_not_guessed_and_summary_does_not_echo_evidence():
    body=valid()
    body['contacts'][0].update(open_state='normally open', evidence='PRIVATE DRAWING CONTENT')
    with pytest.raises(ValueError) as caught:
        parse_extraction(json.dumps(body))
    summary=validation_summary(caught.value)
    assert 'open_state' in summary and 'PRIVATE DRAWING CONTENT' not in summary


def test_automatic_correction_without_network(tmp_path, monkeypatch):
    import asyncio
    import backend.analysis as analysis
    monkeypatch.setenv('GOOGLE_API_KEY','local-test-placeholder')
    calls=[]
    async def responses(runner, session_id, message):
        calls.append(message)
        return ('{"contacts": [', 'MAX_TOKENS') if len(calls)==1 else (json.dumps(valid()), 'STOP')
    monkeypatch.setattr(analysis,'read_response',responses)
    source=tmp_path/'documents'/'test.png'
    source.parent.mkdir()
    source.write_bytes(b'synthetic test, not transmitted')
    result=asyncio.run(analysis.analyze_document(source,'image/png'))
    assert len(calls)==2 and result.contacts[0].terminal_a=='XDB:124'
    diagnostic=json.loads(next((tmp_path/'analysis').glob('*.json')).read_text())
    assert diagnostic['attempts'][0]['finish_reason']=='MAX_TOKENS'


def test_failed_correction_stops_after_two_attempts(tmp_path, monkeypatch):
    import asyncio
    import backend.analysis as analysis
    monkeypatch.setenv('GOOGLE_API_KEY','local-test-placeholder')
    calls=[]
    async def responses(*args):
        calls.append(1)
        return '{}','STOP'
    monkeypatch.setattr(analysis,'read_response',responses)
    source=tmp_path/'documents'/'test.png'
    source.parent.mkdir()
    source.write_bytes(b'synthetic test, not transmitted')
    with pytest.raises(analysis.AnalysisValidationError,match='automatic correction'):
        asyncio.run(analysis.analyze_document(source,'image/png'))
    assert len(calls)==2


def test_transient_provider_failure_retried_once(monkeypatch):
    import asyncio
    import backend.analysis as analysis
    calls=[]
    class ProviderBusy(Exception):
        code=503
    async def responses(*args):
        calls.append(1)
        if len(calls)==1:
            raise ProviderBusy()
        return json.dumps(valid()),'STOP'
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(analysis,'read_response',responses)
    monkeypatch.setattr(analysis.asyncio,'sleep',no_sleep)
    text,reason=asyncio.run(analysis.read_with_transient_retry(None,'test',None))
    assert len(calls)==2 and reason=='STOP' and parse_extraction(text).contacts
