"""
init_db.py — Create SQLite schema and seed demo data for TradeFlow.
Run automatically on first server startup (if DB does not exist).
"""

import os
import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = os.getenv('SQLITE_PATH', 'tradeflow.db')
DB_PATH = os.path.join(os.path.dirname(__file__), DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    email        TEXT    NOT NULL UNIQUE,
    password     TEXT    NOT NULL,
    role         TEXT    NOT NULL DEFAULT 'USER',
    kyc_status   TEXT    NOT NULL DEFAULT 'VERIFIED',
    is_active    INTEGER NOT NULL DEFAULT 1,
    last_login   TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wallet (
    wallet_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    balance      REAL    NOT NULL DEFAULT 0,
    last_updated TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id        INTEGER NOT NULL REFERENCES wallet(wallet_id) ON DELETE CASCADE,
    amount           REAL    NOT NULL,
    transaction_type TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stocks (
    stock_id     INTEGER PRIMARY KEY,
    symbol       TEXT    NOT NULL UNIQUE,
    company_name TEXT    NOT NULL,
    sector       TEXT    NOT NULL DEFAULT 'General',
    is_active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock_price_history (
    price_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    price           REAL    NOT NULL,
    price_timestamp TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    stock_id     INTEGER NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    order_type   TEXT    NOT NULL,
    order_price  REAL    NOT NULL,
    quantity     INTEGER NOT NULL,
    order_status TEXT    NOT NULL DEFAULT 'PENDING',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    executed_price     REAL    NOT NULL,
    executed_quantity  INTEGER NOT NULL,
    trade_time         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolio (
    portfolio_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    stock_id       INTEGER NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    avg_buy_price  REAL    NOT NULL DEFAULT 0,
    UNIQUE(user_id, stock_id)
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    portfolio_transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id  INTEGER NOT NULL REFERENCES portfolio(portfolio_id) ON DELETE CASCADE,
    order_id      INTEGER REFERENCES orders(order_id),
    trade_id      INTEGER REFERENCES trades(trade_id),
    quantity_change INTEGER NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_profiles (
    company_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    stock_id            INTEGER NOT NULL UNIQUE REFERENCES stocks(stock_id) ON DELETE CASCADE,
    company_name        TEXT    NOT NULL,
    cin_number          TEXT,
    registered_address  TEXT,
    contact_email       TEXT,
    website             TEXT,
    verified            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_announcements (
    announcement_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id        INTEGER NOT NULL REFERENCES company_profiles(company_id) ON DELETE CASCADE,
    title             TEXT    NOT NULL,
    content           TEXT    NOT NULL,
    announcement_type TEXT    NOT NULL,
    effective_date    TEXT,
    is_published      INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_financials (
    financial_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL REFERENCES company_profiles(company_id) ON DELETE CASCADE,
    quarter       TEXT    NOT NULL,
    fiscal_year   INTEGER NOT NULL,
    revenue       REAL,
    net_profit    REAL,
    eps           REAL,
    published_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(company_id, quarter, fiscal_year)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(user_id),
    action      TEXT,
    resource    TEXT,
    resource_id TEXT,
    details     TEXT,
    ip_address  TEXT,
    status      TEXT DEFAULT 'SUCCESS',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS system_config (
    config_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key   TEXT NOT NULL UNIQUE,
    config_value TEXT,
    updated_by   INTEGER REFERENCES users(user_id),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS system_logs (
    log_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_id    INTEGER,
    operation TEXT,
    status    TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS database_transactions (
    txn_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(user_id),
    txn_state  TEXT,
    start_time TEXT,
    end_time   TEXT
);

CREATE TABLE IF NOT EXISTS locks (
    lock_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_id        INTEGER,
    resource_type TEXT,
    lock_mode     TEXT
);
"""

VIEWS = [
    ("v_stock_latest_price", """
        SELECT sph.stock_id,
               sph.price AS latest_price,
               sph.price_timestamp
        FROM   stock_price_history sph
        WHERE  sph.price_timestamp = (
            SELECT MAX(price_timestamp) FROM stock_price_history
            WHERE  stock_id = sph.stock_id
        )
    """),
    ("v_portfolio_detail", """
        SELECT
            p.portfolio_id, p.user_id, p.stock_id,
            s.symbol, s.company_name, s.sector,
            p.total_quantity, p.avg_buy_price,
            COALESCE(lp.latest_price, p.avg_buy_price)                              AS current_price,
            ROUND(p.total_quantity * p.avg_buy_price, 2)                            AS total_invested,
            ROUND(p.total_quantity * p.avg_buy_price, 2)                            AS invested_value,
            ROUND(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price), 2) AS current_value,
            ROUND(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price), 2)
              - ROUND(p.total_quantity * p.avg_buy_price, 2)                        AS unrealized_pnl,
            CASE WHEN p.avg_buy_price > 0 THEN
                ROUND(((COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price)
                       / p.avg_buy_price) * 100, 2)
            ELSE 0 END                                                              AS pnl_pct
        FROM portfolio p
        JOIN stocks s ON s.stock_id = p.stock_id
        LEFT JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
        WHERE p.total_quantity > 0
    """),
    ("v_dashboard", """
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
        FROM wallet w
        JOIN users u ON u.user_id = w.user_id
        LEFT JOIN (
            SELECT p.user_id,
                   COUNT(*)                                                               AS holdings_count,
                   ROUND(SUM(p.total_quantity * p.avg_buy_price), 2)                     AS total_invested,
                   ROUND(SUM(p.total_quantity * COALESCE(lp.latest_price, p.avg_buy_price)), 2) AS portfolio_value
            FROM   portfolio p
            LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
            WHERE  p.total_quantity > 0
            GROUP  BY p.user_id
        ) port ON port.user_id = w.user_id
        LEFT JOIN (
            SELECT user_id,
                   COUNT(*) AS total_orders,
                   SUM(CASE WHEN upper(order_status)='EXECUTED'  THEN 1 ELSE 0 END) AS executed_orders,
                   SUM(CASE WHEN upper(order_status)='PENDING'   THEN 1 ELSE 0 END) AS pending_orders,
                   SUM(CASE WHEN upper(order_status)='CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
            FROM   orders
            GROUP  BY user_id
        ) ord ON ord.user_id = w.user_id
    """),
    ("v_company_stock_sentiment", """
        SELECT
            o.stock_id,
            s.symbol,
            s.company_name,
            COUNT(*)                                                          AS total_orders,
            SUM(CASE WHEN o.order_type='BUY'  THEN 1 ELSE 0 END)            AS buy_count,
            SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END)            AS sell_count,
            SUM(CASE WHEN o.order_type='BUY'  THEN o.quantity ELSE 0 END)   AS buy_volume,
            SUM(CASE WHEN o.order_type='SELL' THEN o.quantity ELSE 0 END)   AS sell_volume,
            ROUND(100.0*SUM(CASE WHEN o.order_type='BUY'  THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) AS buy_pct,
            ROUND(100.0*SUM(CASE WHEN o.order_type='SELL' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) AS sell_pct,
            (SELECT COUNT(DISTINCT user_id) FROM portfolio
             WHERE  stock_id = o.stock_id AND total_quantity > 0)            AS total_holders
        FROM   orders o
        JOIN   stocks s ON s.stock_id = o.stock_id
        WHERE  upper(o.order_status) = 'EXECUTED'
        GROUP  BY o.stock_id, s.symbol, s.company_name
    """),
]

USERS = [
    (1,    'Demo User',       'demo@tradeflow.in',    'password', 'USER',    'VERIFIED', 1),
    (2,    'Admin User',      'admin@tradeflow.in',   'password', 'ADMIN',   'VERIFIED', 1),
    (1003, 'TechCorp IR Team','company@tradeflow.in', 'password', 'COMPANY', 'VERIFIED', 1),
]

STOCKS = [
    (1,  'RELIANCE',   'Reliance Industries Ltd',       'Energy',   2890.0),
    (2,  'TCS',        'Tata Consultancy Services Ltd',  'IT',       3850.0),
    (3,  'HDFCBANK',   'HDFC Bank Ltd',                  'Finance',  1680.0),
    (4,  'INFY',       'Infosys Ltd',                    'IT',       1420.0),
    (5,  'WIPRO',      'Wipro Ltd',                      'IT',        485.0),
    (6,  'ITC',        'ITC Ltd',                        'FMCG',      445.0),
    (7,  'SBIN',       'State Bank of India',            'Finance',   780.0),
    (8,  'BHARTIARTL', 'Bharti Airtel Ltd',              'Telecom',  1320.0),
    (9,  'HCLTECH',    'HCL Technologies Ltd',           'IT',       1680.0),
    (10, 'AXISBANK',   'Axis Bank Ltd',                  'Finance',  1090.0),
]


def _gen_price_history(stock_id: int, base_price: float, days: int = 90):
    """Generate realistic random-walk daily price history."""
    rows = []
    p = base_price * 0.85
    random.seed(stock_id * 137)
    for i in range(days, -1, -1):
        dt = datetime.now() - timedelta(days=i)
        p = max(1.0, p * (1 + (random.random() - 0.48) * 0.025))
        ts = dt.strftime('%Y-%m-%d') + ' 15:30:00'
        rows.append((stock_id, round(p, 2), ts))
    return rows


def init_db():
    # Skip SQLite init when using PostgreSQL/Supabase
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('DATABASE_URL'):
        print('[DB] DATABASE_URL set — skipping SQLite init (using PostgreSQL/Supabase)')
        return
    if os.path.exists(DB_PATH):
        return  # Already initialized

    print('[DB] Creating new SQLite database with demo data...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Create tables
    conn.executescript(SCHEMA)

    # Create views
    for name, body in VIEWS:
        conn.execute(f'DROP VIEW IF EXISTS {name}')
        conn.execute(f'CREATE VIEW {name} AS {body}')

    # Seed users
    conn.executemany(
        'INSERT OR IGNORE INTO users (user_id,name,email,password,role,kyc_status,is_active) VALUES (?,?,?,?,?,?,?)',
        USERS
    )

    # Seed wallets (₹100,000 starting balance)
    for uid, *_ in USERS:
        bal = 50000.0 if uid == 1003 else 100000.0
        conn.execute(
            'INSERT OR IGNORE INTO wallet (user_id,balance,last_updated) VALUES (?,?,datetime(\'now\'))',
            (uid, bal)
        )

    # Seed stocks (strip base_price column which is only used for price history)
    conn.executemany(
        'INSERT OR IGNORE INTO stocks (stock_id,symbol,company_name,sector,is_active) VALUES (?,?,?,?,1)',
        [(sid, sym, name, sector) for sid, sym, name, sector, _ in STOCKS]
    )

    # Seed 90-day price history for each stock
    for sid, _, _, _, base_price in STOCKS:
        history = _gen_price_history(sid, base_price)
        conn.executemany(
            'INSERT INTO stock_price_history (stock_id,price,price_timestamp) VALUES (?,?,?)',
            history
        )

    # Seed company profile (company user → RELIANCE stock)
    conn.execute("""
        INSERT OR IGNORE INTO company_profiles
            (user_id, stock_id, company_name, cin_number, registered_address,
             contact_email, website, verified)
        VALUES (1003, 1, 'Reliance Industries Ltd', 'L17110MH1973PLC019786',
                'Maker Chambers IV, 222 Nariman Point, Mumbai 400021',
                'investor.relations@ril.com', 'https://www.ril.com', 1)
    """)

    # Seed default system_config entries
    configs = [
        ('max_order_qty',    '10000'),
        ('trading_enabled',  'true'),
        ('maintenance_mode', 'false'),
    ]
    conn.executemany(
        'INSERT OR IGNORE INTO system_config (config_key, config_value) VALUES (?,?)',
        configs
    )

    conn.commit()
    conn.close()
    print('[DB] Database initialized with demo data.')
    print('[DB]    Login: demo@tradeflow.in / password')
    print('[DB]    Admin: admin@tradeflow.in / password')
    print('[DB]    Company: company@tradeflow.in / password')


if __name__ == '__main__':
    # Allow forced re-init by deleting DB file first
    init_db()
