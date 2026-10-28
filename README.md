# Trishul Breaker Test Lab

Windows/local browser application by Prashil Dalvi and Team Trishul, Amruthvahini College of Engg. ABB text branding identifies the project subject; this is an independent college project, not an ABB-certified product.

## Start

Requires Python 3.11+ and Node.js 20.19+.

```powershell
cd D:\ABB
.\Start-Lab.ps1 -Setup
```

Open http://127.0.0.1:8000. Subsequent starts: `.\Start-Lab.ps1`. Keep the terminal running; Ctrl+C stops the app. The launch script binds only to the local computer. Do not expose this unauthenticated college prototype to a network.

For development, run `.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` and `npm run dev` in separate terminals. Open http://127.0.0.1:5173.

## Google AI configuration

Copy `.env.example` to `.env` if it does not already exist. Set `GOOGLE_API_KEY` and optionally `GEMINI_MODEL`. Restart the backend after changes. The UI displays only whether a key exists, never its contents. Uploaded drawings are sent to Google only when **Analyze with Gemini** is selected. No key is required for the explicitly synthetic demo.

The ADK LlmAgent receives the uploaded PDF/image, requests JSON and validates the returned data against a bounded Pydantic extraction schema locally. It has no tools or PLC access. Each AI mapping is forcibly marked for human review, even when the model claims confidence. Failed or ambiguous analysis never falls back to invented contacts. Drawings are untrusted data, not instructions. Gemini 3.5 Flash was verified with a synthetic two-contact test drawing; the actual breaker drawing still needs validation.

The parser accepts JSON code fences and explicit result/extraction/profile wrappers. Null terminal/evidence strings remain blank and uncertain, not guessed. If the response is incomplete or violates the schema, the agent makes one correction attempt within the same two-minute deadline. Failed-response diagnostics are saved locally under ignored `data/analysis` (may contain drawing-derived content), never returned to the browser or printed to logs. A failed analysis preserves the uploaded drawing and previous profile.

## Workflow

The current interface uses a sequential wizard: **Start → Upload → Analyze → Review profile (approve/edit) → PLC connection → Program → Armed → Review NO/NC → Functional test → Report**. Each screen exposes only the controls for that stage. Profile approval and approval of passing contact-test results are separate decisions. The backend binds functional approval to the exact check timestamp and operator; rechecking, changing scenarios, aborting or reloading invalidates it. Both start endpoints require this approval. The simulator supports the complete flow. Physical mode stops at the programming gate until the reviewed hardware interface is implemented. Previously saved drawings/profiles can be selected without another upload.

Running operations show a modal spinner and make the background inert to mouse, touch and keyboard input. Functional testing retains the overlay for the entire run, with live sequence progress. Abort remains accessible inside the modal through an independent request path; Escape cannot dismiss it. The overlay clears when completion/failure/abort is acknowledged. Communication errors are displayed inside the active overlay.

The dashboard instructions below describe the earlier interface; equivalent operations now appear in the wizard stages rather than all at once.

The default **Physical PLC** dashboard now supports read-only Ethernet identity checks using a private LAN IPv4 address. The **Program PLC** and **Start physical test** controls remain visibly locked. The check uses EtherNet/IP ListIdentity on TCP 44818 and does not write PLC memory. Physical capacity remains unverified until the catalog number and wiring are reviewed.

In the simple dashboard, selecting a schematic automatically uploads it, analyzes it with Gemini and checks input capacity. Missing breaker/revision metadata defaults to the filename and `Unspecified`; edit metadata before approval if needed. The extractor retains up to 256 contacts and never silently trims to the simulator's 20-input capacity. Over-capacity profiles are blocked. Select **Simulator** to use **Confirm mapping & prepare simulator**, which combines approval, connection, profile acknowledgement and arming. **Start automated test** performs the initial contact check before executing trip tests. Advanced settings expose individual mapping edits and manual workflow controls. After a failed simulated trip leaves the breaker CLOSED, disconnect/reconnect to restore the simulated OPEN starting condition and re-arm before rerunning.

