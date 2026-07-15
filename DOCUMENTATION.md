# Terminal Management System - Technical Documentation

## Scope

This document describes the current Terminal Management System application: its architecture, Docker runtime, database model, endpoints, Redis caching behavior, cron cleanup behavior, logging, testing, and main operational flows.

It is intentionally a technical documentation file and not a README.

## System Overview

The application is a Flask-based API for managing POS terminals. It uses MySQL as the source of truth, Redis as a cache layer, Pandas for statistics endpoints, and Docker Compose to run the required services.

The system currently contains these main runtime services:

- `tms-api`: Flask API container.
- `mysql`: MySQL database container.
- `redis`: Redis cache container.
- `decommission-cleanup`: separate cron container for deleting expired decommissioned terminals.
- `tests`: optional pytest service under the `tests` Compose profile.

```text
API Client / Browser / Postman
        |
        v
tms-api Flask API
   |          |
   v          v
MySQL 8.0    Redis 7
   |
   v
mysql_data volume

decommission-cleanup cron container -> MySQL 8.0
tests profile -> tms-api, MySQL 8.0, Redis 7
tms-api and decommission-cleanup -> stdout logs -> Docker logging driver
```

## Source Layout

```text
final_assessment/
|-- app/
|   |-- main.py
|   `-- routes/
|       |-- health.py
|       |-- terminals.py
|       |-- templates.py
|       |-- statistics.py
|       `-- reports.py
|-- db/
|   |-- db_connection.py
|   |-- cache.py
|   |-- schema_utils.py
|   `-- init/
|       |-- 01_schema.sql
|       `-- 02_seed.sql
|-- crontab/
|   |-- cleanup_decommission.py
|   |-- clear_decommission.cron
|   `-- Dockerfile
|-- tests/
|-- docker-compose.yml
|-- .env.example
`-- DOCUMENTATION.md
```

## Application Startup

The Flask app is created in `app/main.py`.

Important startup behavior:

- Logging is configured to write to `stdout`.
- JSON key sorting is disabled with `app.json.sort_keys = False`.
- Unicode JSON output is enabled with `app.json.ensure_ascii = False`.
- Route files are registered as Flask Blueprints.

```text
Docker starts tms-api
        |
        v
python -m app.main
        |
        v
configure logging to stdout
        |
        v
create Flask app
        |
        v
set ensure_ascii = False and sort_keys = False
        |
        v
register health, terminals, templates, statistics, reports blueprints
        |
        v
run Flask on 0.0.0.0:5000
```

## Docker Runtime

The project is started with Docker Compose. The API waits for MySQL and Redis healthchecks before starting.

```text
docker compose up
|-- mysql
|   `-- mysql healthcheck
|       |-- tms-api waits for mysql
|       `-- decommission-cleanup waits for mysql
|-- redis
|   `-- redis-cli ping healthcheck
|       `-- tms-api waits for redis
`-- optional tests profile
    `-- tests service waits for mysql and redis
```

### Service Responsibilities

| Service | Responsibility | Persistence | Health |
|---|---|---|---|
| `mysql` | Stores merchants, templates, terminals, decommission queue | `mysql_data:/var/lib/mysql` | `mysqladmin ping` |
| `redis` | Cache layer for GET endpoints | No active volume in current compose | `redis-cli ping` |
| `tms-api` | Flask API | Stateless | Depends on MySQL and Redis health |
| `decommission-cleanup` | Runs cron cleanup every night | Stateless | Depends on MySQL health |
| `tests` | Runs pytest when profile is enabled | Stateless | Depends on MySQL and Redis health |

### Docker Volumes

| Container | Volume | Status | Purpose |
|---|---|---|---|
| `mysql` | `mysql_data:/var/lib/mysql` | Active | Keeps database files after restarts |
| `redis` | `redis_data:/data` | Commented out | Optional cache persistence, currently not active |

The current Compose file persists MySQL data through `mysql_data`.

Redis persistence is intentionally not active. This is acceptable for a cache because cache data can be rebuilt from MySQL after restart.

### Docker Log Rotation

The Compose file defines a shared logging configuration:

```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "10"
```

Every service uses:

```yaml
logging: *default-logging
```

This means Docker rotates container logs when each log file reaches `10MB`, keeping up to `10` files per container. The application still writes logs to `stdout`; Docker handles the rotation.

