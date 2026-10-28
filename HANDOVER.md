# Project handover

The local app runs at http://127.0.0.1:8000. Restart with `Start-Lab.ps1`; use `-Setup` to install dependencies/build. Development and architecture details are in README.md.

Implemented: React/TypeScript mobile/tablet dashboard, FastAPI backend, Google ADK extraction, automatic upload/analyze/capacity workflow, editable evidence-backed profiles, one-confirmation simulator preparation, contact-fault display, deterministic simulated trip sequence, PDF/CSV exports, SQLite history and requested branding. Default physical mode offers read-only EtherNet/IP identity checks. No physical PLC writes or driver are present.

The active interface is now a ten-stage guided sequence, with separate profile approval and approval of passing NO/NC results before functional testing. Both functional start endpoints enforce the latter approval on the backend, bound to the latest check timestamp and operator. Forty-five automated tests and a browser simulator walkthrough cover the current flow. Google transient provider errors get one bounded retry; invalid JSON gets one schema correction attempt. Failed-response diagnostics stay under ignored data/analysis. Uploaded originals and drafts are retained on failure.

Verified: frontend production build; 26 automated tests; installed dependency consistency; browser approval/arming/check/start workflow; PDF text and all three rendered sample pages. Live Google ADK analysis with the supplied server-side credential and Gemini 3.5 Flash successfully extracted two contacts from a synthetic test drawing and passed local schema validation. The selected model is stored in the ignored .env. No actual breaker schematic or real PLC IP/device response has been tested.

Awaiting from the team: PLC private Ethernet IP, exact catalog label, readable RSLogix ladder and data-file export of ABB2.RSS, actual breaker drawings, verified probe-to-input wiring and command-circuit voltages/output ratings. These are required before implementing the one-time PLC engine interface. Physical model capacity and relay suitability cannot be inferred merely from successful Ethernet identification.

Physical programming/test buttons intentionally remain locked. A future programming action must check identity, verify the approved firmware/register interface, load bounded profile parameters, read back acknowledgement and verify operating permissives. Do not simply replace the blocked endpoint with arbitrary memory/output writes.

The Google key is in the local ignored `.env`, never browser code. Data and uploaded drawings stay in the ignored `data` folder; drawing analysis sends the selected document to Google. No production hosting has been created.
