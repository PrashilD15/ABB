"""Generate isolated QA outputs and optionally test live ADK with a synthetic drawing."""
import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.main import create_app
from backend.analysis import analyze_document

out = Path('tmp/qa')
out.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (1400, 1000), 'white')
draw = ImageDraw.Draw(image)
draw.text((80, 50), 'SYNTHETIC TEST SCHEMATIC - NOT FOR PHYSICAL WIRING', fill='black', font_size=32)
draw.text((80, 120), 'Breaker reference position: OPEN. Contacts are auxiliary position contacts.', fill='black', font_size=24)
for i, (a, b, opened, closed) in enumerate([('TB:1', 'TB:2', 'OPEN', 'CLOSED'), ('TB:3', 'TB:4', 'CLOSED', 'OPEN')]):
    y = 270 + i * 280
    draw.text((80, y), f'Auxiliary {i+1}: {a} to {b}', fill='black', font_size=28)
    draw.line((120, y+80, 500, y+80), fill='black', width=4)
    draw.line((500, y+60, 500, y+100), fill='black', width=4)
    draw.line((550, y+60, 550, y+100), fill='black', width=4)
    if i:
        draw.line((480, y+110, 570, y+50), fill='black', width=4)
    draw.line((550, y+80, 900, y+80), fill='black', width=4)
    draw.text((80, y+145), f'Breaker OPEN: contact {opened}. Breaker CLOSED: contact {closed}.', fill='black', font_size=24)
image.save(out / 'synthetic-schematic.png')

if '--live-ai' in sys.argv:
    async def live():
        try:
            result = await analyze_document(out / 'synthetic-schematic.png', 'image/png')
            print('Live ADK response validated:', len(result.contacts), 'contacts')
            (out / 'live-extraction.json').write_text(result.model_dump_json(indent=2), encoding='utf-8')
        except Exception as exc:
            # Never output exception text from credential-bearing provider requests.
            print('Live ADK check failed:', type(exc).__name__)
            if hasattr(exc, 'code'):
                print('Provider status:', exc.code)
            if hasattr(exc, 'message'):
                import os
                message = str(exc.message).replace(os.getenv('GOOGLE_API_KEY', 'no-key-configured'), '[REDACTED]')
                print('Provider diagnostic:', message[:1000])
    asyncio.run(live())

with TemporaryDirectory() as temp, TestClient(create_app(temp, delay=.001)) as client:
    import time
    p = client.post('/api/demo').json()
    # Long strings exercise wrapping in exported tables.
    p['contacts'][0]['terminal_a'] = 'TB-LONG-DESIGNATION-123456789'
    p = client.put('/api/profiles/' + p['id'], json=p).json()
    client.post('/api/profiles/' + p['id'] + '/approve', json={'operator': 'Prashil Dalvi - QA simulation', 'mapping_confirmed': True})
    client.post('/api/controller/connect')
    client.post('/api/controller/load/' + p['id'])
    client.post('/api/controller/arm', json={'connected_to_tb': True, 'isolation_confirmed': True, 'permissives_confirmed': True})
    client.post('/api/controller/scenario', json={'name': 'wrong_no_nc'})
    client.post('/api/controller/check')
    client.post('/api/controller/scenario', json={'name': 'healthy'})
    client.post('/api/controller/check')
    check = client.get('/api/status').json()['last_check']
    client.post('/api/controller/review-contacts', json={'operator': 'Prashil Dalvi - QA simulation', 'check_timestamp': check['timestamp']})
    run = client.post('/api/controller/start', json={'operator': 'Prashil Dalvi - QA simulation'}).json()
    for _ in range(100):
        if client.get('/api/runs').json()[0]['status'] != 'RUNNING':
            break
        time.sleep(.01)
    (out / 'simulation-report.pdf').write_bytes(client.get(f'/api/runs/{run["id"]}/pdf').content)
    print('QA report saved to tmp/qa/simulation-report.pdf')