```text
flowchart LR
    AppLogs["logger.info / logger.error"] --> Stdout["container stdout"]
    Stdout --> DockerDriver["Docker json-file driver"]
    DockerDriver --> CurrentLog["current log file"]
    CurrentLog --> Rotate["rotate when 10MB"]
    Rotate --> OldLogs["keep max 10 files"]
```

## Database Model

The seed schema creates three core tables:

- `merchants`
- `templates`
- `terminals`

The application adds/ensures two additional structures at runtime:

- `terminals.updated_on`
- `decommission_queue`

```text
flowchart TD
    Merchants["merchants<br/>id PK<br/>mid UNIQUE<br/>name"]
    Templates["templates<br/>id PK<br/>template_name<br/>hardware_model<br/>hardware_family"]
    Terminals["terminals<br/>id PK<br/>tid UNIQUE<br/>merchant_id FK<br/>template_id FK<br/>serial_number<br/>software_version<br/>sdk_version<br/>scenario_number<br/>hardware_model<br/>hardware_family<br/>enabled<br/>created_on<br/>last_call_stamp<br/>updated_on"]
    Queue["decommission_queue<br/>tid PK and FK<br/>queued_on<br/>delete_after"]

    Merchants -->|"one merchant owns many terminals"| Terminals
    Templates -->|"one template can create many terminals"| Terminals
    Terminals -->|"terminal can be queued for deletion"| Queue
```

### Runtime Schema Safety

`db/schema_utils.py` provides idempotent schema helpers:

- `ensure_updated_on_column(conn)`: checks `INFORMATION_SCHEMA.COLUMNS` before running `ALTER TABLE`.
- `ensure_decommission_queue_table(conn)`: uses `CREATE TABLE IF NOT EXISTS`.

```text
flowchart TD
    Start["Write endpoint starts"] --> Begin["Open database transaction"]
    Begin --> EnsureUpdated["ensure_updated_on_column"]
    EnsureUpdated --> CheckColumn["Check INFORMATION_SCHEMA.COLUMNS"]
    CheckColumn -->|Missing| Alter["ALTER TABLE terminals ADD COLUMN updated_on"]
    CheckColumn -->|Exists| Skip["Do nothing"]
    Alter --> Continue["Continue endpoint logic"]
    Skip --> Continue
```

```text
flowchart TD
    Start["A5 decommission or list decommissioned"] --> EnsureQueue["ensure_decommission_queue_table"]
    EnsureQueue --> Create["CREATE TABLE IF NOT EXISTS decommission_queue"]
    Create --> Continue["Continue safely even if table already exists"]
```

## API Endpoint Map

| Group | Method | Path |
|---|---|---|
| Health | `GET` | `/health` |
| Terminals | `GET` | `/terminals` |
| Terminals | `GET` | `/terminals?enabled=true` |
| Terminals | `GET` | `/terminals?enabled=false` |
| Terminals | `GET` | `/terminals/<tid>` |
| Terminals | `GET` | `/terminals/flagged` |
| Terminals | `POST` | `/terminals/<tid>/flag` |
| Terminals | `POST` | `/terminals/<tid>/unflag` |
| Terminals | `POST` | `/terminals/<tid>/decommission` |
| Terminals | `GET` | `/terminals/decommissioned` |
| Terminals | `POST` | `/terminals/from-template` |
| Templates | `GET` | `/templates` |
| Templates | `GET` | `/templates/<id>` |
| Statistics | `GET` | `/statistics/by-hardware` |
| Statistics | `GET` | `/statistics/by-state` |
| Statistics | `GET` | `/statistics/by-hardware-family` |
| Statistics | `GET` | `/statistics/idle-distribution` |
| Reports | `GET` | `/reports/terminals_basic.csv` |

## Endpoint Reference

### Health

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Checks database and Redis availability |

Success response:

```json
{
  "status": "ok",
  "database": "ok",
  "cache": "ok"
}
```

Degraded response returns `503` and marks the failing component.

### Terminals

