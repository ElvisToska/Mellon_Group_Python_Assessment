# Terminal Management System (TMS)

Flask API για διαχείριση POS terminals. Η εφαρμογή συνδέεται με MySQL, χρησιμοποιεί Redis για caching, παράγει στατιστικά με Pandas και τρέχει μέσα από Docker Compose.

Το project υλοποιεί τα βασικά features της εκφώνησης:

- Διαχείριση terminals.
- Flag / unflag terminals για upgrade.
- Decommission terminals με ουρά διαγραφής.
- Templates και δημιουργία terminal από template.
- Redis caching με hit/miss logs και invalidation μετά από writes.
- Statistics endpoints με Pandas.
- CSV report endpoint.
- Health endpoint.
- Cron cleanup container για decommissioned terminals.
- Pytest tests μέσω Docker profile.
- Logging στο stdout με Docker log rotation.

Για αναλυτικό τεχνικό documentation υπάρχει και το αρχείο:

```text
DOCUMENTATION.md
```

## Τεχνολογίες

| Τεχνολογία | Χρήση |
|---|---|
| Flask | REST API |
| MySQL 8.0 | Βάση δεδομένων |
| Redis 7 | Cache layer |
| SQLAlchemy | Database access |
| Pandas | Statistics aggregation |
| Docker Compose | Εκκίνηση όλων των services |
| Pytest | Unit tests |
| Cron | Αυτόματο cleanup decommissioned terminals |

## Services

Το `docker-compose.yml` σηκώνει τα παρακάτω services:

| Service | Περιγραφή |
|---|---|
| `mysql` | MySQL database με seed data από `db/init/` |
| `redis` | Redis cache |
| `tms-api` | Flask API |
| `decommission-cleanup` | Ξεχωριστό cron container για cleanup |
| `tests` | Optional pytest container μέσω profile |

## Προαπαιτούμενα

Χρειάζονται:

- Docker Desktop
- Git
- Προαιρετικά Python 3.12 για local testing

Η εφαρμογή έχει σχεδιαστεί να τρέχει κυρίως με Docker.

## Environment Variables

Το πραγματικό `.env` δεν πρέπει να ανέβει στο git.

Υπάρχει template:

```text
.env.example
```

Για να ξεκινήσει το project, δημιουργήστε το `.env`:

```powershell
Copy-Item .env.example .env
```

Παράδειγμα μεταβλητών:

```env
MYSQL_ROOT_PASSWORD=change_me_root_password
DB_NAME=tms
DB_USER=tms_user
DB_PASS=change_me_app_password
DB_HOST=mysql
DB_PORT=3306

REDIS_HOST=redis
REDIS_PORT=6379
```

Στο Docker Compose, το API χρησιμοποιεί:

```text
DB_HOST=mysql
REDIS_HOST=redis
```

επειδή τα containers επικοινωνούν μεταξύ τους με τα service names.

## Εκκίνηση

Από το root του project:

```powershell
docker compose up -d --build
```

Έλεγχος containers:

```powershell
docker compose ps
```

Logs του API:

```powershell
docker compose logs -f tms-api
```

Logs του cron cleanup:

```powershell
docker compose logs -f decommission-cleanup
```

Τα logs δεν αποθηκεύονται σε κάποιο `.log` αρχείο μέσα στο project. Πηγαίνουν στο `stdout`/`stderr` των containers και τα βλέπουμε μέσω Docker logs.

Το API ακούει στο:

```text
http://localhost:5000
```

## Database Seed

Τα αρχεία:

```text
db/init/01_schema.sql
db/init/02_seed.sql
```

τρέχουν αυτόματα την πρώτη φορά που δημιουργείται το MySQL container, επειδή γίνονται mount στο:

```text
/docker-entrypoint-initdb.d
```

Τα MySQL data αποθηκεύονται σε Docker volume:

```text
mysql_data
```

Αν χρειαστεί πλήρες reset της βάσης:

```powershell
docker compose down -v
docker compose up -d --build
```

Προσοχή: το `down -v` σβήνει το database volume.

## Τι Περιέχει Η Βάση

Η βάση περιέχει τα βασικά δεδομένα του Terminal Management System:

| Πίνακας | Περιγραφή |
|---|---|
| `merchants` | Τα καταστήματα/merchants. Κάθε merchant έχει μοναδικό `mid`. |
| `templates` | Πρότυπα terminal με στοιχεία όπως `hardware_model` και `hardware_family`. |
| `terminals` | Τα πραγματικά POS terminals. Κάθε terminal ανήκει σε merchant και μπορεί προαιρετικά να έχει δημιουργηθεί από template. |
| `decommission_queue` | Ουρά για terminals που έχουν γίνει decommission και θα διαγραφούν μετά από 3 μέρες. Δημιουργείται από τον κώδικα αν δεν υπάρχει. |

