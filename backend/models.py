from typing import Literal
from pydantic import BaseModel, Field


class Contact(BaseModel):
    terminal_a: str = Field(default='', max_length=80)
    terminal_b: str = Field(default='', max_length=80)
    label: str = Field(default='', max_length=120)
    probe: int = Field(ge=1, le=256)
    enabled: bool = True
    open_state: bool | None = None
    closed_state: bool | None = None
    page: int = Field(default=1, ge=1)
    evidence: str = Field(default='', max_length=1000)
    uncertain: bool = True


class CommandCircuit(BaseModel):
    function: Literal['CLOSE', 'TRIP1', 'TRIP2']
    terminal_a: str = Field(default='', max_length=80)
    terminal_b: str = Field(default='', max_length=80)
    page: int = Field(default=1, ge=1)
    evidence: str = Field(default='', max_length=1000)


class Extraction(BaseModel):
    contacts: list[Contact] = Field(default_factory=list, max_length=256)
    commands: list[CommandCircuit] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=50)


class Profile(Extraction):
    id: str
    revision: int = 1
    breaker: str = Field(min_length=1, max_length=120)
    drawing_revision: str = Field(min_length=1, max_length=80)
    document_id: str | None = None
    source: str = 'manual'
    approved: bool = False
    approved_by: str = ''
    digest: str = ''


def validation_errors(profile: Profile, page_count: int | None = None) -> list[str]:
    errors = []
    contacts = [c for c in profile.contacts if c.enabled]
    if not contacts:
        errors.append('Enable at least one verified contact.')
    if len(contacts) > 20:
        errors.append(f'Insufficient simulator capacity: {len(contacts)} inputs required, 20 available. No automatic truncation is permitted.')
    probes, terminals = set(), set()
    for c in contacts:
        prefix = f'Probe {c.probe}'
        if c.probe > 20:
            errors.append(f'{prefix}: exceeds the 20 verified simulator inputs.')
        pair = tuple(sorted([c.terminal_a.strip().upper(), c.terminal_b.strip().upper()]))
        if not all(pair) or pair[0] == pair[1]:
            errors.append(f'{prefix}: enter two distinct TB terminals.')
        elif not all(any(ch.isalpha() for ch in terminal) for terminal in pair):
            errors.append(f'{prefix}: include the external TB designation (for example XDB:124). Bare auxiliary-switch pin numbers are not verified TB connections.')
        if c.probe in probes:
            errors.append(f'{prefix}: duplicate probe assignment.')
        if pair in terminals:
            errors.append(f'{prefix}: duplicate terminal pair.')
        probes.add(c.probe)
        terminals.add(pair)
        if c.open_state is None or c.closed_state is None:
            errors.append(f'{prefix}: OPEN and CLOSED expectations are required.')
        elif c.open_state == c.closed_state:
            errors.append(f'{prefix}: auxiliary position contact must change between OPEN and CLOSED.')
        if c.uncertain or not c.evidence.strip():
            errors.append(f'{prefix}: resolve uncertainty and record drawing evidence.')
        if page_count and c.page > page_count:
            errors.append(f'{prefix}: source page does not exist.')
    return errors
