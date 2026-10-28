import asyncio
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .models import Profile, Contact
from .store import Store
from .engine import Engine, digest
from .controller import SCENARIOS
from .analysis import analyze_document, AnalysisValidationError
from .reports import csv_report, pdf_report
from .hardware import check_identity

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


class Approval(BaseModel):
    operator: str = Field(min_length=1, max_length=120)
    mapping_confirmed: bool = False


class Readiness(BaseModel):
    connected_to_tb: bool
    isolation_confirmed: bool
    permissives_confirmed: bool


class Scenario(BaseModel):
    name: str


class HardwareTarget(BaseModel):
    ip: str = Field(min_length=7, max_length=15)


class FunctionalApproval(BaseModel):
    operator: str = Field(min_length=1, max_length=120)
    check_timestamp: str


def create_app(data_dir=None, delay=.8):
    store = Store(Path(data_dir or os.getenv('TRISHUL_DATA_DIR', ROOT / 'data')))
    engine = Engine(store, delay)
    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.abort()
        if engine.task:
            await asyncio.gather(engine.task, return_exceptions=True)

    app = FastAPI(title='Trishul Breaker Test Lab', lifespan=lifespan)
    app.state.engine, app.state.store = engine, store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8000', 'http://localhost:8000', 'http://127.0.0.1:5173', 'http://localhost:5173'):
            return JSONResponse({'detail': 'Local application origins only.'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'Record not found.'}, status_code=404)

    @app.get('/api/status')
    async def status():
        return {**engine.plc.status(), 'active_run': engine.active, 'last_check': engine.last_check,
                'ai_configured': bool(os.getenv('GOOGLE_API_KEY')), 'ai_model': os.getenv('GEMINI_MODEL', 'gemini-3.5-flash'), 'scenarios': SCENARIOS,
                'hardware_enabled': False}

    @app.post('/api/hardware/check')
    async def hardware_check(target: HardwareTarget):
        return await check_identity(target.ip)

    @app.get('/.well-known/appspecific/com.chrome.devtools.json')
    async def browser_devtools_probe():
        # Chrome probes this optional development endpoint automatically.
        return Response(status_code=204)

    @app.get('/favicon.ico')
    async def favicon():
        return FileResponse(ROOT / 'public' / 'favicon.svg', media_type='image/svg+xml')

    @app.post('/api/hardware/program')
    async def hardware_program():
        raise HTTPException(409, 'Physical programming is disabled. Supply a readable RSLogix ladder/data-file export, verified register map and exact controller/output wiring first. No PLC writes were sent.')

    @app.post('/api/documents')
    async def upload(file: UploadFile = File(...), breaker: str = Form(...), drawing_revision: str = Form(...)):
        data = await file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, 'Maximum document size is 20 MB.')
        mime = file.content_type
        try:
            if mime == 'application/pdf' and data.startswith(b'%PDF'):
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                if reader.is_encrypted:
                    raise ValueError('Encrypted PDF.')
                pages = len(reader.pages)
                if not 1 <= pages <= 50:
                    raise ValueError('PDF must contain 1 to 50 pages.')
                ext = '.pdf'
            elif mime in ('image/jpeg', 'image/png'):
                from PIL import Image
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValueError('Image exceeds 40 megapixels.')
                    if image.format != ('JPEG' if mime == 'image/jpeg' else 'PNG'):
                        raise ValueError('Image format mismatch.')
                    image.verify()
                pages, ext = 1, '.jpg' if mime == 'image/jpeg' else '.png'
            else:
                raise ValueError('Unsupported file.')
        except Exception:
            raise HTTPException(422, 'Use a valid unencrypted PDF (1-50 pages), JPG or PNG image (up to 40 MP).')
        id = str(uuid4())
        profile = Profile(id=str(uuid4()), breaker=breaker.strip(), drawing_revision=drawing_revision.strip(), document_id=id)
        doc = {'id': id, 'name': Path(file.filename or 'schematic').name, 'mime': mime, 'pages': pages, 'ext': ext}
        (store.root / 'documents' / (id + ext)).write_bytes(data)
        store.put('document', id, doc)
        store.put('profile', profile.id, profile.model_dump())
        return profile

    @app.get('/api/documents/{id}/file')
    async def document(id: str):
        doc = store.get('document', id)
        return FileResponse(store.root / 'documents' / (doc['id'] + doc['ext']), media_type=doc['mime'], headers={'X-Content-Type-Options': 'nosniff'})

    @app.get('/api/profiles')
    async def profiles():
        return store.list('profile')

    @app.get('/api/profiles/{id}/capacity')
    async def capacity(id: str):
        p = Profile.model_validate(store.get('profile', id))
        enabled = [c for c in p.contacts if c.enabled]
        candidate = p.model_copy(deep=True)
        for c in candidate.contacts:
            c.uncertain = False
        return {'mode': 'SIMULATION', 'available_inputs': 20, 'required_inputs': len(enabled),
                'spare_inputs': max(0, 20-len(enabled)),
                'sufficient': 0 < len(enabled) <= 20 and all(c.probe <= 20 for c in enabled),
                'blocking_errors': engine.validate(candidate),
                'hardware_capacity_verified': False,
                'note': 'Simulation input capacity only. Physical model, output groups, isolation and electrical ratings remain unverified.'}

    @app.post('/api/profiles/{id}/prepare')
    async def prepare(id: str, approval: Approval):
        async with engine.lock:
            engine.idle()
            p = Profile.model_validate(store.get('profile', id))
            if not approval.mapping_confirmed or not approval.operator.strip():
                raise ValueError('Confirm the reviewed drawing-to-spine mapping before preparing.')
            # One explicit human mapping confirmation replaces per-row review clicks.
            # Missing/contradictory states, evidence and capacity still block preparation.
            for c in p.contacts:
                c.uncertain = False
            errors = engine.validate(p)
            if errors:
                raise HTTPException(422, errors)
            if not p.approved:
                p.approved, p.approved_by = True, approval.operator.strip()
                p.digest = digest(p)
                store.put('profile', id, p.model_dump())
                store.put('revision', f'{id}:{p.revision}', p.model_dump())
                store.event('approved', {'profile': id, 'revision': p.revision, 'operator': p.approved_by, 'flow': 'guided'})
            engine.invalidate()
            engine.plc.connect()
            engine.plc.load_profile(p)
            if not engine.plc.verify_profile(p.digest):
                raise ValueError('Profile acknowledgement mismatch.')
            engine.plc.permissives = True  # Simulator only; never an electrical safety signal.
            engine.plc.arm()
            engine.checks = []
            return p

    @app.post('/api/demo')
    async def demo():
        profile = Profile(id=str(uuid4()), breaker='DEMO - auxiliary contact bench', drawing_revision='DEMO-01', source='demo',
                          warnings=['Synthetic demonstration only. These terminals are not an ABB wiring instruction.'],
                          contacts=[Contact(probe=i + 1, terminal_a=f'DEMO:{i*2+1}', terminal_b=f'DEMO:{i*2+2}',
                                            label=f'Auxiliary {i+1}', open_state=bool(i % 2), closed_state=not bool(i % 2),
                                            uncertain=False, evidence='Synthetic demo contact - confirm for simulation only.') for i in range(6)])
        store.put('profile', profile.id, profile.model_dump())
        return profile

    @app.post('/api/profiles/{id}/analyze')
    async def analyze(id: str):
        async with engine.lock:
            engine.idle()
            p = Profile.model_validate(store.get('profile', id))
            if p.approved:
                raise ValueError('Create a new revision before reanalysis.')
            if not p.document_id:
                raise ValueError('Upload a schematic first.')
            doc = store.get('document', p.document_id)
            revision = p.revision
        try:
            result = await analyze_document(store.root / 'documents' / (doc['id'] + doc['ext']), doc['mime'])
        except AnalysisValidationError as exc:
            store.event('analysis_failed', {'profile': id, 'kind': 'validation', 'message': str(exc)})
            raise HTTPException(502, str(exc) + ' Your drawing and previous profile remain saved; no PLC command was sent.')
        except ValueError as exc:
            if not os.getenv('GOOGLE_API_KEY'):
                raise exc
            raise HTTPException(502, 'Google returned an unsupported response. Your drawing and previous profile remain saved. Retry analysis; no PLC command was sent.')
        except TimeoutError:
            store.event('analysis_failed', {'profile': id, 'kind': 'timeout'})
            raise HTTPException(504, 'Google analysis exceeded two minutes. Your drawing is saved; retry analysis. No profile was approved and no PLC command was sent.')
        except Exception as exc:
            code = getattr(exc, 'code', None)
            store.event('analysis_failed', {'profile': id, 'kind': 'provider', 'code': code if isinstance(code, int) else None, 'exception': type(exc).__name__})
            hint = ' Google is busy; retry shortly.' if code in (429, 503) else ' Check backend model/credentials and retry.'
            provider = f' (provider HTTP {code})' if isinstance(code, int) else ''
            raise HTTPException(502, f'Google schematic analysis failed{provider}.{hint} Your drawing remains saved. No profile was approved and no PLC command was sent.')
        async with engine.lock:
            engine.idle()
            current = Profile.model_validate(store.get('profile', id))
            if current.revision != revision or current.approved:
                raise ValueError('Profile changed during analysis. Retry on the current draft.')
            p.contacts, p.commands, p.warnings = result.contacts, result.commands, result.warnings
            p.source = 'google-adk'
            p.revision += 1
            for c in p.contacts:
                c.uncertain = True  # Every AI mapping requires explicit human verification.
            store.put('profile', id, p.model_dump())
            return p

    @app.put('/api/profiles/{id}')
    async def save(id: str, incoming: Profile):
        async with engine.lock:
            engine.idle()
            old = Profile.model_validate(store.get('profile', id))
            if incoming.id != id or incoming.revision != old.revision:
                raise ValueError('Stale profile. Reload the saved revision.')
            # Source identity cannot be replaced through an editable profile payload.
            incoming.document_id, incoming.source = old.document_id, old.source
            incoming.revision += 1
            incoming.approved, incoming.approved_by, incoming.digest = False, '', ''
            store.put('profile', id, incoming.model_dump())
            if engine.plc.profile and engine.plc.profile.id == id:
                engine.invalidate()
                engine.plc.profile = None
            return incoming

    @app.post('/api/profiles/{id}/approve')
    async def approve(id: str, approval: Approval):
        async with engine.lock:
            engine.idle()
            p = Profile.model_validate(store.get('profile', id))
            errors = engine.validate(p)
            if not approval.mapping_confirmed or not approval.operator.strip():
                errors.append('Named operator must confirm the drawing-to-spine mapping.')
            if errors:
                raise HTTPException(422, errors)
            if p.approved:
                raise ValueError('Already approved. Edit and save to create a new revision.')
            p.approved, p.approved_by = True, approval.operator.strip()
            p.digest = digest(p)
            store.put('profile', id, p.model_dump())
            store.put('revision', f'{id}:{p.revision}', p.model_dump())
            store.event('approved', {'profile': id, 'revision': p.revision, 'operator': p.approved_by})
            return p

    @app.post('/api/controller/connect')
    async def connect():
        async with engine.lock:
            engine.idle()
            engine.invalidate()
            engine.plc.connect()
            engine.plc.permissives = False
            engine.checks = []
            return engine.plc.status()

    @app.post('/api/controller/load/{id}')
    async def load(id: str):
        async with engine.lock:
            engine.idle()
            p = Profile.model_validate(store.get('profile', id))
            if not p.approved or engine.validate(p) or digest(p) != p.digest:
                raise ValueError('Profile is not approved and valid.')
            engine.invalidate()
            engine.plc.permissives = False
            engine.plc.load_profile(p)
            engine.checks = []
            return {'verified': engine.plc.verify_profile(p.digest), **engine.plc.status()}

    @app.post('/api/controller/arm')
    async def arm(readiness: Readiness):
        async with engine.lock:
            engine.idle()
            engine.approved_profile()
            if not all([readiness.connected_to_tb, readiness.isolation_confirmed, readiness.permissives_confirmed]):
                raise ValueError('Complete all connection and permissive confirmations.')
            engine.plc.permissives = True
            engine.plc.arm()
            return engine.plc.status()

    @app.post('/api/controller/scenario')
    async def scenario(value: Scenario):
        async with engine.lock:
            engine.idle()
            if value.name not in SCENARIOS:
                raise ValueError('Unknown scenario.')
            engine.plc.scenario = value.name
            engine.last_check = None
            engine.functional_approval = None
            return engine.plc.status()

    @app.post('/api/controller/check')
    async def check():
        async with engine.lock:
            return engine.check()

    @app.post('/api/controller/start')
    async def start(approval: Approval):
        async with engine.lock:
            return engine.start(approval.operator)

    @app.post('/api/controller/review-contacts')
    async def review_contacts(approval: FunctionalApproval):
        async with engine.lock:
            return engine.approve_functional(approval.operator, approval.check_timestamp)

    @app.post('/api/controller/start-functional')
    async def start_functional(approval: Approval):
        async with engine.lock:
            return engine.start(approval.operator, require_review=True)

    @app.post('/api/controller/abort')
    async def abort():
        async with engine.lock:
            engine.abort()
            return engine.plc.status()

    @app.post('/api/controller/disconnect')
    async def disconnect():
        async with engine.lock:
            engine.abort()
            engine.plc.connected = False
            engine.plc.permissives = False
            return engine.plc.status()

    @app.get('/api/runs')
    async def runs():
        return store.list('run')

    @app.get('/api/runs/{id}/{format}')
    async def report(id: str, format: str):
        run = store.get('run', id)
        if run['status'] == 'RUNNING':
            raise ValueError('Wait for the run to finish or abort before exporting.')
        if format == 'csv':
            return Response(csv_report(run), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="simulation-{id}.csv"'})
        if format == 'pdf':
            return Response(pdf_report(run), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="simulation-{id}.pdf"'})
        raise HTTPException(404, 'Use pdf or csv.')

    if (ROOT / 'dist').exists():
        app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='ui')
    return app


app = create_app()
