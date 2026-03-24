# Riverline Assessment App

This repository contains the full interactive app version of the Riverline assessment project:

- Flask backend API
- React frontend UI
- built-in Test Lab for uploading and evaluating your own prompts and transcripts
- assignment artifacts for Parts 1, 2, and 3

## Features

- Part 1 dashboard: transcript scoring, verdicts, call detail breakdown
- Part 2 dashboard: prompt flaw analysis and before/after simulations
- Part 3 dashboard: prompt iteration pipeline reports and comparisons
- Test Lab: upload custom transcripts and prompts directly from the browser

## Local Development

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd ui
npm install
```

Set environment variable:

```env
OPENAI_API_KEY=your_key_here
```

Run backend:

```bash
python ui/app.py
```

Run frontend in dev mode:

```bash
cd ui
npm run dev
```

## Production / Deployment

This repo includes:

- `Dockerfile`
- `.dockerignore`
- `DEPLOY.md`

Flask serves the built React app from `ui/dist`, so this can be deployed as one web service on Render or Railway.

## Entrypoints

- Backend app: `ui/app.py`
- Frontend app: `ui/src/`
- Pipeline CLI: `run_pipeline.py`
