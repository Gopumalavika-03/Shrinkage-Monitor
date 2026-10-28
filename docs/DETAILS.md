# Shrinkage Monitor: full technical details

The short version is the [README](../README.md). This page has every detail: data design, rules, checks, API, database.

A reproducible synthetic dataset for a 100-store retail chain (1,000,000 baseline stock movements), with
labelled problem cases planted in it, plus a rule-based detector that finds them. Every alert explains
itself from the evidence, and the detector is scored against a separate answer key. A FastAPI backend
serves the results, and a React dashboard lets you explore alerts, evidence, checks and the answer key.

```
                 backend/app/pipeline (Python)                        backend/app (FastAPI)       frontend (React)
generate -> validate -> detect -> evaluate -> CSV / JSON / SQLite  ->  /api/... endpoints   ->   dashboard
clean data   integrity   alerts +   precision   + reports              read-only over the        overview, alerts,
+ planted    checks      reasons    / recall    + manifest             SQLite DB + reports       validation, answer key
```

## Project structure

```
backend/
  app/
    __main__.py          `python -m app`: starts the API with host/port from .env
    main.py              FastAPI app (also serves the built frontend)
    settings.py          reads backend/.env (API, CORS, output folder, database, LLM)
    db.py                Postgres / Supabase: bulk loader + queries (`python -m app.db`)
    api/routes.py        HTTP endpoints, no business logic
    services/results.py  reads reports + SQLite, runs the pipeline in the background
    pipeline/            the data + detection engine, usable without the API
      config.py            seed, size presets, mix rates, detector thresholds
      schema.py            every table: columns, types, keys, allowed values (single source of truth)
      generate.py          parents -> baseline -> planted cases -> calculated balances -> IDs -> ground truth
      validate.py          integrity + business-rule checks, stock equation
      detect.py            6 rules -> shrinkage_alert / alert_evidence / investigation; evaluate()
      run.py               CLI: export CSV/JSON/SQLite, manifest, --repro
      llm.py               optional LLM alert summaries (cached)
  llm_cache/vocab.json   LLM-generated names and notes (committed)
  tests/                 pipeline + API tests
  requirements.txt
  .env.example           backend settings template (copy to .env, git-ignored)
frontend/
  src/
    App.jsx              layout, dataset switch, run button, tabs
    api.js               API client + loading hook
    pages/               Overview, Alerts, Validation, GroundTruth
    components/          AlertDetail, shared UI (tables, bars, status)
    styles.css           light + dark theme tokens
  package.json, vite.config.js
  .env.example           frontend settings template (copy to .env, git-ignored)
docs/
  data_dictionary.md     every field: type, required, allowed values, units, rule
  schema.sql             SQLite DDL with primary + foreign keys
  schema.postgres.sql    Postgres / Supabase DDL, keys and indexes
results/full/, results/medium/   reports, alerts and answer key of those runs (committed)
sample_output/           CSVs + answer key + alerts + reports of a small run (committed)
```

## Run it

**1. Backend + data** (Python 3.12):

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env                               # settings; all optional (see "Environment" below)
python -m app.pipeline.run --size small            # ~3 s: 5 stores, 20k movements (same code as full)
python -m app.pipeline.run --size medium           # ~25 s: half of full (50 stores, 2,500 SKUs, 500k movements)
python -m app.pipeline.run --size full             # ~80 s: the brief's size (100 stores, 5,000 SKUs, 1M movements)
python -m app.pipeline.run --size full --repro     # runs twice with seed 20261022, compares row counts + SHA-256
python -m pytest -q                                # 11 tests (pipeline + API) + 1 Postgres test when TEST_DATABASE_URL is set
python -m app.db --size small                      # optional: load a run into Supabase (needs DATABASE_URL)
python -m app                                      # API on http://127.0.0.1:8000/docs (host/port from .env)
```

**2. Frontend** (Node 18+), in a second terminal:

```bash
cd frontend
cp .env.example .env                               # optional
npm install
npm run dev                                        # dashboard on http://localhost:5173 (proxies /api to :8000)
```

For a single server, run `npm run build` once; FastAPI then serves the dashboard at http://127.0.0.1:8000.

### Environment

Both sides read a `.env` file; the committed `.env.example` files are the templates, and the real `.env` files are
git-ignored. Every value has a default, so nothing is required to run.

| File | Variable | Default | Used for |
|---|---|---|---|
| `backend/.env` | `API_HOST`, `API_PORT`, `API_RELOAD` | `127.0.0.1`, `8000`, `false` | `python -m app` |
| | `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | browsers allowed to call the API |
| | `OUTPUT_DIR` | `output` (inside backend/) | where pipeline runs are written and read |
| | `DATABASE_URL` | empty = local SQLite | Postgres / Supabase connection string |
| | `DB_SCHEMA_PREFIX` | `shrinkage` | schemas `shrinkage_small`, `shrinkage_full` |
| | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | OpenAI URL, empty, empty | optional Explain / `--llm` summaries |
| `frontend/.env` | `VITE_API_BASE_URL` | empty = same origin | set only if the API is hosted elsewhere (then add the site to `CORS_ORIGINS`) |
| | `VITE_DEV_PORT`, `VITE_API_PROXY_TARGET` | `5173`, `http://127.0.0.1:8000` | `npm run dev` only |

