# Shrinkage Monitor

**Finds missing stock in a retail chain, explains why it went missing, and proves the answers are right.**

## The problem

Shops lose stock. Some loss is **innocent**: a jar breaks, milk expires, a delivery box goes missing.
Some is **suspicious**: an employee keeps writing off expensive items, or records are wrong.
The task is to tell the two apart, with evidence.

Real store data is private, so the brief asks to **create realistic fake data, hide problems in it,
and build a system that finds them**, at the size of **100 stores, 5,000 products and 1 million stock movements**.

## What I built

1. **Fake store data:** stores, products, staff, shifts, and a stock logbook with one line for every sale,
   delivery, transfer, return, damage write-off and shelf count. Honest losses (damage, expiry, returns,
   lost deliveries) are included on purpose.
2. **Hidden problems,** recorded in a separate answer key that the detector never reads:

   | Planted problem | What it looks like |
   |---|---|
   | Wrong store | a delivery is booked to a different store than the shift it was posted in |
   | No reason | stock is written off with no reason given |
   | Count before sales | a shelf count is dated before sales it already includes |
   | Double loss | one lost delivery is written off by both stores |
   | Repeated write-offs | one employee writes off far more than colleagues, mostly on night shifts |
   | Unexplained loss | stock keeps going missing after the same employee handled it |
   | *Decoy (innocent)* | *a one-day fridge breakdown with many write-offs; it must not be called theft* |

3. **A detector** that finds them with rules and statistics, and explains each alert:
   who was involved, on which shift, how much stock and money, and the exact records behind it.
4. **A dashboard** (React) and **API** (FastAPI), with the data stored in **Supabase / Postgres**.

## Results (full size, 1 million movements)

| | |
|---|---|
| Problems caught | **100%** (93 of 93) |
| False alarms | **0** |
| Innocent losses called theft | **0** (fridge decoy, damaged returns and lost deliveries are all left alone) |
| Data checks | 228 checks; every integrity check passes and the stock maths balances everywhere |
| Same data every run | yes: seed `20261022`; two separate runs give identical files (hash `1c9cfea7…`) |

Proof: [results/full/](results/full/).

## Run it

**Backend** (Python 3.12):

```bash
cd backend
pip install -r requirements.txt
python -m app.pipeline.run --size small     # build the data (5 stores, ~20,000 rows, ~3 s)
python -m app                               # start the API on http://127.0.0.1:8000
```

**Frontend** (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev                                 # open http://localhost:5173
```

Optional:

```bash
python -m app.pipeline.run --size full      # the brief's size: 100 stores, 1M rows (~1 min)
python -m pytest -q                         # 11 tests
python -m app.db --size small               # load into Supabase (set DATABASE_URL in backend/.env)
```

Settings live in `backend/.env` and `frontend/.env`. Copy the `.env.example` files; everything is optional.

## The dashboard

| Tab | Shows |
|---|---|
| **Overview** | the scorecard: problems caught, innocent losses spared, stock maths |
| **Alerts** | every finding; click one for the reason, people involved and evidence |
| **Validation** | the 228 data-health checks |
| **Answer key** | each hidden problem and whether it was caught |

## Where AI / LLMs are used

- **Realistic names and notes** (products, brands, staff notes) were written once by an LLM and saved
  ([vocab.json](backend/llm_cache/vocab.json)), so every run stays identical.
- **"Explain in plain English" button:** Gemini (or any LLM) rewrites an alert for a store manager.
  It only sees the alert's facts and never invents numbers. Needs `LLM_API_KEY` and `LLM_MODEL` in `backend/.env`.
- **Detection does not use an LLM on purpose:** it must be exact, repeatable and measurable.
- An AI coding assistant helped build this project.

## Project structure

```
backend/
  app/pipeline/   data generator, checks, detector, scoring  (the core)
  app/            API, database, settings
  tests/          automated tests
frontend/         React dashboard
docs/             data dictionary, database schemas, full technical details
results/          scores and alerts from the full and medium runs
sample_output/    a small run's data to browse without running anything
```

## More detail

- [docs/DETAILS.md](docs/DETAILS.md): how the data is built, every detection rule, all checks, API and database
- [docs/data_dictionary.md](docs/data_dictionary.md): every field of every table
- Limitations: the data is synthetic, so thresholds would need tuning on real data, and "last person to handle the
  stock" is a lead for an investigator, not proof of guilt.