| Method | Path | Cache | Purpose |
|---|---|---|---|
| `GET` | `/terminals` | TTL 30s | List terminals |
| `GET` | `/terminals?enabled=true` | TTL 30s | List enabled terminals |
| `GET` | `/terminals?enabled=false` | TTL 30s | List disabled terminals |
| `GET` | `/terminals/<tid>` | TTL 30s | Return one terminal |
| `GET` | `/terminals/flagged` | TTL 30s | Return terminals with active `scenario_number` |
| `POST` | `/terminals/<tid>/flag` | Clears all cache | Flag terminal for upgrade |
| `POST` | `/terminals/<tid>/unflag` | Clears all cache | Reset `scenario_number` to `'0'` |
| `POST` | `/terminals/<tid>/decommission` | Clears all cache | Disable terminal and queue deletion |
| `GET` | `/terminals/decommissioned` | TTL 30s | List queued decommissioned terminals |
| `POST` | `/terminals/from-template` | Clears all cache | Create terminal from template |

### Templates

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/templates` | List templates |
| `GET` | `/templates/<id>` | Return one template or `404` |

### Statistics

All statistics endpoints use Pandas and Redis cache with TTL 60 seconds.

| Method | Path | Pandas operation |
|---|---|---|
| `GET` | `/statistics/by-hardware` | `groupby("hardware_model").size()` |
| `GET` | `/statistics/by-state` | `value_counts()` over `enabled` |
| `GET` | `/statistics/by-hardware-family` | `groupby("hardware_family").size()` |
| `GET` | `/statistics/idle-distribution` | `pd.cut()` buckets and `groupby("range").size()` |

### Reports

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/reports/terminals_basic.csv` | Dynamically generates and downloads `terminals_basic.csv` |

The CSV is generated in memory using `io.StringIO()` and returned as an HTTP response. It is not saved as a permanent project file.

CSV columns:

```csv
tid,mid,hardware_model,software_version,enabled,last_call
```

## Caching Design

The application uses a cache-aside pattern.

```text
GET request
    |
    v
API checks Redis cache
    |
    |-- Cache HIT  -> return cached JSON
    |
    `-- Cache MISS -> query MySQL
                    -> format JSON
                    -> save response in Redis with TTL
                    -> return fresh JSON
```

### Cache Keys

| Endpoint | Cache key |
|---|---|
| `GET /terminals` | `terminals:list:None` |
| `GET /terminals?enabled=true` | `terminals:list:true` |
| `GET /terminals?enabled=false` | `terminals:list:false` |
| `GET /terminals/<tid>` | `terminals:detail:<tid>` |
| `GET /terminals/flagged` | `terminals:flagged` |
| `GET /terminals/decommissioned` | `terminals:decommissioned:list` |
| `GET /statistics/by-hardware` | `statistics:by-hardware` |
| `GET /statistics/by-state` | `statistics:by-state` |
| `GET /statistics/by-hardware-family` | `statistics:by-hardware-family` |
| `GET /statistics/idle-distribution` | `statistics:idle-distribution` |

### Cache TTLs

| Group | TTL |
|---|---|
| Terminals read endpoints | 30 seconds |
| Statistics endpoints | 60 seconds |

### Cache Invalidation

Every write endpoint clears the full Redis database using `cache_clear_all()`.

```text
sequenceDiagram
    participant Client
    participant API
    participant MySQL
    participant Redis

    Client->>API: POST /terminals/T0101001/flag
    API->>MySQL: SELECT terminal FOR UPDATE
    MySQL-->>API: current scenario_number
    API->>MySQL: UPDATE scenario_number, updated_on
    API->>Redis: FLUSHDB
    Redis-->>API: cache cleared
    API-->>Client: 200 Terminal flagged successfully
```

### Redis Failure Behavior

Redis failures are handled inside `db/cache.py`.

```text
flowchart TD
    CacheOp["cache_get/cache_set/cache_clear_all"] --> Try["try Redis operation"]
    Try -->|Success| Normal["Normal cache behavior"]
    Try -->|Exception| Log["logger.error Redis unavailable"]
    Log --> Continue["API continues without cache"]
```

This means the API should not crash if Redis is unavailable. It simply behaves as if there is no cache.

## Feature A - Terminal Flows

### A1: List Terminals

```text
GET /terminals
    |
    v
check Redis cache
    |
    |-- HIT  -> return cached JSON
    |
    `-- MISS -> validate enabled query if it exists
              -> invalid value returns 400
              -> query terminals joined with merchants
              -> format enabled as boolean
              -> format last_call as YYYY-MM-DDTHH:MM:SS
              -> store in Redis for 30 seconds
              -> return JSON array
```