Secrets stay in `backend/.env`. Anything in `frontend/.env` is built into the browser bundle.

### Database (Supabase / Postgres)

Without `DATABASE_URL`, the API reads each run's local SQLite file. To serve everything from Supabase:

1. In the Supabase dashboard open **Connect**, copy the **Session pooler** URI (it works on IPv4 networks; the direct
   `db.<ref>.supabase.co` host is IPv6-only), and put it, with your database password filled in, in `backend/.env` as
   `DATABASE_URL=...`.
2. Load the data: `python -m app.db --size small` (add `--size medium` or `--size full` only if you need them).
3. Restart the API (`python -m app`). The dashboard header then shows `data: Postgres (shrinkage_small)`.

How the load works:
- Each size goes in its own schema (`shrinkage_small`, `shrinkage_full`). They sit outside `public`, so Supabase's
  auto-generated REST API does not expose them.
- Tables are created from [docs/schema.postgres.sql](schema.postgres.sql) with proper types (`DATE`, `TIMESTAMP`,
  `DOUBLE PRECISION`). Every CSV is bulk-loaded with `COPY`, then all 41 foreign keys are added, which re-validates every row.
- Everything is built in a `<schema>_loading` schema and swapped in within one transaction, so readers never see a
  half-loaded run. Reports and the answer key go in too (`pipeline_report`, `ground_truth`), so the API needs no local files.
- Sizes in Postgres: small 7.5 MB, medium **141 MB**, full **284 MB**. Supabase's free plan has 500 MB, so load at most two of
  medium/full there; the dashboard only lists sizes that are loaded.
- After a **Run pipeline** click in the dashboard, the new run is loaded automatically.
- `tests/test_postgres.py` checks that the API returns exactly the same JSON from Postgres as from SQLite.

The dashboard's **Run pipeline** button regenerates a dataset from the UI. It builds in a scratch folder and swaps it in,
so the current results stay readable until the new run is done.

### API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | status, whether an LLM is configured |
| GET | `/api/runs` | which sizes have results, seed, combined hash, run state |
| POST | `/api/runs` `{size, repro}` | starts a pipeline run in the background (202; 409 if one is running) |
| GET | `/api/{size}/overview` | headline numbers, scores, innocent checks, stock equation, alerts by rule, top stores |
| GET | `/api/{size}/alerts?alert_type&classification&severity&store_id&q&limit&offset` | paged, filtered alerts by risk |
| GET | `/api/{size}/alerts/{alert_id}` | alert + investigation + evidence rows + matching answer-key case |
| POST | `/api/{size}/alerts/{alert_id}/explain` | LLM plain-language summary (503 if no LLM configured) |
| GET | `/api/{size}/validation` | every check with status and rows flagged |
| GET | `/api/{size}/ground-truth` | every planted case with CAUGHT / MISSED / CORRECTLY_IGNORED |

Interactive docs: http://127.0.0.1:8000/docs. The API is read-only over the pipeline outputs; all detection logic
lives in `pipeline/`, so the CLI and the API always give the same numbers.

