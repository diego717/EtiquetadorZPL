# Cloud Mode (separate from legacy local flow)

This setup is designed to coexist with the current local flow.
No existing `/api/administrado/*` or `/api/mercadolibre/*` routes were replaced.

## What was added

- Auth routes (new):
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `GET /api/auth/users` (admin)
  - `POST /api/auth/users` (admin)
  - `POST /api/auth/change-password`
- Cloud queue routes (new):
  - `POST /api/cloud/administrado/queue` (admin)
  - `GET /api/cloud/tasks` (admin)
  - `POST /api/cloud/tasks/enqueue-pdf` (admin)
  - `POST /api/cloud/tasks/claim` (agent/admin)
  - `POST /api/cloud/tasks/{task_id}/complete` (agent/admin)
- Agent script:
  - `scripts/cloud_print_agent.py`

## Important note

For USB printing, the printer PC must remain on.
The cloud API can be remote, but the agent must run on the printer PC.

## Default credentials

If no auth config exists yet, first startup creates:

- username: `admin`
- password: `admin123`

Change it immediately with `POST /api/auth/change-password`.

## Quick start

1. Start API as usual.
2. Open cloud web UI:
   - `http://SERVER:8002/web/cloud.html`
3. Login from that page (`admin/admin123` if first boot).
4. Login:
   - `POST /api/auth/login`
   - body: `{"username":"admin","password":"admin123"}`
5. Create an agent user:
   - `POST /api/auth/users` with admin token
   - body: `{"username":"agent1","password":"strongpass123","role":"agent"}`
6. Queue an Administrado label:
   - `POST /api/cloud/administrado/queue`
   - body: `{"envio_id":"46624465730","printer_hint":"Godex GE300"}`
7. Run agent on printer PC:
   - `python scripts/cloud_print_agent.py --server http://SERVER:8002 --username agent1 --password strongpass123 --agent-id PC-IMPRESORA --printer "Godex GE300"`

## Storage paths

- Auth config:
  - Windows: `%APPDATA%\\EtiquetadorZPL\\cloud_auth.json`
- Queue data:
  - same SQLite DB used by the app (`etiquetador.db` in app config dir)

## Quick test on printer PC (no IDE)

Use:

- `install_runtime_pc_b.bat`
- `start_public_web_quick.bat`

Detailed guide:

- `docs/PC_B_QUICK_TEST.md`
