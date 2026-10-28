# Portable project data

This is a deliberately published snapshot of the project's uploaded drawings, profiles, test history and analysis diagnostics. It contains no API key. The live `data/` folder remains ignored so future tests do not automatically publish new records.

On another Windows computer:

```powershell
git clone https://github.com/PrashilD15/ABB.git
cd ABB
.\Restore-ProjectData.ps1
Copy-Item .env.example .env
# Edit .env and enter your Google API key locally.
.\Start-Lab.ps1 -Setup
```

Open http://127.0.0.1:8000. Python 3.11+ and Node.js 20.19+ are required. The setup script reinstalls dependencies and builds the frontend; machine-specific `.venv`, `node_modules`, caches and build output are not transferred through Git.

`reference-materials/` contains the supplied ABB2.RSS project and available reference photos/screenshots. It is reference material, not a verified physical PLC integration. Real programming remains disabled.

To deliberately update the public snapshot later, run `python scripts/export_project_data.py`, review its contents, then commit `project-backup/data`. Drawings and diagnostics can contain project-specific information; review future additions before publishing.
