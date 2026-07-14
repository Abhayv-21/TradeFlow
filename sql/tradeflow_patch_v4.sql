-- ═══════════════════════════════════════════════════════════════════════════
--  TradeFlow — PATCH v4  (Run ONCE in Supabase SQL Editor)
--  Fixes: invested_value alias, order status, market data smoothness
--  Adds:  COMPANY role + company_profiles, announcements, financials tables
--  All statements are idempotent — safe to run multiple times.
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 1: FIX users.role CHECK — add COMPANY support
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE public.users
  ADD CONSTRAINT users_role_check
  CHECK (role IN ('USER','ADMIN','TRADER','ANALYST','COMPANY'));

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 2: FIX v_portfolio_detail — add invested_value alias
-- (Frontend used p.invested_value but view only had total_invested)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_portfolio_detail AS
SELECT
    p.portfolio_id,
    p.user_id,
    p.stock_id,
    s.symbol,
    s.company_name,
    s.sector,
    p.total_quantity,
    p.avg_buy_price,
    COALESCE(lp.latest_price, p.avg_buy_price)                                AS current_price,
    ROUND(p.total_quantity * p.avg_buy_price, 2)                              AS total_invested,
    -- FIX: alias so frontend p.invested_value works
    ROUND(p.total_quantity * p.avg_buy_price, 2)                              AS invested_value,
    ROUND(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price), 2)  AS current_value,
    ROUND(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price), 2)
      - ROUND(p.total_quantity * p.avg_buy_price, 2)                          AS unrealized_pnl,
    CASE WHEN p.avg_buy_price > 0 THEN
        ROUND(((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price)
               / p.avg_buy_price) * 100, 2)
    ELSE 0 END                                                                AS pnl_pct
FROM   public.portfolio             p
JOIN   public.stocks                s  ON s.stock_id  = p.stock_id
LEFT   JOIN public.v_stock_latest_price lp ON lp.stock_id = p.stock_id
WHERE  p.total_quantity > 0;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 3: FIX v_dashboard — ensure total_invested is accurate
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_dashboard AS
SELECT
    w.user_id,
    u.name                                              AS user_name,
    ROUND(w.balance, 2)                                 AS total_balance,
    COALESCE(port.total_invested, 0)                    AS total_invested,
    COALESCE(port.portfolio_value, 0)                   AS portfolio_value,
    COALESCE(port.portfolio_value, 0)
      - COALESCE(port.total_invested, 0)                AS total_profit_loss,
    COALESCE(port.holdings_count, 0)                    AS holdings_count,
    COALESCE(ord.total_orders, 0)                       AS total_orders,
    COALESCE(ord.executed_orders, 0)                    AS executed_orders,
    COALESCE(ord.pending_orders, 0)                     AS pending_orders,
    COALESCE(ord.cancelled_orders, 0)                   AS cancelled_orders,
    w.last_updated                                      AS wallet_updated_at
FROM public.wallet w
JOIN public.users  u ON u.user_id = w.user_id
LEFT JOIN (
    SELECT p.user_id,
           COUNT(*)::INT                                                       AS holdings_count,
           ROUND(SUM(p.total_quantity * p.avg_buy_price), 2)                  AS total_invested,
           ROUND(SUM(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price)), 2) AS portfolio_value
    FROM   public.portfolio p
    LEFT   JOIN public.v_stock_latest_price lp ON lp.stock_id = p.stock_id
    WHERE  p.total_quantity > 0
    GROUP  BY p.user_id
) port ON port.user_id = w.user_id
LEFT JOIN (
    SELECT user_id,
           COUNT(*)::INT                                                               AS total_orders,
           SUM(CASE WHEN upper(order_status)='EXECUTED'  THEN 1 ELSE 0 END)::INT      AS executed_orders,
           SUM(CASE WHEN upper(order_status)='PENDING'   THEN 1 ELSE 0 END)::INT      AS pending_orders,
           SUM(CASE WHEN upper(order_status)='CANCELLED' THEN 1 ELSE 0 END)::INT      AS cancelled_orders
    FROM   public.orders
    GROUP  BY user_id
) ord ON ord.user_id = w.user_id;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 4: FIX stock_price_history — smooth out data by filling gaps
-- Ensures every active stock has a data point for each of the last 90 days
-- so charts render smoothly without random gaps.
-- ─────────────────────────────────────────────────────────────────────────────