### A4: Flag Terminal

```text
POST /terminals/<tid>/flag
    |
    v
read JSON body
    |
    |-- missing scenario_number -> 400
    |-- empty scenario_number   -> 400
    |
    v
begin transaction
    |
    v
ensure updated_on column
    |
    v
SELECT scenario_number FOR UPDATE
    |
    |-- terminal missing       -> 404
    |-- same scenario_number   -> 409
    |
    v
UPDATE scenario_number and updated_on
    |
    v
clear Redis cache
    |
    v
200 Terminal flagged successfully
```

### A4: Unflag Terminal

```text
POST /terminals/<tid>/unflag
    |
    v
begin transaction
    |
    v
ensure updated_on column
    |
    v
SELECT scenario_number FOR UPDATE
    |
    |-- terminal missing                         -> 404
    |-- scenario_number NULL, empty, or "0"      -> 409
    |
    v
set scenario_number = "0" and updated_on = now
    |
    v
clear Redis cache
    |
    v
200 Terminal unflagged successfully
```

### A5: Decommission Terminal

```text
Active terminal
enabled = 1
    |
    | POST /terminals/<tid>/decommission
    v
Decommissioned terminal
enabled = 0
    |
    v
Queued in decommission_queue
    |
    | cleanup cron runs after delete_after
    v
Deleted from queue and terminals

Error paths:
- missing TID -> 404 Terminal not found
- already disabled -> 409 Terminal already decommissioned
```

```text
POST /terminals/<tid>/decommission
    |
    v
BEGIN transaction
    |
    v
ensure updated_on column
    |
    v
ensure decommission_queue table
    |
    v
SELECT enabled FOR UPDATE
    |
    |-- terminal not found -> 404
    |-- already disabled  -> 409
    |
    v
UPDATE terminals SET enabled = 0, updated_on = now
    |
    v
INSERT INTO decommission_queue with queued_on and delete_after
    |
    v
COMMIT transaction
    |
    v
clear Redis cache
    |
    v
return queued_on and delete_after
```

## Feature B - Templates and Create From Template

### Template Endpoints

```text
flowchart TD
    Templates["Templates API"] --> List["GET /templates"]
    Templates --> Detail["GET /templates/&lt;id&gt;"]
    List --> DBList["SELECT id, template_name, hardware_model, hardware_family"]
    Detail --> DBDetail["SELECT template by id"]
    DBDetail -->|Not found| Error404["404 template not found"]
    DBDetail -->|Found| Response["Return template JSON"]
```

### Create Terminal From Template

The create-from-template endpoint runs inside a single transaction.

```text
sequenceDiagram
    participant Client
    participant API
    participant MySQL
    participant Redis

    Client->>API: POST /terminals/from-template
    API->>API: Validate JSON body
    API->>API: Convert template_id to int
    API->>MySQL: BEGIN
    API->>MySQL: SELECT template by id
    alt Template missing
        API-->>Client: 404 template not found
    else Template exists
        API->>MySQL: SELECT merchant by mid FOR UPDATE
        alt Merchant missing
            API-->>Client: 404 merchant not found
        else Merchant exists
            API->>MySQL: SELECT last terminal FOR UPDATE
            API->>API: Generate next TID
            API->>MySQL: INSERT terminal
            API->>MySQL: COMMIT
            API->>Redis: cache_clear_all()
            API-->>Client: 201 Created
        end
    end
```

TID generation:

```text
flowchart TD
    MID["mid = MID000101"] --> Prefix["prefix = T + last 4 chars<br/>T0101"]
    Last["last tid for merchant<br/>T0101006"] --> Suffix["suffix = 006"]
    Suffix --> Increment["increment to 007"]
    Prefix --> NewTID["new tid = T0101007"]
    Increment --> NewTID
```

## Feature D - Statistics With Pandas

All statistics endpoints follow this pattern:

```text
flowchart TD
    Request["GET /statistics/..."] --> Cache["Check Redis cache"]
    Cache -->|Hit| Cached["Return cached JSON"]
    Cache -->|Miss| Select["SELECT raw column(s) from MySQL"]
    Select --> DataFrame["Create Pandas DataFrame"]
    DataFrame --> Aggregate["Calculate aggregation with Pandas"]
    Aggregate --> Response["Build JSON with generated_at"]
    Response --> CacheSet["cache_set TTL 60s"]
    CacheSet --> Return["Return JSON"]
```

