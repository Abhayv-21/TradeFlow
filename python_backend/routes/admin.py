"""
routes/admin.py  →  /api/admin  (ADMIN role only)
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from db import query, query_one, get_conn
from middleware.auth import require_auth, require_role

admin_bp = Blueprint('admin', __name__)


# ── STATS ─────────────────────────────────────────────────────
@admin_bp.get('/stats')
@require_auth
@require_role('ADMIN')
def get_stats():
    try:
        s = query_one("""
            SELECT
                (SELECT COUNT(*) FROM users)                                              AS total_users,
                (SELECT COUNT(*) FROM users WHERE is_active IS NOT FALSE)                 AS active_users,
                (SELECT COUNT(*) FROM orders)                                             AS total_orders,
                (SELECT COUNT(*) FROM orders WHERE upper(order_status)='EXECUTED')       AS executed_orders,
                (SELECT COUNT(*) FROM orders WHERE upper(order_status)='PENDING')        AS pending_orders,
                (SELECT COUNT(*) FROM trades)                                             AS total_trades,
                (SELECT COALESCE(SUM(executed_price*executed_quantity),0) FROM trades)   AS total_volume,
                (SELECT COALESCE(SUM(balance),0) FROM wallet)                            AS total_wallet_bal,
                (SELECT COUNT(*) FROM stocks WHERE is_active IS NOT FALSE)               AS active_stocks,
                (SELECT COUNT(*) FROM audit_logs
                    WHERE created_at >= NOW() - INTERVAL '1 day')                         AS audit_events_24h,
                (SELECT COUNT(*) FROM system_logs WHERE upper(status)='FAILED')           AS error_logs
        """) or {}
        return jsonify({
            'total_users':      int(s.get('total_users',      0)),
            'active_users':     int(s.get('active_users',     0)),
            'total_orders':     int(s.get('total_orders',     0)),
            'executed_orders':  int(s.get('executed_orders',  0)),
            'pending_orders':   int(s.get('pending_orders',   0)),
            'total_trades':     int(s.get('total_trades',     0)),
            'total_volume':     float(s.get('total_volume',   0)),
            'total_wallet_bal': float(s.get('total_wallet_bal', 0)),
            'active_stocks':    int(s.get('active_stocks',    0)),
            'audit_events_24h': int(s.get('audit_events_24h', 0)),
            'error_logs':       int(s.get('error_logs',       0)),
        })
    except Exception as e:
        print(f'[ADMIN STATS] {e}')
        return jsonify({'error': 'Failed to fetch stats.'}), 500


# ── USERS ─────────────────────────────────────────────────────
@admin_bp.get('/users')
@require_auth
@require_role('ADMIN')
def get_users():
    role      = request.args.get('role', '')
    kyc       = request.args.get('kyc_status', '')
    is_active = request.args.get('is_active', '')
    search    = request.args.get('search', '')
    limit     = int(request.args.get('limit', 500))
    offset    = int(request.args.get('offset', 0))
    try:
        sql = """
            SELECT u.user_id, u.name, u.email, u.role, u.kyc_status,
                   u.is_active, u.last_login, u.created_at,
                   COALESCE(w.balance, 0) AS wallet_balance,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.user_id) AS total_orders
            FROM   users u
            LEFT   JOIN wallet w ON w.user_id = u.user_id
            WHERE  1=1
        """
        params = []
        if role and role != 'ALL':
            params.append(role.upper()); sql += ' AND u.role = %s'
        if kyc and kyc != 'ALL':
            params.append(kyc.upper()); sql += ' AND u.kyc_status = %s'
        if is_active and is_active != 'ALL':
            params.append(True if is_active == 'true' else False); sql += ' AND u.is_active = %s'
        if search:
            params.append(f'%{search.lower()}%')
            sql += ' AND (lower(u.name) LIKE %s OR lower(u.email) LIKE %s)'
            params.append(f'%{search.lower()}%')
        sql += ' ORDER BY u.user_id DESC LIMIT %s OFFSET %s'
        params += [limit, offset]
        rows = query(sql, params)
        return jsonify({'users': [dict(r) for r in rows]})
    except Exception as e:
        print(f'[ADMIN USERS] {e}')
        return jsonify({'error': 'Failed to fetch users.'}), 500


@admin_bp.patch('/users/<int:user_id>')
@require_auth
@require_role('ADMIN')
def update_user(user_id):
    body = request.get_json() or {}
    try:
        clauses, params = [], []
        for field, col in [('name','name'), ('email','email'), ('role','role'),
                           ('kyc_status','kyc_status'), ('is_active','is_active'),
                           ('password','password')]:
            if field in body:
                val = body[field]
                if field == 'email':      val = val.strip().lower()
                if field == 'role':       val = val.upper()
                if field == 'kyc_status': val = val.upper()
                if field == 'is_active':  val = bool(val)
                params.append(val); clauses.append(f'{col}=%s')
        if not clauses:
            return jsonify({'error': 'No fields to update.'}), 400
        params.append(user_id)
        rows = query(
            f'UPDATE users SET {",".join(clauses)} WHERE user_id=%s RETURNING *',
            params
        )
        if not rows:
            return jsonify({'error': 'User not found.'}), 404
        return jsonify({'message': 'User updated.', 'user': dict(rows[0])})
    except Exception as e:
        print(f'[ADMIN UPDATE USER] {e}')
        return jsonify({'error': 'Failed to update user.'}), 500


@admin_bp.delete('/users/<int:user_id>')
@require_auth
@require_role('ADMIN')
def delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'You cannot delete yourself.'}), 400
    try:
        rows = query(
            'UPDATE users SET is_active=FALSE WHERE user_id=%s RETURNING user_id, name',
            (user_id,)
        )
        if not rows:
            return jsonify({'error': 'User not found.'}), 404
        return jsonify({'message': f'User {rows[0]["name"]} deactivated.'})
    except Exception as e:
        return jsonify({'error': 'Failed to delete user.'}), 500


@admin_bp.post('/users/<int:user_id>/activate')
@require_auth
@require_role('ADMIN')
def activate_user(user_id):
    try:
        rows = query(
            'UPDATE users SET is_active=TRUE WHERE user_id=%s RETURNING user_id, name',
            (user_id,)
        )
        if not rows:
            return jsonify({'error': 'User not found.'}), 404
        return jsonify({'message': f'User {rows[0]["name"]} activated.'})
    except Exception as e:
        return jsonify({'error': 'Failed to activate user.'}), 500


@admin_bp.post('/users/<int:user_id>/reset-password')
@require_auth
@require_role('ADMIN')
def reset_password(user_id):
    body = request.get_json() or {}
    new_pw = body.get('new_password', '')
    if len(new_pw) < 4:
        return jsonify({'error': 'Password must be at least 4 characters.'}), 400
    try:
        rows = query(
            'UPDATE users SET password=%s WHERE user_id=%s RETURNING user_id',
            (new_pw, user_id)
        )
        if not rows:
            return jsonify({'error': 'User not found.'}), 404
        return jsonify({'message': 'Password reset successfully.'})
    except Exception as e:
        return jsonify({'error': 'Password reset failed.'}), 500


# ── STOCKS ────────────────────────────────────────────────────
@admin_bp.get('/stocks')
@require_auth
@require_role('ADMIN')
def get_stocks():
    try:
        rows = query("""
            SELECT s.stock_id, s.symbol, s.company_name, s.sector, s.is_active,
                   COALESCE(lp.latest_price, 0) AS current_price,
                   lp.last_updated              AS last_price_update,
                   (SELECT COUNT(*) FROM orders o WHERE o.stock_id = s.stock_id)    AS total_orders,
                   (SELECT COUNT(*) FROM portfolio p WHERE p.stock_id = s.stock_id) AS holders
            FROM   stocks s
            LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = s.stock_id
            ORDER  BY s.stock_id
        """)
        return jsonify({'stocks': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch stocks.'}), 500


@admin_bp.post('/stocks')
@require_auth
@require_role('ADMIN')
def create_stock():
    body   = request.get_json() or {}
    symbol = body.get('symbol', '').upper()
    name   = body.get('company_name', '')
    sector = body.get('sector', 'General')
    price  = float(body.get('initial_price', 0))
    if not symbol or not name:
        return jsonify({'error': 'symbol and company_name are required.'}), 400
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT stock_id FROM stocks WHERE upper(symbol)=upper(%s)', (symbol,))
                if cur.fetchone():
                    return jsonify({'error': 'Symbol already exists.'}), 409
                cur.execute('SELECT COALESCE(MAX(stock_id),0)+1 AS next_id FROM stocks')
                stock_id = cur.fetchone()['next_id']
                cur.execute(
                    'INSERT INTO stocks(stock_id,symbol,company_name,sector,is_active) VALUES(%s,%s,%s,%s,TRUE)',
                    (stock_id, symbol, name, sector)
                )
                if price > 0:
                    cur.execute("""
                        INSERT INTO stock_price_history(stock_id,price,price_timestamp)
                        VALUES(%s,%s,NOW())
                    """, (stock_id, price))
                conn.commit()
        return jsonify({'message': 'Stock created.', 'stock_id': stock_id}), 201
    except Exception as e:
        print(f'[ADMIN CREATE STOCK] {e}')
        return jsonify({'error': 'Failed to create stock.'}), 500


@admin_bp.patch('/stocks/<int:stock_id>')
@require_auth
@require_role('ADMIN')
def update_stock(stock_id):
    body = request.get_json() or {}
    clauses, params = [], []
    for field in ['symbol', 'company_name', 'sector', 'is_active']:
        if field in body:
            val = body[field]
            if field == 'symbol':    val = val.upper()
            if field == 'is_active': val = bool(val)
            params.append(val); clauses.append(f'{field}=%s')
    if not clauses:
        return jsonify({'error': 'No fields to update.'}), 400
    params.append(stock_id)
    try:
        rows = query(f'UPDATE stocks SET {",".join(clauses)} WHERE stock_id=%s RETURNING *', params)
        if not rows:
            return jsonify({'error': 'Stock not found.'}), 404
        return jsonify({'message': 'Stock updated.', 'stock': dict(rows[0])})
    except Exception as e:
        return jsonify({'error': 'Failed to update stock.'}), 500


@admin_bp.delete('/stocks/<int:stock_id>')
@require_auth
@require_role('ADMIN')
def delete_stock(stock_id):
    try:
        rows = query(
            'UPDATE stocks SET is_active=FALSE WHERE stock_id=%s RETURNING symbol', (stock_id,)
        )
        if not rows:
            return jsonify({'error': 'Stock not found.'}), 404
        return jsonify({'message': f'Stock {rows[0]["symbol"]} deactivated.'})
    except Exception as e:
        return jsonify({'error': 'Failed to deactivate stock.'}), 500


@admin_bp.post('/stocks/<int:stock_id>/price')
@require_auth
@require_role('ADMIN')
def set_price(stock_id):
    price = float((request.get_json() or {}).get('price', 0))
    if price <= 0:
        return jsonify({'error': 'Price must be positive.'}), 400
    try:
        query("""
            INSERT INTO stock_price_history(stock_id,price,price_timestamp)
            VALUES(%s,%s,NOW())
        """, (stock_id, price))
        return jsonify({'message': 'Price updated.', 'price': price})
    except Exception as e:
        return jsonify({'error': 'Failed to update price.'}), 500


# ── ORDERS ────────────────────────────────────────────────────
@admin_bp.get('/orders')
@require_auth
@require_role('ADMIN')
def get_orders():
    status   = request.args.get('status', '')
    user_id  = request.args.get('user_id')
    stock_id = request.args.get('stock_id')
    limit    = int(request.args.get('limit', 500))
    offset   = int(request.args.get('offset', 0))
    try:
        sql = """
            SELECT o.order_id, o.user_id, u.name AS user_name, o.stock_id,
                   s.symbol, s.company_name, o.order_type, o.order_price,
                   o.quantity, o.order_price * o.quantity AS total,
                   o.order_status, o.created_at
            FROM   orders o
            JOIN   users  u ON u.user_id  = o.user_id
            JOIN   stocks s ON s.stock_id = o.stock_id
            WHERE  1=1
        """
        params = []
        if status and status != 'ALL': params.append(status.upper()); sql += ' AND upper(o.order_status)=%s'
        if user_id:  params.append(int(user_id));  sql += ' AND o.user_id=%s'
        if stock_id: params.append(int(stock_id)); sql += ' AND o.stock_id=%s'
        sql += ' ORDER BY o.created_at DESC LIMIT %s OFFSET %s'
        params += [limit, offset]
        rows = query(sql, params)
        return jsonify({'orders': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch orders.'}), 500


@admin_bp.delete('/orders/<int:order_id>')
@require_auth
@require_role('ADMIN')
def cancel_order(order_id):
    try:
        rows = query("""
            UPDATE orders SET order_status='CANCELLED'
            WHERE  order_id=%s AND order_status='PENDING' RETURNING *
        """, (order_id,))
        if not rows:
            return jsonify({'error': 'Order not found or not pending.'}), 404
        return jsonify({'message': 'Order cancelled by admin.', 'order': dict(rows[0])})
    except Exception as e:
        return jsonify({'error': 'Failed to cancel order.'}), 500


# ── WALLETS ───────────────────────────────────────────────────
@admin_bp.get('/wallets')
@require_auth
@require_role('ADMIN')
def get_wallets():
    limit  = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    try:
        rows = query("""
            SELECT w.wallet_id, w.user_id, u.name AS user_name, u.email,
                   w.balance, w.last_updated,
                   (SELECT COUNT(*) FROM wallet_transactions wt WHERE wt.wallet_id=w.wallet_id) AS txn_count
            FROM   wallet w
            JOIN   users u ON u.user_id = w.user_id
            ORDER  BY w.balance DESC
            LIMIT  %s OFFSET %s
        """, (limit, offset))
        return jsonify({'wallets': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch wallets.'}), 500


@admin_bp.get('/wallets/<int:user_id>/transactions')
@require_auth
@require_role('ADMIN')
def get_wallet_txns(user_id):
    try:
        rows = query("""
            SELECT wt.transaction_id, wt.amount, wt.transaction_type, wt.created_at
            FROM   wallet_transactions wt
            JOIN   wallet w ON w.wallet_id = wt.wallet_id
            WHERE  w.user_id = %s
            ORDER  BY wt.created_at DESC LIMIT 200
        """, (user_id,))
        return jsonify({'transactions': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch transactions.'}), 500


@admin_bp.post('/wallets/<int:user_id>/adjust')
@require_auth
@require_role('ADMIN')
def adjust_wallet(user_id):
    body     = request.get_json() or {}
    amount   = float(body.get('amount', 0))
    txn_type = str(body.get('type', '')).upper()
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive.'}), 400
    if txn_type not in ('CREDIT', 'DEBIT'):
        return jsonify({'error': 'type must be CREDIT or DEBIT.'}), 400
    try:
        if txn_type == 'CREDIT':
            query("UPDATE wallet SET balance=balance+%s, last_updated=NOW() WHERE user_id=%s",
                  (amount, user_id))
        else:
            w = query_one('SELECT balance FROM wallet WHERE user_id=%s', (user_id,))
            if not w or float(w['balance']) < amount:
                return jsonify({'error': 'Insufficient balance.'}), 400
            query("UPDATE wallet SET balance=balance-%s, last_updated=NOW() WHERE user_id=%s",
                  (amount, user_id))
        # Record wallet transaction
        try:
            query("""
                INSERT INTO wallet_transactions (wallet_id, amount, transaction_type, created_at)
                SELECT wallet_id, %s, %s, NOW() FROM wallet WHERE user_id=%s
            """, (amount, txn_type, user_id))
        except Exception:
            pass
        bal = query_one('SELECT balance FROM wallet WHERE user_id=%s', (user_id,))
        return jsonify({
            'message':     f'₹{amount:,.2f} {txn_type.lower()}ed successfully.',
            'new_balance': float(bal['balance']),
        })
    except Exception as e:
        print(f'[ADMIN WALLET ADJUST] {e}')
        return jsonify({'error': str(e)}), 500


# ── AUDIT LOGS ────────────────────────────────────────────────
@admin_bp.get('/audit')
@require_auth
@require_role('ADMIN')
def get_audit():
    action   = request.args.get('action', '')
    user_id  = request.args.get('user_id')
    resource = request.args.get('resource', '')
    status   = request.args.get('status', '')
    limit    = int(request.args.get('limit', 100))
    offset   = int(request.args.get('offset', 0))
    days     = int(request.args.get('days', 7))
    cutoff   = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        sql = """
            SELECT al.audit_id, al.user_id, u.name AS user_name,
                   al.action, al.resource, al.resource_id,
                   al.details, al.ip_address, al.status, al.created_at
            FROM   audit_logs al
            LEFT   JOIN users u ON u.user_id = al.user_id
            WHERE  al.created_at >= %s
        """
        params = [cutoff]
        if action   and action   != 'ALL': params.append(action.upper());   sql += ' AND al.action=%s'
        if user_id:                         params.append(int(user_id));      sql += ' AND al.user_id=%s'
        if resource and resource != 'ALL': params.append(resource);          sql += ' AND al.resource=%s'
        if status   and status   != 'ALL': params.append(status.upper());    sql += ' AND al.status=%s'
        sql += ' ORDER BY al.created_at DESC LIMIT %s OFFSET %s'
        params += [limit, offset]
        rows = query(sql, params)
        return jsonify({'logs': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch audit logs.'}), 500


@admin_bp.get('/audit/actions')
@require_auth
@require_role('ADMIN')
def get_audit_actions():
    try:
        rows = query('SELECT DISTINCT action FROM audit_logs ORDER BY action')
        return jsonify({'actions': [r['action'] for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch actions.'}), 500


# ── SYSTEM CONFIG ─────────────────────────────────────────────
@admin_bp.get('/config')
@require_auth
@require_role('ADMIN')
def get_config():
    try:
        rows = query('SELECT * FROM system_config ORDER BY config_key')
        return jsonify({'config': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch config.'}), 500


@admin_bp.put('/config/<key>')
@require_auth
@require_role('ADMIN')
def update_config(key):
    body = request.get_json() or {}
    value = body.get('value')
    if value is None:
        return jsonify({'error': 'value is required.'}), 400
    try:
        rows = query("""
            UPDATE system_config
            SET config_value=%s, updated_by=%s, updated_at=NOW()
            WHERE config_key=%s RETURNING *
        """, (str(value), g.user['id'], key))
        if not rows:
            return jsonify({'error': 'Config key not found.'}), 404
        return jsonify({'message': 'Config updated.', 'config': dict(rows[0])})
    except Exception as e:
        return jsonify({'error': 'Failed to update config.'}), 500


# ── TRADES ────────────────────────────────────────────────────
@admin_bp.get('/trades')
@require_auth
@require_role('ADMIN')
def get_trades():
    user_id  = request.args.get('user_id')
    stock_id = request.args.get('stock_id')
    limit    = int(request.args.get('limit', 100))
    offset   = int(request.args.get('offset', 0))
    try:
        sql = """
            SELECT t.trade_id, t.order_id,
                   o.user_id, u.name AS user_name,
                   o.stock_id, s.symbol, s.company_name,
                   o.order_type AS trade_type,
                   t.executed_quantity AS quantity,
                   t.executed_price    AS price,
                   ROUND(t.executed_price * t.executed_quantity, 2) AS total_value,
                   t.trade_time AS executed_at
            FROM   trades t
            JOIN   orders  o ON o.order_id  = t.order_id
            JOIN   users   u ON u.user_id   = o.user_id
            JOIN   stocks  s ON s.stock_id  = o.stock_id
            WHERE  1=1
        """
        params = []
        if user_id:  params.append(int(user_id));  sql += ' AND o.user_id=%s'
        if stock_id: params.append(int(stock_id)); sql += ' AND o.stock_id=%s'
        sql += ' ORDER BY t.trade_time DESC LIMIT %s OFFSET %s'
        params += [limit, offset]
        rows = query(sql, params)
        return jsonify({'trades': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch trades.'}), 500


# ── INSIGHTS ──────────────────────────────────────────────────
@admin_bp.get('/insights')
@require_auth
@require_role('ADMIN')
def get_insights():
    try:
        top_vol = query("""
            SELECT s.symbol, s.company_name, s.sector,
                   COUNT(t.trade_id)         AS trade_count,
                   SUM(t.executed_quantity)  AS total_shares,
                   ROUND(SUM(t.executed_price * t.executed_quantity), 2) AS total_value
            FROM   trades t
            JOIN   orders o ON o.order_id = t.order_id
            JOIN   stocks s ON s.stock_id = o.stock_id
            GROUP  BY s.stock_id, s.symbol, s.company_name, s.sector
            ORDER  BY total_shares DESC LIMIT 10
        """)
        gainers = query("""
            WITH prev AS (
                SELECT s.stock_id,
                       (SELECT price FROM stock_price_history
                        WHERE  stock_id = s.stock_id
                          AND  price_timestamp < NOW() - INTERVAL '1 day'
                        ORDER  BY price_timestamp DESC LIMIT 1) AS prev_price
                FROM stocks s WHERE s.is_active IS NOT FALSE
            )
            SELECT s.symbol, s.company_name,
                   lp.latest_price AS current_price,
                   prev.prev_price,
                   ROUND(((lp.latest_price - prev.prev_price) / NULLIF(prev.prev_price, 0)) * 100, 2) AS change_pct
            FROM   stocks s
            JOIN   v_stock_latest_price lp ON lp.stock_id = s.stock_id
            JOIN   prev ON prev.stock_id = s.stock_id
            WHERE  s.is_active IS NOT FALSE AND prev.prev_price IS NOT NULL
            ORDER  BY change_pct DESC LIMIT 5
        """)
        losers = query("""
            WITH prev AS (
                SELECT s.stock_id,
                       (SELECT price FROM stock_price_history
                        WHERE  stock_id = s.stock_id
                          AND  price_timestamp < NOW() - INTERVAL '1 day'
                        ORDER  BY price_timestamp DESC LIMIT 1) AS prev_price
                FROM stocks s WHERE s.is_active IS NOT FALSE
            )
            SELECT s.symbol, s.company_name,
                   lp.latest_price AS current_price,
                   prev.prev_price,
                   ROUND(((lp.latest_price - prev.prev_price) / NULLIF(prev.prev_price, 0)) * 100, 2) AS change_pct
            FROM   stocks s
            JOIN   v_stock_latest_price lp ON lp.stock_id = s.stock_id
            JOIN   prev ON prev.stock_id = s.stock_id
            WHERE  s.is_active IS NOT FALSE AND prev.prev_price IS NOT NULL
            ORDER  BY change_pct ASC LIMIT 5
        """)
        week_cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        daily = query("""
            SELECT date(t.trade_time)              AS trade_date,
                   COUNT(t.trade_id)               AS trades,
                   SUM(t.executed_quantity)        AS shares,
                   ROUND(SUM(t.executed_price * t.executed_quantity), 2) AS volume
            FROM   trades t
            WHERE  t.trade_time >= %s
            GROUP  BY date(t.trade_time)
            ORDER  BY trade_date ASC
        """, (week_cutoff,))
        return jsonify({
            'most_traded':  [dict(r) for r in top_vol],
            'top_gainers':  [dict(r) for r in gainers],
            'top_losers':   [dict(r) for r in losers],
            'daily_volume': [dict(r) for r in daily],
        })
    except Exception as e:
        print(f'[ADMIN INSIGHTS] {e}')
        return jsonify({'error': 'Failed to fetch insights.'}), 500


# ── LEGACY: LOGS, DB-TXN, LOCKS ──────────────────────────────
@admin_bp.get('/logs')
@require_auth
@require_role('ADMIN')
def get_logs():
    status = request.args.get('status', '')
    limit  = int(request.args.get('limit', 100))
    try:
        sql = """
            SELECT l.log_id, l.txn_id, l.operation, l.status, l.timestamp,
                   dt.user_id, u.name AS user_name
            FROM   system_logs l
            LEFT   JOIN database_transactions dt ON dt.txn_id = l.txn_id
            LEFT   JOIN users u ON u.user_id = dt.user_id
        """
        params = []
        if status and status != 'ALL':
            sql += ' WHERE upper(l.status)=%s'; params.append(status.upper())
        sql += f' ORDER BY l.timestamp DESC LIMIT %s'
        params.append(limit)
        rows = query(sql, params)
        return jsonify({'logs': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch logs.'}), 500


@admin_bp.get('/db-transactions')
@require_auth
@require_role('ADMIN')
def get_db_txns():
    try:
        rows = query("""
            SELECT dt.txn_id, dt.user_id, u.name AS user_name,
                   dt.txn_state, dt.start_time, dt.end_time
            FROM   database_transactions dt
            LEFT   JOIN users u ON u.user_id = dt.user_id
            ORDER  BY dt.start_time DESC LIMIT 100
        """)
        result = []
        now = datetime.utcnow()
        for r in rows:
            d = dict(r)
            try:
                fmt = '%Y-%m-%d %H:%M:%S'
                t0 = datetime.strptime(str(d['start_time'])[:19], fmt)
                t1_str = d.get('end_time')
                t1 = datetime.strptime(str(t1_str)[:19], fmt) if t1_str else now
                d['duration_ms'] = round((t1 - t0).total_seconds() * 1000)
            except Exception:
                d['duration_ms'] = None
            result.append(d)
        return jsonify({'transactions': result})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch DB transactions.'}), 500


@admin_bp.get('/locks')
@require_auth
@require_role('ADMIN')
def get_locks():
    try:
        recorded = query("""
            SELECT lk.lock_id, lk.txn_id, lk.resource_type, lk.lock_mode,
                   dt.txn_state, dt.user_id, u.name AS user_name
            FROM   locks lk
            LEFT   JOIN database_transactions dt ON dt.txn_id = lk.txn_id
            LEFT   JOIN users u ON u.user_id = dt.user_id
            ORDER  BY lk.lock_id DESC LIMIT 50
        """)
        return jsonify({'locks': [dict(r) for r in recorded], 'live_locks': []})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch locks.'}), 500


# ── COMPANIES (admin manages company profiles) ────────────────
@admin_bp.get('/companies')
@require_auth
@require_role('ADMIN')
def get_companies():
    try:
        rows = query("""
            SELECT cp.company_id, cp.user_id, u.name AS user_name, u.email,
                   cp.company_name, s.symbol, s.company_name AS stock_name,
                   cp.cin_number, cp.contact_email, cp.website,
                   cp.verified, cp.created_at
            FROM   company_profiles cp
            JOIN   users  u ON u.user_id  = cp.user_id
            JOIN   stocks s ON s.stock_id = cp.stock_id
            ORDER  BY cp.created_at DESC
        """)
        return jsonify({'companies': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch companies.'}), 500


@admin_bp.post('/companies')
@require_auth
@require_role('ADMIN')
def create_company():
    body = request.get_json() or {}
    required = ['user_id', 'stock_id', 'company_name']
    if not all(body.get(k) for k in required):
        return jsonify({'error': 'user_id, stock_id and company_name are required.'}), 400
    try:
        rows = query("""
            INSERT INTO company_profiles (user_id, stock_id, company_name, cin_number,
                        registered_address, contact_email, website, verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
            RETURNING company_id
        """, (body['user_id'], body['stock_id'], body['company_name'],
              body.get('cin_number'), body.get('registered_address'),
              body.get('contact_email'), body.get('website')))
        return jsonify({'message': 'Company profile created.', 'company_id': rows[0]['company_id']}), 201
    except Exception as e:
        print(f'[ADMIN CREATE COMPANY] {e}')
        return jsonify({'error': str(e)}), 500


@admin_bp.patch('/companies/<int:company_id>/verify')
@require_auth
@require_role('ADMIN')
def verify_company(company_id):
    body     = request.get_json() or {}
    verified = 1 if body.get('verified', True) else 0
    try:
        rows = query(
            'UPDATE company_profiles SET verified=%s WHERE company_id=%s RETURNING company_id',
            (verified, company_id)
        )
        if not rows:
            return jsonify({'error': 'Company not found.'}), 404
        return jsonify({'message': f'Company {"verified" if verified else "unverified"}.'})
    except Exception as e:
        return jsonify({'error': 'Failed to update verification.'}), 500


@admin_bp.delete('/companies/<int:company_id>')
@require_auth
@require_role('ADMIN')
def delete_company(company_id):
    try:
        rows = query(
            'DELETE FROM company_profiles WHERE company_id=%s RETURNING company_id',
            (company_id,)
        )
        if not rows:
            return jsonify({'error': 'Company not found.'}), 404
        return jsonify({'message': 'Company profile deleted.'})
    except Exception as e:
        return jsonify({'error': 'Failed to delete company.'}), 500
