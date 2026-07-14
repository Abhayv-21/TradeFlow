# TradeFlow v4 — Delivery Notes

## What's in this package

```
tradeflow_v4/
├── sql/
│   └── tradeflow_patch_v4.sql     ← Run this FIRST in Supabase
├── python_backend/
│   ├── server.py                  ← Main entry point
│   ├── db.py                      ← PostgreSQL pool
│   ├── requirements.txt
│   ├── .env.example               ← Copy to .env and fill in credentials
│   ├── middleware/
│   │   └── auth.py                ← JWT auth helpers
│   └── routes/
│       ├── auth.py
│       ├── stocks.py
│       ├── portfolio.py
│       ├── wallet.py
│       ├── orders.py
│       ├── admin.py               ← Includes company management endpoints
│       └── company.py             ← All COMPANY role routes
└── frontend/
    └── index.html                 ← Drop-in replacement (all fixes + COMPANY UI)
```

---

## Step 1 — Run SQL Patch in Supabase

1. Open your Supabase project → **SQL Editor**
2. Paste the contents of `sql/tradeflow_patch_v4.sql`
3. Click **Run**

### What the SQL patch does:
- **Fixes `invested_value` bug** — adds alias to `v_portfolio_detail` so frontend reads correctly
- **Fixes `v_dashboard`** — adds `pending_orders` and `cancelled_orders` counts
- **Fills 90 days of price history** — makes charts smooth for all active stocks
- **Adds COMPANY role** to `users.role` constraint
- **Creates 3 new tables**: `company_profiles`, `company_announcements`, `company_financials`
- **Creates sentiment view**: `v_company_stock_sentiment`
- **Creates trigger**: auto-logs to `system_logs` when an announcement is published
- **Seeds demo COMPANY user**: `company@tradeflow.in` / `password`

---

## Step 2 — Start Python Backend

```bash
cd python_backend

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env — paste your Supabase DATABASE_URL

# Run
python server.py
```

The Python backend is a **100% drop-in replacement** for the Node.js backend.
- Same port: `4000`
- Same API routes and response shapes
- Same JWT tokens — no frontend changes needed to switch

---

## Step 3 — Replace Frontend

Replace your existing `frontend/index.html` with the one in `frontend/index.html`.

---

## Bug Fixes Included

### Bug 1: Total Invested = ₹0 on Dashboard and Portfolio
**Root cause:** The `v_portfolio_detail` SQL view returned the column as `total_invested`
but the frontend read `p.invested_value` (which was undefined → 0).

**Fix:** SQL patch adds `invested_value` as an alias. Frontend also reads
`p.invested_value || p.total_invested` as a fallback in 4 places.

### Bug 2: Orders & Trades showing Executed/Pending/Cancelled = 0
**Root cause:** Order stats were computed from the filtered list (e.g., if you
selected "EXECUTED" filter, only executed orders loaded — so pending count = 0).

**Fix:** Stats now fetch ALL orders in a separate `useData` call, independent
of the current filter selection.

### Bug 3: Market graphs look weird / spiky
**Root cause:** Some stocks only had 1–2 price data points in `stock_price_history`,
so charts showed extreme jumps or a flat line with random outliers.

**Fix:** SQL patch inserts smooth daily closing prices for every active stock for
the last 90 days (only fills gaps — won't overwrite existing data).

---

## New Feature: COMPANY Role

### Three roles in TradeFlow:

| Role | What they do |
|------|-------------|
| **USER** | Trades stocks, manages wallet and portfolio |
| **COMPANY** | Listed company's IR team — monitors their own stock |
| **ADMIN** | Full platform control |

### COMPANY portal features:
- **Company Dashboard** — price, holders, today's volume, buy/sell sentiment
- **My Stock** — 7/14/30/90-day price chart, detailed analytics
- **Announcements** — create, edit, publish regulatory disclosures (DIVIDEND, SPLIT, BONUS, RESULTS, AGM)
- **Financial Results** — upload quarterly EPS/revenue/profit data
- **Company Profile** — edit contact email, website, registered address

### Demo credentials:
| Role | Email | Password |
|------|-------|----------|
| USER | demo@tradeflow.in | password |
| ADMIN | admin@tradeflow.in | password |
| COMPANY | company@tradeflow.in | password |

### Security:
- COMPANY users **cannot** access wallet, portfolio, order placement
- All company SQL queries enforce `WHERE company_profiles.user_id = current_user_id`
- A COMPANY user can only see their own stock — enforced at the database query level

### Admin can:
- View all company profiles in **Admin Panel → Companies** tab
- Verify or revoke company verification
- Delete company profiles

---

## API Routes Added

### COMPANY routes (`/api/company/*`)
All require `Authorization: Bearer <token>` with a COMPANY-role JWT.

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/company/profile` | Fetch company profile |
| PUT | `/api/company/profile` | Edit contact_email, website, address |
| GET | `/api/company/stock/overview` | Price, holders, today's volume + sentiment |
| GET | `/api/company/stock/history?days=30` | Price history |
| GET | `/api/company/stock/sentiment` | Buy/sell ratio |
| GET | `/api/company/announcements` | List all announcements |
| POST | `/api/company/announcements` | Create announcement |
| PUT | `/api/company/announcements/:id` | Edit announcement |
| DELETE | `/api/company/announcements/:id` | Delete draft announcement |
| GET | `/api/company/financials` | List quarterly results |
| POST | `/api/company/financials` | Upload quarter result |

### Admin company routes (`/api/admin/companies/*`)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/admin/companies` | List all companies |
| POST | `/api/admin/companies` | Create company profile |
| PATCH | `/api/admin/companies/:id/verify` | Verify/unverify company |
| DELETE | `/api/admin/companies/:id` | Delete company |
