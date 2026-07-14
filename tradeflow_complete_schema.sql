-- =============================================================================
-- TradeFlow v4 — Complete PostgreSQL Schema
-- Includes: Tables, Indexes, Views (by role), Triggers, Functions
-- Target: Supabase / PostgreSQL 15+
-- =============================================================================

-- ============================================================================
-- SECTION 1: CORE TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id     SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    email       TEXT        NOT NULL UNIQUE,
    password    TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'USER'    CHECK (role IN ('USER','ADMIN','COMPANY')),
    kyc_status  TEXT        NOT NULL DEFAULT 'PENDING' CHECK (kyc_status IN ('PENDING','VERIFIED','REJECTED')),
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallet (
    wallet_id    SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    balance      NUMERIC(18,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    transaction_id  SERIAL PRIMARY KEY,
    wallet_id       INTEGER       NOT NULL REFERENCES wallet(wallet_id) ON DELETE CASCADE,
    amount          NUMERIC(18,2) NOT NULL,
    transaction_type TEXT         NOT NULL CHECK (transaction_type IN ('CREDIT','DEBIT')),
    description     TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stocks (
    stock_id     SERIAL PRIMARY KEY,
    symbol       TEXT    NOT NULL UNIQUE,
    company_name TEXT    NOT NULL,
    sector       TEXT    NOT NULL DEFAULT 'General',
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_price_history (
    price_id        SERIAL PRIMARY KEY,
    stock_id        INTEGER       NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    price           NUMERIC(18,2) NOT NULL CHECK (price > 0),
    price_timestamp TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     SERIAL PRIMARY KEY,
    user_id      INTEGER       NOT NULL REFERENCES users(user_id)  ON DELETE CASCADE,
    stock_id     INTEGER       NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    order_type   TEXT          NOT NULL CHECK (order_type IN ('BUY','SELL')),
    order_price  NUMERIC(18,2) NOT NULL CHECK (order_price > 0),
    quantity     INTEGER       NOT NULL CHECK (quantity > 0),
    order_status TEXT          NOT NULL DEFAULT 'PENDING' CHECK (order_status IN ('PENDING','EXECUTED','CANCELLED')),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id           SERIAL PRIMARY KEY,
    order_id           INTEGER       NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    executed_price     NUMERIC(18,2) NOT NULL,
    executed_quantity  INTEGER       NOT NULL,
    trade_time         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio (
    portfolio_id   SERIAL PRIMARY KEY,
    user_id        INTEGER       NOT NULL REFERENCES users(user_id)  ON DELETE CASCADE,
    stock_id       INTEGER       NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    total_quantity INTEGER       NOT NULL DEFAULT 0 CHECK (total_quantity >= 0),
    avg_buy_price  NUMERIC(18,4) NOT NULL DEFAULT 0,
    UNIQUE (user_id, stock_id)
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    pt_id            SERIAL PRIMARY KEY,
    portfolio_id     INTEGER     NOT NULL REFERENCES portfolio(portfolio_id) ON DELETE CASCADE,
    order_id         INTEGER     REFERENCES orders(order_id),
    trade_id         INTEGER     REFERENCES trades(trade_id),
    quantity_change  INTEGER     NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_profiles (
    company_id           SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    stock_id             INTEGER NOT NULL UNIQUE REFERENCES stocks(stock_id) ON DELETE CASCADE,
    company_name         TEXT    NOT NULL,
    cin_number           TEXT,
    registered_address   TEXT,
    contact_email        TEXT,
    website              TEXT,
    verified             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_announcements (
    announcement_id   SERIAL PRIMARY KEY,
    company_id        INTEGER     NOT NULL REFERENCES company_profiles(company_id) ON DELETE CASCADE,
    title             TEXT        NOT NULL,
    content           TEXT        NOT NULL,
    announcement_type TEXT        NOT NULL DEFAULT 'OTHER'
                      CHECK (announcement_type IN ('DIVIDEND','SPLIT','BONUS','RESULTS','AGM','OTHER')),
    effective_date    DATE,
    is_published      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_financials (
    financial_id  SERIAL PRIMARY KEY,
    company_id    INTEGER       NOT NULL REFERENCES company_profiles(company_id) ON DELETE CASCADE,
    quarter       TEXT          NOT NULL CHECK (quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_year   INTEGER       NOT NULL,
    revenue       NUMERIC(18,2) NOT NULL,
    net_profit    NUMERIC(18,2) NOT NULL,
    eps           NUMERIC(10,4) NOT NULL,
    published_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, quarter, fiscal_year)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id    SERIAL PRIMARY KEY,
    user_id     INTEGER     REFERENCES users(user_id) ON DELETE SET NULL,
    action      TEXT        NOT NULL,
    resource    TEXT        NOT NULL,
    resource_id INTEGER,
    details     TEXT,
    ip_address  TEXT,
    status      TEXT        NOT NULL DEFAULT 'SUCCESS' CHECK (status IN ('SUCCESS','FAILED','WARNING')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS database_transactions (
    txn_id     SERIAL PRIMARY KEY,
    user_id    INTEGER     REFERENCES users(user_id) ON DELETE SET NULL,
    txn_state  TEXT        NOT NULL DEFAULT 'ACTIVE' CHECK (txn_state IN ('ACTIVE','COMMITTED','ROLLED_BACK')),
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS system_logs (
    log_id    SERIAL PRIMARY KEY,
    txn_id    INTEGER REFERENCES database_transactions(txn_id) ON DELETE SET NULL,
    operation TEXT        NOT NULL,
    status    TEXT        NOT NULL DEFAULT 'SUCCESS',
    details   TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS locks (
    lock_id       SERIAL PRIMARY KEY,
    txn_id        INTEGER REFERENCES database_transactions(txn_id) ON DELETE CASCADE,
    resource_type TEXT    NOT NULL,
    resource_id   INTEGER,
    lock_mode     TEXT    NOT NULL DEFAULT 'EXCLUSIVE' CHECK (lock_mode IN ('SHARED','EXCLUSIVE')),
    acquired_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_config (
    config_id    SERIAL PRIMARY KEY,
    config_key   TEXT NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    description  TEXT,
    updated_by   INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================================
-- SECTION 2: INDEXES
-- ============================================================================

-- Users
CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role        ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active   ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_kyc_status  ON users(kyc_status);
CREATE INDEX IF NOT EXISTS idx_users_created_at  ON users(created_at DESC);

-- Wallet
CREATE INDEX IF NOT EXISTS idx_wallet_user_id    ON wallet(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_txn_wallet ON wallet_transactions(wallet_id);
CREATE INDEX IF NOT EXISTS idx_wallet_txn_date   ON wallet_transactions(created_at DESC);

-- Stocks & Price History
CREATE INDEX IF NOT EXISTS idx_stocks_symbol     ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector     ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_active     ON stocks(is_active);
CREATE INDEX IF NOT EXISTS idx_price_stock_ts    ON stock_price_history(stock_id, price_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_price_ts          ON stock_price_history(price_timestamp DESC);

-- Orders
CREATE INDEX IF NOT EXISTS idx_orders_user_id    ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_stock_id   ON orders(stock_id);
CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_orders_type       ON orders(order_type);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_user_stock ON orders(user_id, stock_id);

-- Trades
CREATE INDEX IF NOT EXISTS idx_trades_order_id   ON trades(order_id);
CREATE INDEX IF NOT EXISTS idx_trades_trade_time ON trades(trade_time DESC);

-- Portfolio
CREATE INDEX IF NOT EXISTS idx_portfolio_user    ON portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_stock   ON portfolio(stock_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_qty     ON portfolio(total_quantity) WHERE total_quantity > 0;

-- Company
CREATE INDEX IF NOT EXISTS idx_company_user      ON company_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_company_stock     ON company_profiles(stock_id);
CREATE INDEX IF NOT EXISTS idx_ann_company       ON company_announcements(company_id);
CREATE INDEX IF NOT EXISTS idx_ann_published     ON company_announcements(is_published, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fin_company       ON company_financials(company_id, fiscal_year DESC, quarter);

-- Audit & Logs
CREATE INDEX IF NOT EXISTS idx_audit_user        ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action      ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource    ON audit_logs(resource);
CREATE INDEX IF NOT EXISTS idx_audit_created     ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_txn        ON system_logs(txn_id);
CREATE INDEX IF NOT EXISTS idx_syslog_ts         ON system_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dbtxn_user        ON database_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_dbtxn_state       ON database_transactions(txn_state);


-- ============================================================================
-- SECTION 3: VIEWS (organized by role)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 3A: SHARED / PUBLIC VIEWS (accessible to all authenticated roles)
-- ---------------------------------------------------------------------------

-- Latest price per stock (used across all roles)
CREATE OR REPLACE VIEW v_stock_latest_price AS
SELECT DISTINCT ON (sph.stock_id)
    s.stock_id,
    s.symbol,
    s.company_name,
    s.sector,
    sph.price        AS latest_price,
    sph.price_timestamp AS last_updated
FROM   stock_price_history sph
JOIN   stocks s ON s.stock_id = sph.stock_id
ORDER  BY sph.stock_id, sph.price_timestamp DESC;

-- ---------------------------------------------------------------------------
-- 3B: USER ROLE VIEWS
-- ---------------------------------------------------------------------------

-- Full portfolio detail view (shows PnL per holding)
CREATE OR REPLACE VIEW v_portfolio_detail AS
SELECT
    p.portfolio_id,
    p.user_id,
    p.stock_id,
    s.symbol,
    s.company_name,
    s.sector,
    p.total_quantity,
    p.avg_buy_price,
    COALESCE(lp.latest_price, p.avg_buy_price)                         AS current_price,
    ROUND(p.avg_buy_price * p.total_quantity, 2)                       AS invested_value,
    ROUND(COALESCE(lp.latest_price, p.avg_buy_price) * p.total_quantity, 2) AS current_value,
    ROUND((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price) * p.total_quantity, 2) AS unrealized_pnl,
    ROUND(
        ((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price)
        / NULLIF(p.avg_buy_price, 0)) * 100, 2
    )                                                                    AS pnl_pct
FROM   portfolio p
JOIN   stocks s ON s.stock_id = p.stock_id
LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
WHERE  p.total_quantity > 0;

-- User order history with full detail
CREATE OR REPLACE VIEW v_orders AS
SELECT
    o.order_id,
    o.user_id,
    u.name     AS user_name,
    u.email    AS user_email,
    o.stock_id,
    s.symbol,
    s.company_name,
    o.order_type,
    o.order_price,
    o.quantity,
    ROUND(o.order_price * o.quantity, 2) AS total_value,
    o.order_status,
    o.created_at
FROM   orders o
JOIN   users  u ON u.user_id  = o.user_id
JOIN   stocks s ON s.stock_id = o.stock_id;

-- User trade history with full detail
CREATE OR REPLACE VIEW v_trades AS
SELECT
    t.trade_id,
    t.order_id,
    o.user_id,
    u.name     AS user_name,
    o.stock_id,
    s.symbol,
    s.company_name,
    o.order_type                                         AS trade_type,
    t.executed_quantity                                  AS quantity,
    t.executed_price                                     AS price,
    ROUND(t.executed_price * t.executed_quantity, 2)    AS total_value,
    t.trade_time                                         AS executed_at
FROM   trades t
JOIN   orders  o ON o.order_id  = t.order_id
JOIN   users   u ON u.user_id   = o.user_id
JOIN   stocks  s ON s.stock_id  = o.stock_id;

-- User wallet dashboard (balance + totals)
CREATE OR REPLACE VIEW v_dashboard AS
SELECT
    u.user_id,
    u.name,
    u.email,
    u.role,
    COALESCE(w.balance, 0)                                       AS wallet_balance,
    COALESCE(ptf.total_invested, 0)                              AS total_invested,
    COALESCE(ptf.current_value, 0)                               AS portfolio_value,
    COALESCE(ord.total_orders, 0)                                AS total_orders,
    COALESCE(ord.executed_orders, 0)                             AS executed_orders
FROM   users u
LEFT   JOIN wallet w ON w.user_id = u.user_id
LEFT   JOIN (
    SELECT user_id,
           SUM(ROUND(avg_buy_price * total_quantity, 2)) AS total_invested,
           SUM(ROUND(COALESCE(lp.latest_price, p.avg_buy_price) * p.total_quantity, 2)) AS current_value
    FROM   portfolio p
    LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
    GROUP  BY user_id
) ptf ON ptf.user_id = u.user_id
LEFT   JOIN (
    SELECT user_id,
           COUNT(*)                                              AS total_orders,
           SUM(CASE WHEN upper(order_status)='EXECUTED' THEN 1 ELSE 0 END) AS executed_orders
    FROM   orders
    GROUP  BY user_id
) ord ON ord.user_id = u.user_id;

-- ---------------------------------------------------------------------------
-- 3C: COMPANY ROLE VIEWS
-- ---------------------------------------------------------------------------

-- Company stock sentiment (buy/sell pressure)
CREATE OR REPLACE VIEW v_company_stock_sentiment AS
SELECT
    o.stock_id,
    s.symbol,
    s.company_name,
    COUNT(*)                                                            AS total_orders,
    SUM(CASE WHEN o.order_type='BUY'  THEN 1 ELSE 0 END)             AS buy_count,
    SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END)             AS sell_count,
    SUM(CASE WHEN o.order_type='BUY'  THEN o.quantity ELSE 0 END)    AS buy_volume,
    SUM(CASE WHEN o.order_type='SELL' THEN o.quantity ELSE 0 END)    AS sell_volume,
    ROUND(100.0 * SUM(CASE WHEN o.order_type='BUY'  THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS buy_pct,
    ROUND(100.0 * SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS sell_pct,
    (SELECT COUNT(DISTINCT user_id) FROM portfolio
     WHERE  stock_id = o.stock_id AND total_quantity > 0)             AS total_holders
FROM   orders o
JOIN   stocks s ON s.stock_id = o.stock_id
WHERE  upper(o.order_status) = 'EXECUTED'
GROUP  BY o.stock_id, s.symbol, s.company_name;

-- Company investor breakdown
CREATE OR REPLACE VIEW v_company_investor_summary AS
SELECT
    p.stock_id,
    s.symbol,
    COUNT(DISTINCT p.user_id)                   AS total_investors,
    SUM(p.total_quantity)                       AS total_shares_held,
    ROUND(AVG(p.avg_buy_price), 2)              AS avg_investor_price,
    MIN(p.avg_buy_price)                        AS min_buy_price,
    MAX(p.avg_buy_price)                        AS max_buy_price,
    SUM(ROUND(p.avg_buy_price * p.total_quantity, 2)) AS total_invested_value
FROM   portfolio p
JOIN   stocks s ON s.stock_id = p.stock_id
WHERE  p.total_quantity > 0
GROUP  BY p.stock_id, s.symbol;

-- Company daily trading activity
CREATE OR REPLACE VIEW v_company_daily_activity AS
SELECT
    o.stock_id,
    s.symbol,
    DATE(t.trade_time)                                AS trade_date,
    COUNT(t.trade_id)                                 AS trade_count,
    SUM(t.executed_quantity)                          AS volume,
    ROUND(SUM(t.executed_price * t.executed_quantity), 2) AS turnover,
    MIN(t.executed_price)                             AS day_low,
    MAX(t.executed_price)                             AS day_high,
    (SELECT t2.executed_price FROM trades t2
     JOIN orders o2 ON o2.order_id = t2.order_id
     WHERE o2.stock_id = o.stock_id AND DATE(t2.trade_time) = DATE(t.trade_time)
     ORDER BY t2.trade_time ASC LIMIT 1)              AS open_price,
    (SELECT t2.executed_price FROM trades t2
     JOIN orders o2 ON o2.order_id = t2.order_id
     WHERE o2.stock_id = o.stock_id AND DATE(t2.trade_time) = DATE(t.trade_time)
     ORDER BY t2.trade_time DESC LIMIT 1)             AS close_price
FROM   trades t
JOIN   orders  o ON o.order_id  = t.order_id
JOIN   stocks  s ON s.stock_id  = o.stock_id
GROUP  BY o.stock_id, s.symbol, DATE(t.trade_time);

-- ---------------------------------------------------------------------------
-- 3D: ADMIN ROLE VIEWS
-- ---------------------------------------------------------------------------

-- Full admin user overview
CREATE OR REPLACE VIEW v_admin_user_overview AS
SELECT
    u.user_id,
    u.name,
    u.email,
    u.role,
    u.kyc_status,
    u.is_active,
    u.last_login,
    u.created_at,
    COALESCE(w.balance, 0)           AS wallet_balance,
    COALESCE(o.total_orders, 0)      AS total_orders,
    COALESCE(o.executed_orders, 0)   AS executed_orders,
    COALESCE(o.pending_orders, 0)    AS pending_orders,
    COALESCE(p.holdings_count, 0)    AS holdings_count,
    COALESCE(p.portfolio_value, 0)   AS portfolio_value
FROM   users u
LEFT   JOIN wallet w ON w.user_id = u.user_id
LEFT   JOIN (
    SELECT user_id,
           COUNT(*)                                                    AS total_orders,
           SUM(CASE WHEN upper(order_status)='EXECUTED' THEN 1 ELSE 0 END) AS executed_orders,
           SUM(CASE WHEN upper(order_status)='PENDING'  THEN 1 ELSE 0 END) AS pending_orders
    FROM   orders GROUP BY user_id
) o ON o.user_id = u.user_id
LEFT   JOIN (
    SELECT p.user_id,
           COUNT(DISTINCT p.stock_id)                                AS holdings_count,
           SUM(COALESCE(lp.latest_price, p.avg_buy_price) * p.total_quantity) AS portfolio_value
    FROM   portfolio p
    LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
    WHERE  p.total_quantity > 0
    GROUP  BY p.user_id
) p ON p.user_id = u.user_id;

-- Admin platform stats (single-row summary)
CREATE OR REPLACE VIEW v_admin_platform_stats AS
SELECT
    (SELECT COUNT(*) FROM users)                                              AS total_users,
    (SELECT COUNT(*) FROM users WHERE is_active = TRUE)                      AS active_users,
    (SELECT COUNT(*) FROM users WHERE role = 'COMPANY')                      AS company_users,
    (SELECT COUNT(*) FROM orders)                                             AS total_orders,
    (SELECT COUNT(*) FROM orders WHERE upper(order_status)='EXECUTED')       AS executed_orders,
    (SELECT COUNT(*) FROM orders WHERE upper(order_status)='PENDING')        AS pending_orders,
    (SELECT COUNT(*) FROM trades)                                             AS total_trades,
    (SELECT COALESCE(SUM(executed_price * executed_quantity), 0) FROM trades) AS total_volume,
    (SELECT COALESCE(SUM(balance), 0) FROM wallet)                           AS total_wallet_balance,
    (SELECT COUNT(*) FROM stocks WHERE is_active = TRUE)                     AS active_stocks,
    (SELECT COUNT(*) FROM portfolio WHERE total_quantity > 0)                AS active_holdings,
    (SELECT COUNT(*) FROM audit_logs WHERE created_at > NOW() - INTERVAL '24 hours') AS audit_events_24h,
    (SELECT COUNT(*) FROM audit_logs WHERE status='FAILED'
     AND created_at > NOW() - INTERVAL '24 hours')                          AS failed_events_24h;

-- Admin stock overview with trading activity
CREATE OR REPLACE VIEW v_admin_stock_overview AS
SELECT
    s.stock_id,
    s.symbol,
    s.company_name,
    s.sector,
    s.is_active,
    COALESCE(lp.latest_price, 0)     AS current_price,
    lp.last_updated                  AS last_price_update,
    (SELECT COUNT(*) FROM orders o WHERE o.stock_id = s.stock_id)            AS total_orders,
    (SELECT COUNT(*) FROM orders o WHERE o.stock_id = s.stock_id
     AND upper(o.order_status)='EXECUTED')                                   AS executed_orders,
    (SELECT COUNT(DISTINCT user_id) FROM portfolio
     WHERE stock_id = s.stock_id AND total_quantity > 0)                     AS total_holders,
    (SELECT COALESCE(SUM(t.executed_quantity), 0)
     FROM trades t JOIN orders o ON o.order_id = t.order_id
     WHERE o.stock_id = s.stock_id
     AND t.trade_time > NOW() - INTERVAL '1 day')                           AS volume_24h,
    (SELECT price FROM stock_price_history
     WHERE stock_id = s.stock_id
     AND price_timestamp < NOW() - INTERVAL '1 day'
     ORDER BY price_timestamp DESC LIMIT 1)                                  AS prev_close
FROM   stocks s
LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = s.stock_id;

-- Portfolio ID helper view (for portfolio routes)
CREATE OR REPLACE VIEW v_portfolio_id AS
SELECT portfolio_id, user_id, stock_id FROM portfolio;


-- ============================================================================
-- SECTION 4: FUNCTIONS
-- ============================================================================

-- fn_get_user_portfolio: Returns full portfolio for a user
CREATE OR REPLACE FUNCTION fn_get_user_portfolio(p_user_id INTEGER)
RETURNS TABLE (
    stock_id       INTEGER,
    symbol         TEXT,
    company_name   TEXT,
    sector         TEXT,
    total_quantity INTEGER,
    avg_buy_price  NUMERIC,
    current_price  NUMERIC,
    invested_value NUMERIC,
    current_value  NUMERIC,
    unrealized_pnl NUMERIC,
    pnl_pct        NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT
        p.stock_id, s.symbol, s.company_name, s.sector,
        p.total_quantity, p.avg_buy_price,
        COALESCE(lp.latest_price, p.avg_buy_price),
        ROUND(p.avg_buy_price * p.total_quantity, 2),
        ROUND(COALESCE(lp.latest_price, p.avg_buy_price) * p.total_quantity, 2),
        ROUND((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price) * p.total_quantity, 2),
        ROUND(((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price) / NULLIF(p.avg_buy_price,0)) * 100, 2)
    FROM   portfolio p
    JOIN   stocks s ON s.stock_id = p.stock_id
    LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
    WHERE  p.user_id = p_user_id AND p.total_quantity > 0
    ORDER  BY s.symbol;
$$;

-- fn_stock_price_change: Returns % price change over N days
CREATE OR REPLACE FUNCTION fn_stock_price_change(p_stock_id INTEGER, p_days INTEGER DEFAULT 1)
RETURNS NUMERIC LANGUAGE SQL STABLE AS $$
    WITH
    current_p AS (
        SELECT price FROM stock_price_history
        WHERE  stock_id = p_stock_id
        ORDER  BY price_timestamp DESC LIMIT 1
    ),
    old_p AS (
        SELECT price FROM stock_price_history
        WHERE  stock_id = p_stock_id
          AND  price_timestamp <= NOW() - (p_days || ' days')::INTERVAL
        ORDER  BY price_timestamp DESC LIMIT 1
    )
    SELECT ROUND(((c.price - o.price) / NULLIF(o.price, 0)) * 100, 2)
    FROM   current_p c, old_p o;
$$;

-- fn_user_total_pnl: Returns total unrealized PnL for a user
CREATE OR REPLACE FUNCTION fn_user_total_pnl(p_user_id INTEGER)
RETURNS NUMERIC LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(
        SUM(ROUND((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price) * p.total_quantity, 2)),
        0
    )
    FROM   portfolio p
    LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
    WHERE  p.user_id = p_user_id AND p.total_quantity > 0;
$$;

-- fn_top_gainers: Returns top N gaining stocks
CREATE OR REPLACE FUNCTION fn_top_gainers(p_limit INTEGER DEFAULT 5)
RETURNS TABLE (
    stock_id     INTEGER,
    symbol       TEXT,
    company_name TEXT,
    current_price NUMERIC,
    prev_price    NUMERIC,
    change_pct    NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT
        s.stock_id, s.symbol, s.company_name,
        lp.latest_price::NUMERIC,
        ph.prev_price::NUMERIC,
        ROUND(((lp.latest_price - ph.prev_price) / NULLIF(ph.prev_price, 0)) * 100, 2)
    FROM   stocks s
    JOIN   v_stock_latest_price lp ON lp.stock_id = s.stock_id
    JOIN   LATERAL (
        SELECT price AS prev_price FROM stock_price_history
        WHERE  stock_id = s.stock_id
          AND  price_timestamp < NOW() - INTERVAL '1 day'
        ORDER  BY price_timestamp DESC LIMIT 1
    ) ph ON TRUE
    WHERE  s.is_active = TRUE
    ORDER  BY change_pct DESC NULLS LAST
    LIMIT  p_limit;
$$;

-- fn_company_stats: Returns trading stats for a company's stock
CREATE OR REPLACE FUNCTION fn_company_stats(p_stock_id INTEGER)
RETURNS TABLE (
    total_orders   BIGINT,
    total_volume   BIGINT,
    total_value    NUMERIC,
    unique_holders BIGINT,
    buy_pressure   NUMERIC,
    sell_pressure  NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT
        COUNT(DISTINCT o.order_id),
        COALESCE(SUM(t.executed_quantity), 0)::BIGINT,
        COALESCE(ROUND(SUM(t.executed_price * t.executed_quantity), 2), 0),
        COUNT(DISTINCT p.user_id),
        ROUND(100.0 * SUM(CASE WHEN o.order_type='BUY'  THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1),
        ROUND(100.0 * SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1)
    FROM   orders o
    LEFT   JOIN trades t ON t.order_id = o.order_id
    LEFT   JOIN portfolio p ON p.stock_id = o.stock_id AND p.total_quantity > 0
    WHERE  o.stock_id = p_stock_id AND upper(o.order_status) = 'EXECUTED';
$$;


-- ============================================================================
-- SECTION 5: TRIGGERS
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 5A: Audit log trigger — logs user-facing mutations automatically
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_audit_orders()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (user_id, action, resource, resource_id, details, status)
        VALUES (NEW.user_id, 'ORDER_PLACED', 'orders', NEW.order_id,
                'Type: ' || NEW.order_type || ', Stock: ' || NEW.stock_id::TEXT ||
                ', Qty: ' || NEW.quantity::TEXT || ', Price: ' || NEW.order_price::TEXT,
                'SUCCESS');
    ELSIF TG_OP = 'UPDATE' AND NEW.order_status = 'CANCELLED' THEN
        INSERT INTO audit_logs (user_id, action, resource, resource_id, details, status)
        VALUES (NEW.user_id, 'ORDER_CANCELLED', 'orders', NEW.order_id,
                'Cancelled order for stock ' || NEW.stock_id::TEXT, 'SUCCESS');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_orders ON orders;
CREATE TRIGGER trg_audit_orders
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION trg_fn_audit_orders();

-- ---------------------------------------------------------------------------
-- 5B: Wallet audit trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_audit_wallet()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.balance IS DISTINCT FROM NEW.balance THEN
        INSERT INTO audit_logs (user_id, action, resource, resource_id, details, status)
        VALUES (NEW.user_id,
                CASE WHEN NEW.balance > OLD.balance THEN 'WALLET_CREDIT' ELSE 'WALLET_DEBIT' END,
                'wallet', NEW.wallet_id,
                'Balance changed from ' || OLD.balance::TEXT || ' to ' || NEW.balance::TEXT,
                'SUCCESS');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_wallet ON wallet;
CREATE TRIGGER trg_audit_wallet
AFTER UPDATE ON wallet
FOR EACH ROW EXECUTE FUNCTION trg_fn_audit_wallet();

-- ---------------------------------------------------------------------------
-- 5C: Auto-update wallet.last_updated on balance change
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_wallet_updated()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_wallet_last_updated ON wallet;
CREATE TRIGGER trg_wallet_last_updated
BEFORE UPDATE ON wallet
FOR EACH ROW EXECUTE FUNCTION trg_fn_wallet_updated();

-- ---------------------------------------------------------------------------
-- 5D: Auto-log system event on DB transaction state change
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_dbtxn_log()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.txn_state = 'ACTIVE' THEN
        INSERT INTO system_logs (txn_id, operation, status, details)
        VALUES (NEW.txn_id,
                'TRANSACTION_' || NEW.txn_state,
                CASE NEW.txn_state WHEN 'COMMITTED' THEN 'SUCCESS' ELSE 'FAILED' END,
                'Transaction ' || NEW.txn_id::TEXT || ' ' || NEW.txn_state ||
                ' (duration: ' || ROUND(EXTRACT(EPOCH FROM (COALESCE(NEW.end_time, NOW()) - NEW.start_time)) * 1000) || 'ms)');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dbtxn_log ON database_transactions;
CREATE TRIGGER trg_dbtxn_log
AFTER UPDATE ON database_transactions
FOR EACH ROW EXECUTE FUNCTION trg_fn_dbtxn_log();

-- ---------------------------------------------------------------------------
-- 5E: Announcement updated_at auto-stamp
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_ann_updated()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ann_updated_at ON company_announcements;
CREATE TRIGGER trg_ann_updated_at
BEFORE UPDATE ON company_announcements
FOR EACH ROW EXECUTE FUNCTION trg_fn_ann_updated();

-- ---------------------------------------------------------------------------
-- 5F: Prevent duplicate active portfolio entries (safety check)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_portfolio_positive()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.total_quantity < 0 THEN
        RAISE EXCEPTION 'Portfolio quantity cannot be negative (stock_id=%, user_id=%)',
                        NEW.stock_id, NEW.user_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_portfolio_positive ON portfolio;
CREATE TRIGGER trg_portfolio_positive
BEFORE INSERT OR UPDATE ON portfolio
FOR EACH ROW EXECUTE FUNCTION trg_fn_portfolio_positive();


-- ============================================================================
-- SECTION 6: ROW-LEVEL SECURITY (RLS) — Role-based access control
-- ============================================================================
-- NOTE: Enable RLS in Supabase dashboard, then apply these policies.
-- These policies assume you pass user_id via app_settings or JWT claims.

-- Example: Enable RLS on orders (uncomment to activate)
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY orders_user_isolation ON orders
--   FOR ALL TO authenticated
--   USING (user_id = current_setting('app.user_id')::INTEGER);

-- Example: Portfolio isolation
-- ALTER TABLE portfolio ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY portfolio_user_isolation ON portfolio
--   FOR ALL TO authenticated
--   USING (user_id = current_setting('app.user_id')::INTEGER);

-- Example: Wallet isolation
-- ALTER TABLE wallet ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY wallet_user_isolation ON wallet
--   FOR ALL TO authenticated
--   USING (user_id = current_setting('app.user_id')::INTEGER);


-- ============================================================================
-- SECTION 7: ROLE-BASED API PERMISSIONS REFERENCE
-- ============================================================================
--
-- USER role can access:
--   GET  /api/stocks                  → v_stock_latest_price (read all)
--   GET  /api/stocks/:id/history      → stock_price_history (read)
--   GET  /api/orders                  → v_orders WHERE user_id=self
--   POST /api/orders                  → INSERT orders, trades, UPDATE portfolio/wallet
--   GET  /api/portfolio               → v_portfolio_detail WHERE user_id=self
--   GET  /api/wallet                  → wallet WHERE user_id=self
--   POST /api/wallet/deposit          → UPDATE wallet, INSERT wallet_transactions
--   POST /api/wallet/withdraw         → UPDATE wallet, INSERT wallet_transactions
--
-- COMPANY role can access (own stock only):
--   GET  /api/company/profile         → company_profiles WHERE user_id=self
--   PUT  /api/company/profile         → UPDATE company_profiles WHERE user_id=self
--   GET  /api/company/stock/overview  → v_admin_stock_overview WHERE stock_id=own
--   GET  /api/company/stock/history   → stock_price_history WHERE stock_id=own
--   GET  /api/company/stock/sentiment → v_company_stock_sentiment WHERE stock_id=own
--   GET  /api/company/announcements   → company_announcements WHERE company_id=own
--   POST/PUT/DELETE /api/company/announcements → CRUD on company_announcements
--   GET  /api/company/financials      → company_financials WHERE company_id=own
--   POST /api/company/financials      → INSERT/UPDATE company_financials
--
-- ADMIN role can access (all data):
--   GET  /api/admin/stats             → v_admin_platform_stats
--   GET  /api/admin/users             → v_admin_user_overview (all users)
--   PATCH/DELETE /api/admin/users/:id → UPDATE/soft-delete users
--   GET  /api/admin/stocks            → v_admin_stock_overview (all stocks)
--   POST /api/admin/stocks            → INSERT stocks, stock_price_history
--   GET  /api/admin/orders            → v_orders (all orders)
--   GET  /api/admin/trades            → v_trades (all trades)
--   GET  /api/admin/wallets           → wallet + wallet_transactions (all)
--   GET  /api/admin/audit             → audit_logs (all)
--   GET  /api/admin/logs              → system_logs + database_transactions
--   GET  /api/admin/db-transactions   → database_transactions (all)
--   GET  /api/admin/companies         → company_profiles (all)
--   GET  /api/admin/insights          → fn_top_gainers, v_admin_stock_overview
--   GET/PUT /api/admin/config         → system_config
--
-- =============================================================================
-- END OF FILE
-- =============================================================================