### Pipeline output

Each run writes to `backend/output/<size>/` (git-ignored; the full run is ~700 MB):

| Folder | Contents |
|---|---|
| `data/csv`, `data/json`, `data/shrinkage.sqlite` | The 17 tables as CSV, JSON Lines, and SQLite with PK/FK constraints ([docs/schema.sql](schema.sql)) |
| `ground_truth/` | The answer key (`anomalies.csv/.jsonl`). **The detector never reads it**, and the input tables carry no label or flag column. |
| `alerts/` | `shrinkage_alert`, `alert_evidence`, `investigation` (detector output) |
| `reports/` | `validation_summary.json`, `evaluation.json`, `manifest.json` (rows + SHA-256 per file), `reproducibility.json` |

Seed and sizes live in [backend/app/pipeline/config.py](../backend/app/pipeline/config.py). The CLI exits non-zero if any
integrity check fails.

## Sizes

| Size | Stores | SKUs | Baseline movements | Cycle counts | Build time | Use it for |
|---|---|---|---|---|---|---|
| small | 5 | 200 | 20,000 | 500 | ~3 s | default: exploring, demos, tests |
| medium | 50 | 2,500 | 500,000 | 10,000 | ~25 s | a bigger demo |
| full | 100 | 5,000 | 1,000,000 | 20,000 | ~80 s | the size the brief requires |

All three use the same code and plant the same kinds of cases; medium also scores 100% precision and recall
([results/medium/evaluation.json](../results/medium/evaluation.json)).

## Results (full run, seed 20261022)

| Planted case | Unit scored | Planted | Flagged | Precision | Recall |
|---|---|---|---|---|---|
| Movement booked to the wrong store | movement | 25 | 25 | 1.00 | 1.00 |
| Adjustment with no reason | movement | 25 | 25 | 1.00 | 1.00 |
| Count timestamped before movements it includes | cycle count | 25 | 25 | 1.00 | 1.00 |
| Transfer written off as loss at both stores | transfer | 10 | 10 | 1.00 | 1.00 |
| Repeated write-offs by one employee | employee | 4 | 4 | 1.00 | 1.00 |
| Unexplained shortages after one employee's handling | employee | 4 | 4 | 1.00 | 1.00 |

**Innocent explanations are not called theft:**

| Innocent loss in the data | Count | In a theft alert |
|---|---|---|
| Rows from one-day damage incidents (decoys, e.g. a cold-room failure) | 166 | 0 |
| Customer returns written off as damaged | 7,945 | 0 |
| Honest transit losses (written off once, correctly) | 575 | 0 |
| Large count shortages with no staff pattern (shoplifting-like background) | 181 | 1* |

\* This shortage happened on stock a real planted suspect handled, so it sits inside a correct alert's evidence.

**Without the one-day-incident rule, the decoy makes the detector accuse an innocent stock associate** (4 alerts, 1 false).
With the rule: 0 false. So the decoy is a real test, not padding.

**Validation:** 228 checks, 224 pass. The 4 that flag rows are business-rule checks, and each flags exactly the planted
errors (25, 25, 25 and 10 rows). SQLite `PRAGMA foreign_key_check` finds 0 violations.

**Stock equation (whole network, units):**

```
opening 1,655,365 + receipts 1,199,028 - sales 1,265,072 + transfers in 361,516 - transfers out 361,516
+ returns 53,153 + adjustments (-63,270) = closing book 1,579,204   ✔
```

The same equation is checked **for each of the 20,000 cycle counts** (`expected_qty`) and each of the 60,000 store-SKU closing
balances. It's recomputed in `validate.py` by a different method from the generator.

**Reproducibility:** two full runs with the same seed give identical output: all 38 CSV/JSON/report files have the same
row counts and SHA-256, combined hash `1c9cfea792c93369…`. The second run is a separate Python process, so nothing in memory is shared
([results/full/reproducibility.json](../results/full/reproducibility.json)).

## What is generated

