# Agent Adda — Browser Plugin (Chrome Extension MV3)

Chart intelligence side panel for TradingView, Zerodha Kite, ChartInk, and NSE India.

## Features
- 📸 One-click chart capture (screenshot via `chrome.tabs.captureVisibleTab`)
- 🧠 GPT-4o vision analysis grounded in PG-sourced key levels
- 📊 K13/K15 pattern engine integration (confirmed/forming status)
- 💬 Follow-up chat within the same capture context
- 🔒 Captured-first enforcement — no chat until a chart is captured

## Prerequisites
- Node.js ≥ 18
- Chrome ≥ 114
- Agent Adda FastAPI backend running on `localhost:8765`

## Install & Build

```bash
cd browser_plugin
npm install
npm run build
```

Built output lands in `dist/`. Load as an unpacked Chrome extension:
1. Open `chrome://extensions`
2. Enable **Developer Mode**
3. Click **Load unpacked** → select `dist/`
4. Pin the extension → click the icon → side panel opens

## Start the backend

```bash
cd /path/to/Unified-NSE-Analysis
OPENAI_API_KEY=sk-... python3 -m agent_adda.web_api.main
```

## Dev (hot-reload UI only)

```bash
npm run dev
```

Note: `chrome.*` APIs are unavailable outside the extension context. Use the Chrome Extension Vite HMR plugin for live reload during development.

## Project structure

```
browser_plugin/
├── manifest.json          # MV3 manifest
├── package.json
├── vite.config.ts
├── src/
│   ├── types.ts           # Shared TS interfaces (mirrors Pydantic schemas)
│   ├── background/        # Service worker
│   ├── content/           # Read-only content script (symbol/TF extraction)
│   └── side_panel/        # React app (main UI)
│       ├── App.tsx
│       ├── App.css
│       ├── main.tsx
│       ├── index.html
│       ├── api/           # localhost:8765 client
│       ├── store/         # chartContext hook + chrome.storage.local
│       └── components/    # Header, CaptureButton, LevelsPanel, PatternPanel, ResultCard, ChatPanel
└── public/icons/          # 16, 48, 128px PNGs (placeholder or real)
```

## Backend API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Liveness check |
| `/api/chart/levels` | GET | PG key levels for symbol/TF |
| `/api/patterns/query` | GET | K13 pattern findings |
| `/api/analysis/chart` | POST | Vision LLM analysis |
| `/api/analysis/followup` | POST | Follow-up in capture context |
