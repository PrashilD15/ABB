import asyncio
import hashlib
import json
from uuid import uuid4
from .controller import SimulatedController
from .models import Profile, validation_errors
from .store import now


def digest(profile):
    body = profile.model_dump(exclude={'approved', 'approved_by', 'digest'})
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class Engine:
    def __init__(self, store, delay=0.8):
        self.store = store
        self.plc = SimulatedController()
        self.lock = asyncio.Lock()
        self.active = None
        self.task = None
        self.delay = delay
        self.last_check = None
        self.checks = []
        self.functional_approval = None

    def idle(self):
        if self.active:
            raise ValueError('Sequence running. Abort before changing configuration.')

    def invalidate(self):
        self.plc.abort()
        self.last_check = None
        self.functional_approval = None

    def approved_profile(self):
        p = self.plc.profile
        if not p or not p.approved or not self.plc.verify_profile(p.digest) or digest(p) != p.digest:
            raise ValueError('Load an approved profile and verify controller acknowledgement.')
        return p

    def evaluate(self, expected_position=None):
        p = self.approved_profile()
        position = expected_position or self.plc.position
        inputs = self.plc.read_inputs()
        rows = []
        for c in p.contacts:
            if c.enabled:
                expected = c.open_state if position == 'OPEN' else c.closed_state
                rows.append({**c.model_dump(), 'input': c.probe - 1, 'expected': expected,
                             'actual': inputs[c.probe], 'pass': inputs[c.probe] == expected})
        return {'timestamp': now(), 'position': position, 'rows': rows,
                'pass': bool(rows) and all(r['pass'] for r in rows), 'profile_digest': p.digest,
                'scenario': self.plc.scenario, 'mode': 'SIMULATION'}

    def check(self):
        self.idle()
        if not self.plc.armed:
            raise ValueError('Arm before checking contacts.')
        result = self.evaluate()
        self.last_check = result
        self.functional_approval = None
        self.checks.append(result)
        self.store.put('check', str(uuid4()), result)
        return result

    def approve_functional(self, operator, check_timestamp):
        self.idle()
        self.approved_profile()
        if not operator.strip() or not self.plc.armed or not self.last_check or not self.last_check['pass']:
            raise ValueError('Pass the contact check and enter an operator before approving functional tests.')
        if self.last_check['timestamp'] != check_timestamp or not self.evaluate()['pass']:
            raise ValueError('Contact results changed. Recheck and review the latest results.')
        self.functional_approval = {'operator': operator.strip(), 'check_timestamp': check_timestamp}
        self.store.event('functional_approval', self.functional_approval)
        return self.functional_approval

    def start(self, operator, require_review=True):
        self.idle()
        p = self.approved_profile()
        if not operator.strip():
            raise ValueError('Enter operator name.')
        if not self.plc.armed or not self.plc.permissives or not self.last_check or not self.last_check['pass']:
            raise ValueError('Arm and pass the initial contact checks first.')
        if require_review and (not self.functional_approval or self.functional_approval['check_timestamp'] != self.last_check['timestamp']):
            raise ValueError('Review and approve the latest passing NO/NC results before functional tests.')
        if require_review and self.functional_approval['operator'] != operator.strip():
            raise ValueError('The operator starting functional tests must match the contact-results approver.')
        if self.plc.position != 'OPEN' or self.last_check['profile_digest'] != p.digest or not self.evaluate()['pass']:
            raise ValueError('Starting position must be OPEN with a matching passing contact check.')
        run = {'id': str(uuid4()), 'mode': 'SIMULATION', 'status': 'RUNNING', 'started': now(),
               'finished': None, 'operator': operator.strip(), 'profile': p.model_dump(),
               'checks': list(self.checks), 'steps': [], 'reason': '', 'functional_approval': self.functional_approval}
        self.active = run
        self.functional_approval = None
        self.store.put('run', run['id'], run)
        self.task = asyncio.create_task(self.execute(run))
        return run

    async def execute(self, run):
        try:
            for command, expected in [('CLOSE', 'CLOSED'), ('TRIP1', 'OPEN'), ('CLOSE', 'CLOSED'), ('TRIP2', 'OPEN')]:
                await asyncio.sleep(self.delay)
                async with self.lock:
                    if self.active is not run:
                        return
                    self.plc.operate(command)
                    check = self.evaluate(expected)
                    passed = self.plc.position == expected and check['pass']
                    run['steps'].append({'command': command, 'expected_position': expected,
                                         'actual_position': self.plc.position, 'pass': passed,
                                         'timestamp': now(), 'contacts': check})
                    self.store.put('run', run['id'], run)
                    if not passed:
                        run['status'] = 'FAILED'
                        run['reason'] = f'{command}: position or contact verification failed. Correct and rerun.'
                        break
            else:
                run['status'] = 'PASSED'
        except asyncio.CancelledError:
            run['status'] = 'ABORTED'
            run['reason'] = 'Operator aborted or application stopped.'
        except Exception as exc:
            run['status'] = 'INTERRUPTED'
            run['reason'] = str(exc)
        finally:
            self.plc.abort()
            self.last_check = None
            run['finished'] = now()
            self.store.put('run', run['id'], run)
            if self.active is run:
                self.active = None

    def abort(self):
        self.plc.abort()
        self.last_check = None
        self.functional_approval = None
        if self.task and not self.task.done():
            self.task.cancel()

    def validate(self, p: Profile):
        count = self.store.get('document', p.document_id)['pages'] if p.document_id else None
        return validation_errors(p, count)