1. Upload a PDF (1-50 pages), JPG or PNG up to 20 MB, with breaker identity and drawing revision. Alternatively select **Try demo profile**.
2. Analyze with Gemini or add contacts manually. A source page/verification note is required. Click a contact row to navigate to its source page (PDF) or source image; the demo shows a selectable illustrative schedule. The current version navigates by page, not exact symbol bounding boxes.
3. Edit TB pairs, expected continuity in breaker OPEN/CLOSED positions and probe assignments. Probe N has a fixed mapping to simulator input N-1. Clear **Review** only after verification, save the draft, enter your name and confirm the mapping. Approve the profile. Revision snapshots and a SHA256 digest are retained.
4. Connect the simulator; load the approved profile and complete the three connection/permissive confirmations. Select **Arm simulator**.
5. Run contact checks. Fault cards identify TB pair, probe, input, expected and actual state. To simulate an operator correction choose `healthy`, then recheck; previous failed checks remain in the run history.
6. Start the sequence. It closes, checks contacts, trips via Trip 1, checks contacts, closes again and tests Trip 2. The first failure stops progression. Abort/disconnect always disarm; no automatic restart occurs.
7. Export PDF/CSV or review previous runs in Reports & history. All results say SIMULATION. Times are stored/reported in UTC; history is displayed in the browser's local timezone.

Supported fault scenarios: healthy, inverted NO/NC, disconnected first enabled probe (reads OFF), stuck first enabled contact at its OPEN value, Trip 1 failure, Trip 2 failure and communications loss. A disconnected probe already expected OFF can pass an OPEN precheck and fail only after closing. This intentionally illustrates the limits of simple digital input observations.

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q
npm run build
```

Tests cover profile validation, full sequence, independent trip failures, retest preservation, abort/disconnect, stale approval, restart interruption, upload validation, mocked AI review, origin restrictions and disabled hardware. A live Google request additionally needs valid credentials and available quota.

## Storage and interfaces

Profiles, immutable approved revision snapshots, observations and run records live in `data/lab.sqlite3`; uploaded originals are stored in `data/documents`. `.env`, `data`, build artifacts and dependencies are ignored by Git. Back up the data folder with the app stopped. Use a single backend worker; the simulator state belongs to that process.

API documentation: http://127.0.0.1:8000/docs. Controller endpoints support connect, load/verify profile, arm, contact check, sequence start, abort, disconnect and scenario injection. `/api/profiles` manages editable drafts; approval is a separate action. `/api/runs/{id}/pdf` and `/csv` export completed runs. No endpoint accepts arbitrary PLC writes, register addresses or output commands.

## Physical hardware milestone

**This version cannot program, contact or operate a physical PLC.** The MicroLogix adapter deliberately raises an error; no PLC driver is installed. The simulator uses Boolean state transitions, not real timing or coil measurement. Candidate AI command-circuit terminals are displayed as evidence for review and are not executed.

Real integration needs: a readable RSLogix ladder/data-file export of ABB2.RSS; exact controller catalog number and output groups; actual breaker drawings; verified probe wiring; control voltage and inductive switching ratings; and reviewed operating permissives/interlocks. Then implement the `Controller` protocol against an approved fixed ladder engine with a documented register map, parameter handshake, watchdog and locally enforced coil pulse bounds. Hardware must be bench-validated separately before enabling any physical adapter. A short pulse does not permit exceeding relay switching ratings.

Initial contact profiles support complementary auxiliary position contacts. Spring/gas/other permissive contacts require a reviewed future hardware model rather than guessed position expectations. The v1 readiness confirmations are simulator controls, not verified electrical safety signals. Functional trip results do not measure resistance, insulation, current signature or precision breaker timing.
