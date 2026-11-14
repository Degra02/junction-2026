# Decode the Noise — Browser Extension (Manifest V3)

Companion Chrome / Brave / Edge / Chromium extension connected to the live Decode the Noise instance (`https://the4thlover.tech` by default, configurable to `http://127.0.0.1:8080` or any self-hosted deployment).

## Capabilities

1. **Page Link Check (`kind: "url"`)**: submits the active tab URL to `POST /api/analyses` and streams all 8 pipeline stages live over SSE (`/api/analyses/{id}/events`).
2. **Highlighted Claim / Quote Check (`kind: "text"`)**: automatically detects highlighted text on the active page (or via the right-click context menu *"Check selected text with Decode the Noise"*).
3. **Reader DOM Extraction (`kind: "text"`)**: extracts visible article/feed paragraphs directly from the active tab DOM when a page requires a logged-in session or blocks server-side HTTP fetchers.
4. **Side Panel + Full Breakdown Handoff**: docks into the browser side panel for side-by-side reading and links directly to `/analyses/{id}` on the connected site for the interactive log-odds waterfall and verbatim span highlights.

## Load Unpacked

1. Open `chrome://extensions` (or `brave://extensions`, `edge://extensions`).
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` folder (or unzip `decode-the-noise-extension.zip` downloaded from `/extension` on the web app).