| Table | Rows (full) | ID format | Notes |
|---|---|---|---|
| store | 100 | `STORE-000001` | 3 formats (traffic 3x / 1.5x / 0.6x), 5 regions |
| sku | 5,000 | `SKU-000001` | 10 categories, cost < price, perishable flag, shrink risk |
| store_sku *(bridge)* | 60,000 | (store, sku) | Assortment: 12% of SKUs per store; opening + closing book stock |
| role | 4 | `ROLE-01` | Cashier, Stock Associate, Shift Supervisor, Store Manager |
| employee | 1,400 | `EMP-000001` | 14 per store |
| employee_role *(bridge)* | 1,700 | (employee, role) | Supervisors also hold Stock Associate |
| shift | 54,300 | `SHF-2026-000001` | 3 x 8 h per store per day, Jan–Jun 2026 |
| shift_assignment *(bridge)* | 162,900 | (shift, employee) | Cashier + stock associate + supervisor on every shift |
| promotion / promotion_sku *(bridge)* | 40 / 3,612 | `PRM-2026-0001` | Promo price is used in refund maths |
| transfer | 30,000 | `TRF-2026-000001` | 2% lost in transit |
| **inventory_movement** | **1,003,375** | `MOV-2026-00000001` | 1,000,000 baseline + 2,899 count corrections + 476 planted rows (166 of them decoys) |
| customer_return | 40,000 | `RET-2026-000001` | Linked to the original sale; 20% come back damaged |
| **cycle_count** | **20,000** | `CNT-2026-000001` | Book snapshot vs shelf count |
| **shrinkage_alert** | 93 | `SHR-2026-000001` | Detector output |
| alert_evidence *(bridge)* | 629 | (alert, type, id) | Which movements/counts/transfers back each alert |
| **investigation** | 93 | `INV-2026-000001` | One open case per alert, assigned to the store manager |

Every field (type, required, allowed values, units, rule) is in [docs/data_dictionary.md](data_dictionary.md), generated from
[schema.py](../backend/app/pipeline/schema.py), the same definition the validator and the SQLite schema use.

## How the data is built

1. **Parents first:** stores → SKUs → roles → employees → shifts → assignments → assortment → promotions.
2. **Clean baseline, exactly 1,000,000 movements:** sales (≈76%), receipts in case packs, transfers (out + in pairs),
   customer returns tied to a real earlier sale, and everyday adjustments. Honest losses are built in: damage, expiry,
   miscounts, found stock, damaged returns written off, transfers lost in transit (written off once), and small
   untraceable count shortages that are larger for high-risk SKUs.
3. **Plant the problems** (each tagged internally; tags never reach the exported tables):
   - *Wrong store:* a receipt is booked to another store that also stocks the SKU, while its shift and employee stay at
     the real store.
   - *No reason:* the reason and note are removed from a normal write-off.
   - *Count before movements:* a count's `count_ts` is moved before movements already included in its `expected_qty`.
   - *Transfer double loss:* the sending store also writes off a transfer the receiving store already wrote off.
   - *Repeated adjustments:* one stock associate per store posts about 2x their normal write-offs on top of normal,
     75% on night shifts, on high-value SKUs, using believable reasons.
   - *Unexplained loss:* large shortages (6–15 units) on counts where one employee was the last to handle the stock.
   - *Decoy:* a one-day damage incident. Most of the clean-up is logged by the morning stock associate, so per person
     it looks like the repeated-adjustment pattern.
4. **Balances come from the data, not from random numbers:**
   - Any count variance is posted as a new `COUNT_VARIANCE` movement. History is append-only and nothing is edited.
   - Opening stock is the smallest amount that keeps every running balance and every shelf count ≥ 0.
   - `expected_qty` = opening + all movements up to the book snapshot; `counted_qty` = expected + variance.
   - Values, refunds (with promo discount) and closing stock are all calculated.
5. **IDs are assigned after sorting by time**, so a planted row can't be spotted by an unusual ID.

## How the detector decides (detect.py)

