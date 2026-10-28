"""Simulation only. This module imports no network or physical PLC driver."""
from typing import Protocol
from .models import Profile

SCENARIOS = ['healthy', 'wrong_no_nc', 'disconnected_probe', 'stuck_contact', 'trip1_failure', 'trip2_failure', 'communications_loss']


class Controller(Protocol):
    def connect(self) -> None: ...
    def load_profile(self, profile: Profile) -> None: ...
    def verify_profile(self, digest: str) -> bool: ...
    def read_inputs(self) -> dict[int, bool]: ...
    def arm(self) -> None: ...
    def operate(self, command: str) -> None: ...
    def abort(self) -> None: ...
    def status(self) -> dict: ...


class MicroLogixAdapter:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('Physical PLC operation disabled pending ladder, hardware and electrical review.')


class SimulatedController:
    def __init__(self):
        self.connected = False
        self.armed = False
        self.outputs_active = False
        self.position = 'OPEN'
        self.profile: Profile | None = None
        self.scenario = 'healthy'
        self.permissives = False

    def connect(self):
        self.connected = True
        self.armed = False
        self.position = 'OPEN'

    def load_profile(self, profile):
        if not self.connected:
            raise ValueError('Connect simulator first.')
        self.profile = profile.model_copy(deep=True)
        self.armed = False

    def verify_profile(self, digest):
        return bool(self.connected and self.profile and self.profile.digest == digest)

    def arm(self):
        if not self.connected or not self.profile or not self.permissives or self.outputs_active:
            raise ValueError('Controller is not ready to arm.')
        self.armed = True

    def read_inputs(self):
        if not self.connected or not self.profile:
            raise ValueError('Controller disconnected or profile not loaded.')
        result = {}
        for c in self.profile.contacts:
            value = c.open_state if self.position == 'OPEN' else c.closed_state
            result[c.probe] = bool(value)
        first = next((c for c in self.profile.contacts if c.enabled), None)
        if first:
            if self.scenario == 'wrong_no_nc':
                result[first.probe] = not result[first.probe]
            elif self.scenario == 'disconnected_probe':
                result[first.probe] = False
            elif self.scenario == 'stuck_contact':
                result[first.probe] = bool(first.open_state)
        return result

    def operate(self, command):
        if not self.armed or not self.connected or not self.permissives:
            raise ValueError('Controller not armed.')
        if command not in ('CLOSE', 'TRIP1', 'TRIP2'):
            raise ValueError('Unknown command.')
        if self.scenario == 'communications_loss':
            self.connected = False
            self.abort()
            raise ConnectionError('Simulated communications loss. Reconnect and re-arm explicitly.')
        self.outputs_active = True
        try:
            if command == 'CLOSE':
                self.position = 'CLOSED'
            elif self.scenario != command.lower() + '_failure':
                self.position = 'OPEN'
        finally:
            self.outputs_active = False

    def abort(self):
        self.armed = False
        self.outputs_active = False

    def status(self):
        return {'mode': 'SIMULATION', 'connected': self.connected, 'armed': self.armed,
                'outputs_active': self.outputs_active, 'position': self.position,
                'permissives': self.permissives, 'scenario': self.scenario,
                'profile_digest': self.profile.digest if self.profile else None}