### D1: By Hardware

```text
flowchart LR
    SQL["SELECT hardware_model FROM terminals"] --> DF["DataFrame"]
    DF --> Group["groupby('hardware_model').size()"]
    Group --> JSON["{ generated_at, data: [{hardware_model, count}] }"]
```

### D2: By State

```text
flowchart LR
    SQL["SELECT enabled FROM terminals"] --> DF["DataFrame"]
    DF --> Counts["value_counts()"]
    Counts --> Active["active = count of 1"]
    Counts --> Inactive["inactive = count of 0"]
    Active --> JSON["{ generated_at, active, inactive, total }"]
    Inactive --> JSON
```

### D3: By Hardware Family

```text
flowchart LR
    SQL["SELECT hardware_family FROM terminals"] --> DF["DataFrame"]
    DF --> Group["groupby('hardware_family').size()"]
    Group --> JSON["{ generated_at, data: [{hardware_family, count}] }"]
```

### D4: Idle Distribution

```text
flowchart TD
    SQL["SELECT last_call_stamp FROM terminals"] --> DF["DataFrame"]
    DF --> Days["days_since_last_call = now - last_call_stamp"]
    Days --> Buckets["pd.cut() into buckets"]
    Buckets --> Group["groupby('range').size()"]
    Group --> JSON["{ generated_at, data: [{range, count}] }"]
```

Idle buckets:

| Bucket | Meaning |
|---|---|
| `Ξ£Ξ®ΞΌΞµΟΞ±` | Last call today |
| `1-7 ΞΌΞ­ΟΞµΟ‚` | Last call 1 to 7 days ago |
| `8-30 ΞΌΞ­ΟΞµΟ‚` | Last call 8 to 30 days ago |
| `31-90 ΞΌΞ­ΟΞµΟ‚` | Last call 31 to 90 days ago |
| `90+ ΞΌΞ­ΟΞµΟ‚` | Last call more than 90 days ago |

## CSV Report

The CSV report endpoint creates a CSV response dynamically.

```text
sequenceDiagram
    participant Client
    participant API
    participant MySQL

    Client->>API: GET /reports/terminals_basic.csv
    API->>MySQL: SELECT terminal + merchant fields
    MySQL-->>API: rows
    API->>API: Build CSV in memory with StringIO
    API-->>Client: text/csv attachment terminals_basic.csv
```

The endpoint does not write a permanent `.csv` file to the repository or container filesystem. It generates the CSV at request time and returns it with:

```http
Content-Disposition: attachment; filename=terminals_basic.csv
Content-Type: text/csv; charset=utf-8
```

## Cron Decommission Cleanup

The bonus cleanup runs in a separate container.

Cron schedule:

```cron
0 2 * * * . /etc/environment && cd /app && PYTHONPATH=/app /usr/local/bin/python /app/crontab/cleanup_decommission.py >> /proc/1/fd/1 2>> /proc/1/fd/2
```

This runs every day at `02:00`.

```text
sequenceDiagram
    participant Cron as cron daemon
    participant Script as cleanup_decommission.py
    participant MySQL
    participant DockerLogs as Docker stdout/stderr logs

    Cron->>Script: run daily at 02:00
    Script->>MySQL: ensure decommission_queue table
    Script->>MySQL: SELECT tid WHERE delete_after < now
    alt No expired rows
        Script->>DockerLogs: log "No expired..."
    else Expired rows found
        loop each expired terminal
            Script->>MySQL: DELETE FROM decommission_queue
            Script->>MySQL: DELETE FROM terminals
            Script->>DockerLogs: log deleted TID
        end
        Script->>DockerLogs: log cleanup summary
    end
```

The delete order matters:

```text
flowchart LR
    Queue["decommission_queue<br/>FK references terminals.tid"] --> Terminal["terminals"]
    DeleteQueue["1. Delete queue row first"] --> DeleteTerminal["2. Delete terminal row second"]
```

Because `decommission_queue.tid` references `terminals.tid`, the queue row must be deleted before deleting the terminal row.

