"""
TradeFlow — Python/Flask Backend
Run: python server.py
Requires: pip install flask flask-cors PyJWT python-dotenv psycopg2-binary
"""

import os
import random
import threading
import time
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# Auto-initialize SQLite DB with schema + demo data on first run
from init_db import init_db
init_db()

app = Flask(__name__)

# Disable strict slashes so /api/stocks and /api/stocks/ both work
# without redirecting (redirect strips Authorization header in browsers)
app.url_map.strict_slashes = False

# Allow all origins including file:// (null origin) — returns * not null
CORS(app,
     resources={r"/api/*": {
         "origins": "*",
         "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"],
         "expose_headers": ["Content-Type"],
         "supports_credentials": False,
         "send_wildcard": True,
     }})

app.config['JSON_SORT_KEYS'] = False

# ── Register route blueprints ────────────────────────────────
from routes.auth      import auth_bp
from routes.stocks    import stocks_bp
from routes.orders    import orders_bp
from routes.portfolio import portfolio_bp
from routes.wallet    import wallet_bp
from routes.admin     import admin_bp
from routes.company   import company_bp

app.register_blueprint(auth_bp,      url_prefix='/api/auth')
app.register_blueprint(stocks_bp,    url_prefix='/api/stocks')
app.register_blueprint(orders_bp,    url_prefix='/api/orders')
app.register_blueprint(portfolio_bp, url_prefix='/api/portfolio')
app.register_blueprint(wallet_bp,    url_prefix='/api/wallet')
app.register_blueprint(admin_bp,     url_prefix='/api/admin')
app.register_blueprint(company_bp,   url_prefix='/api/company')

# ── Health check ─────────────────────────────────────────────
from db import query
from datetime import datetime, timezone

@app.get('/api/health')
def health():
    db_status = 'ok'
    db_latency = None
    try:
        import time
        t0 = time.time()
        query('SELECT 1')
        db_latency = round((time.time() - t0) * 1000)
    except Exception as e:
        db_status = f'error: {str(e)}'
    return {
        'status': 'ok',
        'ts': datetime.now(timezone.utc).isoformat(),
        'db': db_status,
        'db_latency_ms': db_latency,
        'env': os.getenv('NODE_ENV', 'development'),
    }

# ── Global error handler ─────────────────────────────────────
@app.errorhandler(Exception)
def handle_error(e):
    print(f'[SERVER] {e}')
    return {'error': 'Internal server error.'}, 500

# ── Price simulator (background thread) ─────────────────────
def _price_tick():
    """Simulate live price ticks every 60 s — keeps charts fresh."""
    from db import query
    time.sleep(10)  # Wait for server to fully start
    while True:
        try:
            stocks = query("SELECT stock_id FROM stocks WHERE is_active IS NOT FALSE")
            for s in stocks:
                sid = s['stock_id']
                last = query(
                    "SELECT price FROM stock_price_history WHERE stock_id=%s ORDER BY price_timestamp DESC LIMIT 1",
                    (sid,)
                )
                if last:
                    prev = float(last[0]['price'])
                    change = prev * (random.uniform(-0.008, 0.009))
                    new_price = round(max(1, prev + change), 2)
                    query(
                        "INSERT INTO stock_price_history (stock_id, price, price_timestamp) VALUES (%s, %s, NOW())",
                        (sid, new_price)
                    )
        except Exception as e:
            print(f'[TICKER] {e}')
        time.sleep(60)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 4000))
    # Start price simulator only when not in debug reloader child process
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or os.getenv('NODE_ENV') == 'production':
        t = threading.Thread(target=_price_tick, daemon=True)
        t.start()
        print('[SERVER] Price simulator started (60s tick)')
    print(f'[SERVER] TradeFlow Python API -> http://localhost:{port}')
    print(f'[SERVER] Health check -> http://localhost:{port}/api/health')
    app.run(host='0.0.0.0', port=port, debug=os.getenv('NODE_ENV') != 'production')