Επιπλέον, ο κώδικας προσθέτει με ασφαλή τρόπο τη στήλη:

```text
terminals.updated_on
```

Η στήλη αυτή δεν υπάρχει στο αρχικό seed schema και χρησιμοποιείται όταν γίνεται flag, unflag ή decommission.

## Endpoints

### Health

| Method | Endpoint | Περιγραφή |
|---|---|---|
| `GET` | `/health` | Ελέγχει MySQL και Redis. Επιστρέφει `200` αν όλα είναι ok ή `503` αν κάποιο service είναι degraded. |

### Terminals

| Method | Endpoint | Περιγραφή |
|---|---|---|
| `GET` | `/terminals` | Επιστρέφει όλα τα terminals. |
| `GET` | `/terminals?enabled=true` | Επιστρέφει μόνο ενεργά terminals. |
| `GET` | `/terminals?enabled=false` | Επιστρέφει μόνο ανενεργά terminals. |
| `GET` | `/terminals/<tid>` | Επιστρέφει λεπτομέρειες για συγκεκριμένο terminal. |
| `GET` | `/terminals/flagged` | Επιστρέφει terminals που έχουν `scenario_number` διαφορετικό από `NULL`, κενό string ή `'0'`. |
| `POST` | `/terminals/<tid>/flag` | Θέτει νέο `scenario_number` και ενημερώνει το `updated_on`. |
| `POST` | `/terminals/<tid>/unflag` | Θέτει `scenario_number = '0'` και ενημερώνει το `updated_on`. |
| `POST` | `/terminals/<tid>/decommission` | Θέτει `enabled = 0` και βάζει το terminal στο `decommission_queue`. |
| `GET` | `/terminals/decommissioned` | Επιστρέφει terminals που βρίσκονται στην ουρά decommission. |
| `POST` | `/terminals/from-template` | Δημιουργεί νέο terminal από template για συγκεκριμένο merchant. |

Παράδειγμα body για flag:

```json
{
  "scenario_number": "5"
}
```

Παράδειγμα body για create from template:

```json
{
  "template_id": 1,
  "mid": "MID000101"
}
```

### Templates

| Method | Endpoint | Περιγραφή |
|---|---|---|
| `GET` | `/templates` | Επιστρέφει όλα τα templates. |
| `GET` | `/templates/<id>` | Επιστρέφει συγκεκριμένο template ή `404` αν δεν υπάρχει. |

### Statistics

Τα statistics υλοποιούνται με Pandas και cache TTL 60 δευτερόλεπτα.

| Method | Endpoint | Περιγραφή |
|---|---|---|
| `GET` | `/statistics/by-hardware` | Κατανομή terminals ανά `hardware_model`. |
| `GET` | `/statistics/by-state` | Πλήθος active / inactive / total terminals. |
| `GET` | `/statistics/by-hardware-family` | Κατανομή terminals ανά `hardware_family`. |
| `GET` | `/statistics/idle-distribution` | Κατανομή terminals με βάση τις μέρες από το τελευταίο `last_call_stamp`. |

### Reports

| Method | Endpoint | Περιγραφή |
|---|---|---|
| `GET` | `/reports/terminals_basic.csv` | Παράγει δυναμικά και κατεβάζει το `terminals_basic.csv`. |

Το CSV δεν αποθηκεύεται σαν μόνιμο αρχείο στο project. Δημιουργείται στη μνήμη όταν καλείται το endpoint. Πραγματοποιείται μεθοδολογία ETL.

## Redis Cache

Η εφαρμογή χρησιμοποιεί cache-aside pattern:

1. Το API ψάχνει πρώτα στο Redis.
2. Αν υπάρχει cache HIT, επιστρέφει cached response.
3. Αν υπάρχει cache MISS, διαβάζει από MySQL.
4. Μετά αποθηκεύει το αποτέλεσμα στο Redis για επόμενο request.

TTL:

| Endpoints | TTL |
|---|---|
| `/terminals*` read endpoints | 30 δευτερόλεπτα |
| `/statistics/*` endpoints | 60 δευτερόλεπτα |

Μετά από κάθε write endpoint γίνεται:

```text
cache_clear_all()
```

ώστε το επόμενο GET να διαβάσει φρέσκα δεδομένα από τη βάση.

Αν το Redis είναι εκτός λειτουργίας, το API δεν κρασάρει. Απλώς συνεχίζει χωρίς cache και γράφει error log.

## Schema Changes Από Τον Κώδικα

Η αρχική seed βάση δεν έχει:

```text
terminals.updated_on
```

Η εφαρμογή το προσθέτει με ασφαλή/idempotent τρόπο μέσω `INFORMATION_SCHEMA`, ώστε να μη σκάει αν η στήλη υπάρχει ήδη.

Επίσης η εφαρμογή δημιουργεί τον πίνακα:

```text
decommission_queue
```