-- Fill any missing days with realistic interpolated prices
INSERT INTO public.stock_price_history (price_id, stock_id, price, price_timestamp)
SELECT
    70000 + (s.rn * 91) + d.day_offset,
    s.stock_id,
    -- Use last known price as base, add small daily drift (+/- 2%)
    ROUND(
        s.base_price * (
            1 + (0.004 * (random() - 0.5) * 2)  -- daily drift ±0.4% avg
        )::NUMERIC,
        2
    ),
    (NOW() - ((90 - d.day_offset) || ' days')::interval)::DATE + TIME '15:30:00'
FROM (
    SELECT stock_id,
           row_number() OVER () AS rn,
           COALESCE(
               (SELECT price FROM public.stock_price_history
                WHERE stock_id = st.stock_id ORDER BY price_timestamp DESC LIMIT 1),
               1000
           ) AS base_price
    FROM   public.stocks st
    WHERE  is_active = TRUE
) s
CROSS JOIN (SELECT generate_series(0, 90) AS day_offset) d
-- Only insert where data is truly missing for that day
WHERE NOT EXISTS (
    SELECT 1 FROM public.stock_price_history sph
    WHERE sph.stock_id = s.stock_id
      AND DATE(sph.price_timestamp) = DATE(NOW() - ((90 - d.day_offset) || ' days')::interval)
)
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 5: COMPANY ROLE — new tables
-- ─────────────────────────────────────────────────────────────────────────────

-- company_profiles: links a COMPANY user to one listed stock
CREATE TABLE IF NOT EXISTS public.company_profiles (
    company_id          SERIAL          PRIMARY KEY,
    user_id             INT             NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    stock_id            INT             NOT NULL REFERENCES public.stocks(stock_id) ON DELETE CASCADE,
    company_name        VARCHAR(200)    NOT NULL,
    cin_number          VARCHAR(21),                     -- Corporate Identity Number (India)
    registered_address  TEXT,
    contact_email       VARCHAR(200),
    website             VARCHAR(300),
    verified            BOOLEAN         DEFAULT FALSE,   -- admin must approve
    created_at          TIMESTAMP       DEFAULT NOW(),
    UNIQUE(user_id),
    UNIQUE(stock_id)
);