## Logging

Application logging is configured in `app/main.py`.

Format:

```text
%(asctime)s [%(levelname)-8s] %(name)s - %(message)s
```

Example:

```text
2026-07-14 10:02:59,305 [INFO    ] app.routes.statistics - Fetched 68 rows from the database for hardware model statistics.
```

```text
flowchart TD
    Code["logger.info / logger.error"] --> PythonLogging["Python logging"]
    PythonLogging --> Stdout["stdout"]
    Stdout --> DockerLogs["docker compose logs"]
    DockerLogs --> Rotation["Docker json-file rotation<br/>10MB x 10 files"]
```

Logs are not written to application-managed files.

## Error Handling

The application uses `try/except` around database and Redis operations.

Common error response pattern:

```json
{
  "error": "database error"
}
```

Expected user-facing errors include:

| Case | Status |
|---|---|
| Terminal not found | `404` |
| Template not found | `404` |
| Merchant not found | `404` |
| Missing `scenario_number` | `400` |
| Empty `scenario_number` | `400` |
| Already flagged with same scenario number | `409` |
| Already unflagged | `409` |
| Already decommissioned | `409` |
| Wrong HTTP method | `405` |

```text
flowchart TD
    Request["Request"] --> Validate["Validate input"]
    Validate -->|Bad input| ClientError["400 / 404 / 409"]
    Validate -->|Valid| DB["Database operation"]
    DB -->|Success| Response["2xx response"]
    DB -->|Exception| Log["logger.error"]
    Log --> ServerError["500 database error"]
```

## Security and Query Safety

User inputs are passed to SQL using bind parameters instead of f-string SQL interpolation.

Example pattern:

```python
conn.execute(
    text("SELECT * FROM terminals WHERE tid = :tid"),
    {"tid": tid}
)
```

Environment variables are loaded from `.env` / `.env.example` and are not hardcoded in the source code.

## Health Checks

There are two kinds of health checks:

- Application HTTP health endpoint: `GET /health`.
- Docker Compose service healthchecks for MySQL and Redis.

```text
flowchart TD
    Client["GET /health"] --> API["Flask health endpoint"]
    API --> DBCheck["SELECT 1 against MySQL"]
    API --> RedisCheck["redis_client.ping()"]
    DBCheck --> Status["Build component status"]
    RedisCheck --> Status
    Status -->|All ok| OK["200 status=ok"]
    Status -->|Any error| Degraded["503 status=degraded"]
```

## Testing

The project has pytest coverage for route registration, cache behavior, cron cleanup, endpoint behavior, route validation, schema utilities, and statistics behavior.

```text
flowchart TD
    Tests["pytest suite"] --> AppReg["test_app_registration.py"]
    Tests --> CacheTests["test_cache.py"]
    Tests --> CronTests["test_cron_cleanup.py"]
    Tests --> EndpointTests["test_endpoint_behaviour.py"]
    Tests --> RouteValidation["test_route_validation.py"]
    Tests --> SchemaTests["test_schema_utils.py"]
    Tests --> StatisticsTests["test_statistics_behaviour.py"]
```

The Docker tests service is enabled only when the `tests` profile is used.

```text
sequenceDiagram
    participant User
    participant Compose
    participant MySQL
    participant Redis
    participant Tests

    User->>Compose: docker compose --profile tests run --rm tests
    Compose->>MySQL: ensure healthy
    Compose->>Redis: ensure healthy
    Compose->>Tests: run pytest
    Tests-->>User: pass/fail result
```

Current verified result after the latest statistics changes:

```text
40 passed
```

## Main Data Lifecycles

### Normal Terminal Read

```text
flowchart LR
    Client --> API
    API --> RedisCheck["Check Redis"]
    RedisCheck -->|Hit| Client
    RedisCheck -->|Miss| MySQL
    MySQL --> API
    API --> RedisStore["Store cache"]
    RedisStore --> Client
```

### Terminal Upgrade Flag Lifecycle

```text
flowchart LR
    Unflagged["Unflagged<br/>scenario_number is NULL, empty, or '0'"]
    Flagged["Flagged<br/>scenario_number has upgrade value"]
    Unflagged -->|"POST /flag"| Flagged
    Flagged -->|"POST /flag with different scenario_number"| Flagged
    Flagged -->|"POST /unflag"| Unflagged
```