| Rule | Fires when | Classified as |
|---|---|---|
| WRONG_STORE | movement's store ≠ the store of the shift it was posted in | data error |
| MISSING_REASON | adjustment with no reason code | process error |
| COUNT_BEFORE_MOVEMENTS | `count_ts` < book snapshot; lists the movements in between | data error |
| TRANSFER_DOUBLE_LOSS | more than one store wrote off the same transfer; names the sender's duplicate | data error |
| REPEATED_ADJUSTMENTS | employee's write-offs vs their share of the store's write-offs in the same role (by shifts worked): Poisson z ≥ 4, **or** z ≥ 2.5 **and** night-shift share far above the role's normal (binomial p < 0.01). One-day incidents (≥ 20 write-offs by ≥ 3 people) are excluded first. | suspected theft |
| UNEXPLAINED_LOSS | ≥ 3 large shortages (≥ 5 units) on stock the employee handled last, with chance p < 1e-4 against **everyone else's** shortage rate | suspected theft |

Choices worth noting:
- **Exposure-based comparison.** Hypermarket staff post more write-offs than Express staff simply because of traffic,
  so each person is compared with peers in the same store and role, adjusted for shifts worked.
- **Joint threshold.** z ≥ 2.5 happens by chance for about 0.6% of people and night p < 0.01 for 1%, so needing both
  (≈0.006%) is as strict as z ≥ 4 alone (≈0.003%). It catches a thief in a small store whose count alone is weak.
- **Leave-one-out baseline.** A suspect's own shortages are left out of the baseline they are compared with.
- **Counts with bad timestamps are not used as theft evidence:** they are already reported as data errors.

Each alert stores the employee, role and shift involved, units and INR at stake, a 0–100 risk score
(rule base + log of value), its severity, and a `reason_text` built only from computed numbers, for example:

> EMP-000062 (Cashier) was the last person to handle the stock before 6 of the 20 counts that followed their movements
> showed a large shortage (>= 5 units). At everyone else's rate of 1.0% about 0.2 would be expected by chance
> (p = 8.1e-08). 62 units (INR 18,615) are missing with no write-off or reason recorded.

## Validation checks (validate.py)

- **Keys:** primary keys unique; ID formats; all 41 foreign keys, including composite (store, sku) → store_sku.
- **Values:** required fields present, allowed values only, quantity sign matches movement type, reason only on adjustments,
  unit cost matches the SKU, price > cost, no duplicate movements.
- **Dates:** shifts are 8 h long; movements fall inside their shift; transfer received after shipped; return after its
  sale (same store and SKU, qty ≤ sold); hired after the store opened; promotion end ≥ start.
- **Maths:** stock equation per count and per store-SKU; running balance never negative; variance = counted − expected;
  variance value; refund = qty × price × (1 − discount); every variance posted exactly once.
- **Business rules** (expected to flag exactly the planted rows): store = shift's store; adjustment has a reason;
  count not before its snapshot; transfer written off at most once.

## Where LLMs are used

- **Realistic vocabulary:** product names, brands, pack sizes, cities, staff names and staff notes
  ([backend/llm_cache/vocab.json](../backend/llm_cache/vocab.json)) were generated **once** by an LLM (Claude, 2026-10-28) and committed.
  The generator only reads this file and never calls an LLM, so the seed alone fixes the output.
- **Plain-language alert summaries (optional):** `python -m app.pipeline.run --llm` (or the dashboard's *Explain* button) sends the top 25 alerts' *computed facts*
  to any OpenAI-compatible endpoint at temperature 0. Settings (`LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`) go in
`backend/.env` (template: [backend/.env.example](../backend/.env.example); `.env` is git-ignored). The LLM only rephrases;
  it never sees raw data or produces numbers. Replies are cached in `llm_cache/`, and the file is kept out of the checksums.
- LLMs were also used as coding assistants while building this repo.

## Limitations

- The data is synthetic. Scores show the detector finds patterns of this shape at this strength; real shrink is messier.
  Thresholds in `pipeline/config.py` would need tuning on real data.
- Perfect scores come from planted cases that are strong enough to find at these sizes. Lowering
  `REPEATED_ADJ_MULTIPLIER` or `UNEXPLAINED_SHORTAGE` in `pipeline/config.py` makes them harder and shows recall drop.
- "Last handler" is a proxy for responsibility. It points an investigator at whom to ask first; it is not proof.
- No external data is used, so there are no third-party sources or licences to record.