με `CREATE TABLE IF NOT EXISTS`.

## Cron Cleanup

Υπάρχει ξεχωριστό service:

```text
decommission-cleanup
```

Το cron τρέχει κάθε μέρα στις `02:00`:

```cron
0 2 * * * . /etc/environment && cd /app && PYTHONPATH=/app /usr/local/bin/python /app/crontab/cleanup_decommission.py >> /proc/1/fd/1 2>> /proc/1/fd/2
```

Το `>> /proc/1/fd/1` στέλνει το κανονικό output του script στο `stdout` του container.

Το `2>> /proc/1/fd/2` στέλνει τα errors στο `stderr` του container.

Άρα τα cron logs φαίνονται με:

```powershell
docker compose logs -f decommission-cleanup
```

Το script:

1. Βρίσκει terminals στο `decommission_queue` με `delete_after < now`.
2. Διαγράφει πρώτα τη γραμμή από `decommission_queue`.
3. Διαγράφει μετά το αντίστοιχο terminal από `terminals`.

Η σειρά αυτή είναι σημαντική λόγω foreign key.

Manual run για έλεγχο:

```powershell
docker compose exec decommission-cleanup python /app/crontab/cleanup_decommission.py
```

## Logging

Όλα τα application logs γράφονται σε `stdout`, όχι σε application log files.

Αυτό σημαίνει ότι:

| Service | Πού βλέπω logs |
|---|---|
| `tms-api` | `docker compose logs -f tms-api` |
| `decommission-cleanup` | `docker compose logs -f decommission-cleanup` |
| `mysql` | `docker compose logs -f mysql` |
| `redis` | `docker compose logs -f redis` |

Το format περιλαμβάνει:

- timestamp
- log level
- logger name
- message

Παράδειγμα:

```text
2026-07-14 10:02:59,305 [INFO    ] app.routes.statistics - Fetched 68 rows from the database for hardware model statistics.
```

Το Docker Compose έχει log rotation:

```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "10"
```

Άρα τα logs συνεχίζουν να είναι Docker/container logs, αλλά το Docker κρατά μέχρι 10 rotated log files των 10MB ανά service.

## Tests

Το project έχει pytest tests για:

- route registration
- cache behavior
- cron cleanup
- endpoint behavior
- route validation
- schema utilities
- statistics behavior

Τρέξιμο tests με Docker profile:

```powershell
docker compose --profile tests run --rm tests
```

Τελευταίο επιβεβαιωμένο αποτέλεσμα:

```text
40 passed
```

## CI

Υπάρχει GitHub Actions workflow στο:

```text
.github/workflows/ci.yml
```

Το CI τρέχει αυτόματα:

- σε κάθε `push` σε οποιοδήποτε branch
- σε κάθε `pull request` προς `main`

Το workflow έχει δύο jobs:

| Job | Τι κάνει |
|---|---|
| `Python tests` | Στήνει Python 3.12, κάνει pip cache, εγκαθιστά dependencies και τρέχει `pytest -q` τοπικά στο GitHub runner. |
| `Docker Compose tests` | Δημιουργεί test `.env`, κάνει validate το Compose config, χτίζει το test image και τρέχει `docker compose --profile tests run --rm tests`. |

Αν αποτύχει το Docker Compose job, το CI εμφανίζει τα container logs για debugging.

## Χρήσιμα Commands

Start / rebuild:

```powershell
docker compose up -d --build
```

Stop:

```powershell
docker compose down
```

Full reset μαζί με database volume:

```powershell
docker compose down -v
docker compose up -d --build
```

API logs:

```powershell
docker compose logs -f tms-api
```

Cleanup logs:

```powershell
docker compose logs -f decommission-cleanup
```

Run tests:

```powershell
docker compose --profile tests run --rm tests
```

Health check:

```powershell
Invoke-RestMethod http://localhost:5000/health
```

Download CSV:

```powershell
Invoke-WebRequest -Uri http://localhost:5000/reports/terminals_basic.csv -OutFile "$env:USERPROFILE\Downloads\terminals_basic.csv"
```

## Σημειώσεις Για Τον Έλεγχο

- Το API τρέχει στο `http://localhost:5000`.
- Η MySQL έχει persistent volume (`mysql_data`).
- Το Redis χρησιμοποιείται ως προσωρινό cache layer, άρα δεν έχει ενεργό volume. (volume σε σχόλια)
- Το CSV report παράγεται δυναμικά από endpoint και δεν αποθηκεύεται μόνιμα.
- Το cron cleanup τρέχει σε ξεχωριστό container.
- Τα logs γράφονται στο stdout και γίνονται rotate από Docker logging options.
- Τα statistics endpoints χρησιμοποιούν Pandas για aggregation.
- Μετά από κάθε write γίνεται cache invalidation.
- Τα database queries με user input χρησιμοποιούν bind parameters.