### Decommission Lifecycle

```text
flowchart LR
    Day0["Day 0<br/>Terminal is active"] --> Decom["POST /terminals/{tid}/decommission"]
    Decom --> Disabled["enabled set to 0"]
    Disabled --> Queue["row inserted into decommission_queue"]
    Queue --> Waiting["Day 1-2<br/>GET /terminals/decommissioned shows days_remaining"]
    Waiting --> Expired["Day 3+<br/>delete_after is expired"]
    Expired --> Cron["cleanup cron runs"]
    Cron --> DeleteQueue["delete queue row"]
    DeleteQueue --> DeleteTerminal["delete terminal row"]
```

## Operational Notes

### Logs

Useful commands:

```bash
docker compose logs -f tms-api
docker compose logs -f decommission-cleanup
docker compose logs --tail=100 tms-api
```

### Cache Verification

Expected cache check:

```text
sequenceDiagram
    participant User
    participant API
    participant Redis

    User->>API: GET /terminals
    API->>Redis: MISS
    User->>API: GET /terminals
    API->>Redis: HIT
    User->>API: POST /terminals/{tid}/flag
    API->>Redis: FLUSHDB
    User->>API: GET /terminals
    API->>Redis: MISS again
```

### CSV Download

The report can be downloaded from:

```text
http://localhost:5000/reports/terminals_basic.csv
```

### Cron Cleanup Logs

Cron output is redirected to Docker stdout/stderr:

```text
/proc/1/fd/1
/proc/1/fd/2
```

Therefore cleanup logs are visible with:

```bash
docker compose logs -f decommission-cleanup
```

## Design Decisions

### Why Redis Has No Active Volume

Redis is used as a cache layer, not as the source of truth. If Redis restarts and loses cache data, the API can safely read from MySQL and repopulate Redis.

```text
flowchart LR
    RedisLost["Redis cache lost"] --> API["API receives GET"]
    API --> Miss["Cache MISS"]
    Miss --> MySQL["Read from MySQL"]
    MySQL --> Repopulate["Repopulate Redis"]
    Repopulate --> Response["Return response"]
```

### Why CSV Is Not Saved As A File

The assignment asks for an endpoint that produces `terminals_basic.csv`. The endpoint generates the CSV dynamically and returns it as a downloadable response. This avoids storing generated report files inside containers.

### Why Full Cache Clear Is Used On Writes

The application clears the full Redis DB after writes because multiple cached endpoints can be affected by a single change.

Example:

- Flagging a terminal affects `/terminals/<tid>`.
- It may affect `/terminals/flagged`.
- It may affect general terminal lists.
- It may affect statistics if enabled/state/hardware-related data changes through other write endpoints.

Full invalidation is simpler and safer for this project.

## Current Implementation Summary

```text
flowchart TD
    TMS["TMS"]
    TMS --> Flask["Flask API"]
    Flask --> Blueprints["Blueprints"]
    Flask --> JSON["JSON responses"]
    Flask --> MethodHandler["405 handler"]

    TMS --> MySQL["MySQL"]
    MySQL --> Seed["Seed schema"]
    MySQL --> Volume["Persistent volume"]
    MySQL --> SchemaHelpers["Runtime schema helpers"]

    TMS --> Redis["Redis"]
    Redis --> CacheAside["Cache-aside"]
    Redis --> HitMiss["Hit/Miss logs"]
    Redis --> Fallback["Safe fallback"]

    TMS --> Pandas["Pandas"]
    Pandas --> HardwareStats["Hardware stats"]
    Pandas --> StateStats["State stats"]
    Pandas --> FamilyStats["Family stats"]
    Pandas --> IdleBuckets["Idle buckets"]

    TMS --> Docker["Docker"]
    Docker --> Services["Compose services"]
    Docker --> Healthchecks["Healthchecks"]
    Docker --> LogRotation["Log rotation"]

    TMS --> Cron["Cron"]
    Cron --> SeparateContainer["Separate container"]
    Cron --> DailyCleanup["Daily cleanup"]
    Cron --> StdoutLogs["Docker stdout logs"]

    TMS --> Tests["Tests"]
    Tests --> Pytest["Pytest"]
    Tests --> DockerProfile["Docker profile"]
```