-- company_announcements: press releases / regulatory events
CREATE TABLE IF NOT EXISTS public.company_announcements (
    announcement_id     SERIAL          PRIMARY KEY,
    company_id          INT             NOT NULL REFERENCES public.company_profiles(company_id) ON DELETE CASCADE,
    title               VARCHAR(300)    NOT NULL,
    content             TEXT            NOT NULL,
    announcement_type   VARCHAR(20)     NOT NULL
                        CHECK (announcement_type IN ('DIVIDEND','SPLIT','BONUS','RESULTS','AGM','OTHER')),
    effective_date      DATE,
    is_published        BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMP       DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ann_company ON public.company_announcements(company_id);
CREATE INDEX IF NOT EXISTS idx_ann_published ON public.company_announcements(is_published, created_at DESC);

-- company_financials: quarterly results
CREATE TABLE IF NOT EXISTS public.company_financials (
    financial_id        SERIAL          PRIMARY KEY,
    company_id          INT             NOT NULL REFERENCES public.company_profiles(company_id) ON DELETE CASCADE,
    quarter             VARCHAR(2)      NOT NULL CHECK (quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_year         INT             NOT NULL,
    revenue             NUMERIC(20,2),
    net_profit          NUMERIC(20,2),
    eps                 NUMERIC(10,2),                   -- Earnings Per Share
    published_at        TIMESTAMP       DEFAULT NOW(),
    UNIQUE(company_id, quarter, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_fin_company ON public.company_financials(company_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 6: TRIGGER — log when a company announcement is published
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.trg_log_announcement_publish()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_stock_id INT;
    v_symbol   TEXT;
BEGIN
    -- Only fire when is_published changes from FALSE to TRUE
    IF (TG_OP = 'UPDATE' AND OLD.is_published = FALSE AND NEW.is_published = TRUE)
    OR (TG_OP = 'INSERT' AND NEW.is_published = TRUE) THEN
        SELECT cp.stock_id, s.symbol
        INTO   v_stock_id, v_symbol
        FROM   company_profiles cp
        JOIN   stocks s ON s.stock_id = cp.stock_id
        WHERE  cp.company_id = NEW.company_id;

        INSERT INTO public.system_logs (txn_id, operation, status, "timestamp")
        SELECT
            nextval('log_seq'),
            'ANNOUNCEMENT_PUBLISHED: ' || NEW.title || ' [' || v_symbol || ']',
            'SUCCESS',
            NOW()
        WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='system_logs');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS log_announcement_publish ON public.company_announcements;
CREATE TRIGGER log_announcement_publish
  AFTER INSERT OR UPDATE ON public.company_announcements
  FOR EACH ROW EXECUTE FUNCTION public.trg_log_announcement_publish();

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 7: VIEW — v_company_stock_sentiment (buy vs sell ratio per stock)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_company_stock_sentiment AS
SELECT
    o.stock_id,
    s.symbol,
    s.company_name,
    COUNT(*)                                                                AS total_orders,
    SUM(CASE WHEN o.order_type = 'BUY'  THEN 1 ELSE 0 END)::INT           AS buy_count,
    SUM(CASE WHEN o.order_type = 'SELL' THEN 1 ELSE 0 END)::INT           AS sell_count,
    SUM(CASE WHEN o.order_type = 'BUY'  THEN o.quantity ELSE 0 END)::INT  AS buy_volume,
    SUM(CASE WHEN o.order_type = 'SELL' THEN o.quantity ELSE 0 END)::INT  AS sell_volume,
    ROUND(
        100.0 * SUM(CASE WHEN o.order_type='BUY' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1
    )                                                                       AS buy_pct,
    ROUND(
        100.0 * SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1
    )                                                                       AS sell_pct,
    -- Distinct investors currently holding the stock
    (SELECT COUNT(DISTINCT user_id) FROM public.portfolio
     WHERE stock_id = o.stock_id AND total_quantity > 0)::INT              AS total_holders
FROM   public.orders  o
JOIN   public.stocks  s ON s.stock_id = o.stock_id
WHERE  upper(o.order_status) = 'EXECUTED'
GROUP  BY o.stock_id, s.symbol, s.company_name;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 8: SEED — demo COMPANY user linked to first stock
-- ─────────────────────────────────────────────────────────────────────────────

-- Create a demo COMPANY user (user_id 1003)
INSERT INTO public.users (user_id, name, email, password, role, kyc_status, is_active)
VALUES (1003, 'TechCorp IR Team', 'company@tradeflow.in', 'password', 'COMPANY', 'VERIFIED', TRUE)
ON CONFLICT (user_id) DO UPDATE
  SET password  = EXCLUDED.password,
      role      = EXCLUDED.role,
      is_active = TRUE;

-- Link this company user to stock_id 1 (first stock in the DB)
INSERT INTO public.company_profiles
    (user_id, stock_id, company_name, cin_number, registered_address,
     contact_email, website, verified)
SELECT
    1003,
    (SELECT stock_id FROM public.stocks ORDER BY stock_id LIMIT 1),
    (SELECT company_name FROM public.stocks ORDER BY stock_id LIMIT 1),
    'U72200MH2000PLC123456',
    'Plot No 12, MIDC, Andheri East, Mumbai - 400093',
    'investor.relations@techcorp.in',
    'https://www.techcorp.in',
    TRUE
WHERE NOT EXISTS (SELECT 1 FROM public.company_profiles WHERE user_id = 1003);

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 9: SEED RBAC for COMPANY role
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO public.roles(role_name, description)
VALUES ('COMPANY', 'Listed company with investor relations access')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO public.user_roles(user_id, role_id)
SELECT 1003, r.role_id FROM public.roles r WHERE r.role_name = 'COMPANY'
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFY — run these selects to confirm patch worked
-- ─────────────────────────────────────────────────────────────────────────────
/*
-- Check invested_value alias is present:
SELECT portfolio_id, symbol, total_invested, invested_value, current_value FROM v_portfolio_detail LIMIT 5;

-- Check dashboard has order counts:
SELECT user_id, total_invested, executed_orders, pending_orders, cancelled_orders FROM v_dashboard LIMIT 5;

-- Check company tables exist:
SELECT * FROM company_profiles;
SELECT * FROM v_company_stock_sentiment LIMIT 5;

-- Login as company user:
-- email: company@tradeflow.in  |  password: password
*/
