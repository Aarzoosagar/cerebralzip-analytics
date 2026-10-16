# Production deployment

This repository deploys the FastAPI backend as a Docker Web Service on Render and
the React/Vite frontend as a Vercel project. SQLite and the downloaded Olist dataset
must be stored on Render's persistent disk.

## 1. Push the repository to GitHub

If this local copy is not already connected to the intended GitHub repository, create
or choose that repository first. From the repository root, review the files and push
the deployment changes:

```powershell
git status
git remote -v
git add Dockerfile DEPLOYMENT.md
git commit -m "Prepare Render and Vercel deployment"
git push origin <branch-name>
```

Do not add `.env`, API keys, downloaded dataset files, or generated SQLite databases.
If the Git remote is already configured, keep it; otherwise add the correct GitHub
remote before pushing:

```powershell
git remote add origin <github-repository-url>
```

## 2. Create the Render backend

1. In Render, choose **New + → Web Service** and connect the GitHub repository.
2. Choose **Docker** as the runtime.
3. Use the repository root as the service root directory (leave it blank if Render
   indicates the repository root by default).
4. Set the Dockerfile path to `Dockerfile` and the Docker build context to the
   repository root.
5. Leave the Docker start command blank so the Dockerfile's command is used. It
   starts `app.main:app`, binds to `0.0.0.0`, and uses Render's `PORT` variable with
   `8000` as a local fallback.
6. Set the health check path to `/health`.
7. Use one service instance with a persistent disk as described below. SQLite is
   file-based and this configuration is not intended for multiple instances.

The Docker build installs dependencies declared in `pyproject.toml` and does not
build the frontend; Vercel builds the frontend separately.

### Render persistent disk

In the Render service's **Disks** settings, create a persistent disk and set its
mount path to:

```text
/var/data
```

Set both database and dataset directory variables to paths on this disk:

| Variable | Value |
|---|---|
| `DATABASE_PATH` | `/var/data/olist.db` |
| `DATA_DIR` | `/var/data` |

The application checks for a complete initialized database at startup. If one is not
present, it downloads the archive and loads the CSV data into SQLite on the disk.
This first startup can take several minutes. Later restarts reuse an initialized
database. Do not remove or replace the disk if its SQLite dashboard data must be
preserved.

**Data safety:** the CSV loader drops and recreates analytical tables when invoked.
The normal startup path skips loading when the database is complete, but a missing,
incomplete, or invalid database can enter the load path. Back up the persistent disk
before any recovery or manual load operation. This deployment configuration does
not alter the database schema or run the loader as a deployment step.

## 3. Configure Render environment variables

Add these in the Render service's **Environment** settings. Render provides `PORT`;
do not set it manually. The process binds to that value automatically.

| Variable | Production value / default | Notes |
|---|---|---|
| `DATABASE_PATH` | `/var/data/olist.db` | Required for persistence; this exact name is read by the SQLite connection code. |
| `DATA_DIR` | `/var/data` | Required to persist the downloaded dataset and CSVs on the same disk. |
| `FRONTEND_ORIGIN` | `https://cerebralzip-analytics.vercel.app` | Set to the exact browser origin, with no path or trailing slash. |
| `AGENT_MODE` | `llm` | Selects the Groq-backed agent. `fallback` selects deterministic analytics without Groq. |
| `GROQ_API_KEY` | `<your-groq-api-key>` | Secret; add only to Render, never to Vercel or source control. |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Existing application default. |
| `LLM_TIMEOUT_SECONDS` | `20` | Existing application default. |
| `DATASET_URL` | `https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce?datasetVersionNumber=2` | Optional; this is the built-in public dataset URL. Set only to override it. |

`GROQ_API_KEY` is required for successful Groq requests. With `AGENT_MODE=llm` and a
missing key, the application falls back to its deterministic agent; configure the
secret in Render to enable Groq. The key is read by the Python backend and is not a
Vite environment variable.

The application does not read `API_HOST` or `API_PORT` at runtime: Docker sets the
bind host and uses `PORT`. Those variables appear in local example/Compose
configuration but are not needed in Render. Do not rely on `API_PORT` to configure
the Render listener.

## 4. Import the frontend into Vercel

1. In Vercel, choose **Add New → Project** and import the same GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Use the Vite defaults or verify these project settings:
   - Framework preset: **Vite**
   - Build command: `npm run build`
   - Output directory: `dist`
   - Install command: `npm install` (Vercel may use the committed `package-lock.json`
     to install reproducibly)
4. Add this environment variable for the Production environment (and Preview too if
   you want preview builds to call the backend):

   | Variable | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://<your-render-service>.onrender.com` |

The frontend reads `VITE_API_BASE_URL` at build time and uses it for the `/api/query`
and `/api/dashboard` requests. Use the Render service's HTTPS URL and do not append
`/api`. This variable is public in the built frontend and must contain only the
backend base URL, never a secret.

## 5. Connect Vercel and configure CORS

1. The backend allows `https://cerebralzip-analytics.vercel.app` and also reads
   `FRONTEND_ORIGIN` from its Render environment. Set that variable to the exact
   production origin (scheme and hostname only), especially when using a custom
   domain.
2. The backend retains its local development origins.
3. If using a custom domain, configure `FRONTEND_ORIGIN` to the domain users visit.
   The configured value adds one allowed origin; Vercel preview domains may differ,
   so do not expect every preview URL to be allowed.
4. Redeploy/restart the Render service after changing its environment. Vercel
   environment changes require a new frontend deployment because Vite embeds them at
   build time.

## 6. Verify deployment

Replace the placeholders with the actual service URLs:

```powershell
curl.exe -i https://<your-render-service>.onrender.com/health
curl.exe -i https://<your-render-service>.onrender.com/api/dashboard
```

The health response should be HTTP 200 with `{"status":"ok"}`. The dashboard endpoint
should respond with JSON and `success: true`. Open the Vercel URL, run an analytics
query, and verify that the chart renders. Pin a chart, reload the page, and confirm
the pinned item remains; this checks SQLite persistence across requests. For an
end-to-end Groq check, use a configured `GROQ_API_KEY` and inspect backend logs for
startup or provider errors.

## Troubleshooting

- **Render health check fails or service does not bind:** confirm Docker runtime,
  root Docker build context, `Dockerfile` path, and that the Docker start command is
  not overriding the image command. Inspect Render logs for startup errors. Dataset
  download and database initialization occur before the service begins accepting
  requests.
- **Startup reports a dataset/download/load error:** check Render outbound network
  access and the `DATASET_URL`. Confirm `DATA_DIR=/var/data`, and verify the
  persistent disk is mounted and has enough capacity.
- **Pinned dashboard entries disappear after restart:** confirm a persistent disk is
  attached at `/var/data` and `DATABASE_PATH=/var/data/olist.db`. Do not run a manual
  loader against the live database without a backup.
- **Browser reports a CORS error:** set `FRONTEND_ORIGIN` to the exact deployed
  frontend origin (including `https://`, excluding paths), then restart/redeploy the
  backend. Check whether the browser is on a Vercel preview hostname instead.
- **Frontend still calls localhost or the wrong backend:** verify
  `VITE_API_BASE_URL` in the correct Vercel environment and redeploy the frontend.
- **Groq is not used:** verify `AGENT_MODE=llm` and configure `GROQ_API_KEY` in
  Render. Never put the key in Vercel. With a missing or invalid key the application
  can fall back to deterministic analytics.
- **API returns query errors:** inspect Render logs and verify the database finished
  initializing; `/health` indicates liveness, not that every analytics query has
  succeeded.
