"""Export a consistent, credential-free snapshot for another computer."""
from pathlib import Path
import shutil
import sqlite3

root = Path(__file__).resolve().parents[1]
source = root / 'data'
destination = root / 'project-backup' / 'data'
destination.mkdir(parents=True, exist_ok=True)
if (source / 'lab.sqlite3').exists():
    with sqlite3.connect(source / 'lab.sqlite3') as original, sqlite3.connect(destination / 'lab.sqlite3') as snapshot:
        original.backup(snapshot)
for directory in ('documents', 'analysis'):
    if (source / directory).exists():
        shutil.copytree(source / directory, destination / directory, dirs_exist_ok=True)
print('Project data snapshot exported to project-backup/data. No .env or credentials copied.')
