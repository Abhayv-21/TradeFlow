"""
routes/orders.py  →  /api/orders
POST /          — place BUY or SELL order
GET  /          — user's order history
GET  /trades    — user's trade history
DELETE /:id     — cancel PENDING order
"""

from flask import Blueprint, request, jsonify, g
from db import get_conn, query
from middleware.auth import require_auth

orders_bp = Blueprint('orders', __name__)


# ── GET /api/orders ──────────────────────────────────────────
@orders_bp.get('/')
@require_auth
def get_orders():
    status = request.args.get('status', '').upper()
    try:
        sql = """
            SELECT
                o.order_id,
                o.stock_id,
                s.symbol,
                s.company_name,
                o.order_type,
                o.order_price          AS price,
                o.quantity,
                ROUND(o.order_price * o.quantity, 2) AS total_value,
                o.order_status         AS status,
                o.created_at
            FROM   orders o
            JOIN   stocks s ON s.stock_id = o.stock_id
            WHERE  o.user_id = %s
        """
        params = [g.user['id']]
        if status and status != 'ALL':
            sql    += ' AND upper(o.order_status) = %s'
            params.append(status)
        sql += ' ORDER BY o.created_at DESC LIMIT 200'
        rows = query(sql, params)
        return jsonify({'orders': [dict(r) for r in rows]})
    except Exception as e:
        print(f'[ORDERS GET] {e}')
        return jsonify({'error': 'Failed to fetch orders.'}), 500


# ── GET /api/orders/trades ────────────────────────────────────
@orders_bp.get('/trades')
@require_auth
def get_trades():
    try:
        rows = query("""
            SELECT
                t.trade_id,
                t.order_id,
                o.stock_id,
                s.symbol,
                s.company_name,
                o.order_type                                       AS trade_type,
                t.executed_quantity                                AS quantity,
                t.executed_price                                   AS price,
                ROUND(t.executed_price * t.executed_quantity, 2)   AS total_value,
                t.trade_time                                       AS executed_at
            FROM   trades  t
            JOIN   orders  o ON o.order_id  = t.order_id
            JOIN   stocks  s ON s.stock_id  = o.stock_id
            WHERE  o.user_id = %s
            ORDER  BY t.trade_time DESC
            LIMIT  200
        """, (g.user['id'],))
        return jsonify({'trades': [dict(r) for r in rows]})
    except Exception as e:
        print(f'[TRADES GET] {e}')
        return jsonify({'error': 'Failed to fetch trades.'}), 500


# ── POST /api/orders — place BUY or SELL ─────────────────────
@orders_bp.post('/')
@require_auth
def place_order():
    body      = request.get_json() or {}
    stock_id  = body.get('stock_id')
    order_type = str(body.get('order_type', '')).upper()
    qty       = body.get('qty')
    price     = body.get('price')

    if not all([stock_id, order_type, qty, price]):
        return jsonify({'error': 'stock_id, order_type, qty and price are required.'}), 400

    try:
        quantity   = int(qty)
        exec_price = float(price)
    except (ValueError, TypeError):
        return jsonify({'error': 'qty must be integer, price must be a number.'}), 400

    if order_type not in ('BUY', 'SELL'):
        return jsonify({'error': 'order_type must be BUY or SELL.'}), 400
    if quantity <= 0:
        return jsonify({'error': 'qty must be a positive integer.'}), 400
    if exec_price <= 0:
        return jsonify({'error': 'price must be a positive number.'}), 400

    user_id = g.user['id']
    total   = round(quantity * exec_price, 2)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                if order_type == 'BUY':
                    # 1. Lock & check wallet
                    cur.execute('SELECT wallet_id, balance FROM wallet WHERE user_id = %s FOR UPDATE', (user_id,))
                    w = cur.fetchone()
                    if not w:
                        raise ValueError('Wallet not found.')
                    if float(w['balance']) < total:
                        raise ValueError(
                            f'Insufficient balance. Need ₹{total:,.2f}, '
                            f'available ₹{float(w["balance"]):,.2f}.'
                        )

                    # 2. Create order
                    cur.execute("""
                        INSERT INTO orders (user_id,stock_id,order_type,order_price,quantity,order_status,created_at)
                        VALUES (%s,%s,'BUY',%s,%s,'EXECUTED',NOW()) RETURNING order_id
                    """, (user_id, stock_id, exec_price, quantity))
                    order_id = cur.fetchone()['order_id']

                    # 3. Create trade
                    cur.execute("""
                        INSERT INTO trades (order_id,executed_price,executed_quantity,trade_time)
                        VALUES (%s,%s,%s,NOW()) RETURNING trade_id
                    """, (order_id, exec_price, quantity))
                    trade_id = cur.fetchone()['trade_id']

                    # 4. Deduct wallet
                    cur.execute(
                        'UPDATE wallet SET balance=balance-%s, last_updated=NOW() WHERE wallet_id=%s',
                        (total, w['wallet_id'])
                    )

                    # 5. Record wallet transaction (non-fatal)
                    try:
                        cur.execute("""
                            INSERT INTO wallet_transactions (wallet_id,transaction_id,amount,transaction_type,created_at)
                            VALUES (%s,nextval('txn_seq'),%s,'DEBIT',NOW())
                        """, (w['wallet_id'], total))
                    except Exception:
                        try:
                            cur.execute("""
                                INSERT INTO wallet_transactions (wallet_id,amount,transaction_type,created_at)
                                VALUES (%s,%s,'DEBIT',NOW())
                            """, (w['wallet_id'], total))
                        except Exception:
                            pass

                    # 6. UPSERT portfolio (weighted average price)
                    cur.execute("""
                        SELECT portfolio_id, total_quantity, avg_buy_price
                        FROM   portfolio WHERE user_id=%s AND stock_id=%s FOR UPDATE
                    """, (user_id, stock_id))
                    existing = cur.fetchone()
                    if existing:
                        new_qty = existing['total_quantity'] + quantity
                        new_avg = ((existing['avg_buy_price'] * existing['total_quantity'])
                                   + (exec_price * quantity)) / new_qty
                        cur.execute(
                            'UPDATE portfolio SET total_quantity=%s, avg_buy_price=%s WHERE portfolio_id=%s',
                            (new_qty, round(new_avg, 4), existing['portfolio_id'])
                        )
                        portfolio_id = existing['portfolio_id']
                    else:
                        cur.execute("""
                            INSERT INTO portfolio (user_id,stock_id,total_quantity,avg_buy_price)
                            VALUES (%s,%s,%s,%s) RETURNING portfolio_id
                        """, (user_id, stock_id, quantity, exec_price))
                        portfolio_id = cur.fetchone()['portfolio_id']

                    # 7. portfolio_transactions (non-fatal)
                    try:
                        cur.execute("""
                            INSERT INTO portfolio_transactions (portfolio_id,order_id,trade_id,quantity_change,created_at)
                            VALUES (%s,%s,%s,%s,NOW())
                        """, (portfolio_id, order_id, trade_id, quantity))
                    except Exception:
                        pass

                else:  # SELL
                    # 1. Check portfolio holdings
                    cur.execute("""
                        SELECT portfolio_id, total_quantity
                        FROM   portfolio WHERE user_id=%s AND stock_id=%s FOR UPDATE
                    """, (user_id, stock_id))
                    p = cur.fetchone()
                    if not p:
                        raise ValueError('No holdings found for this stock.')
                    if p['total_quantity'] < quantity:
                        raise ValueError(
                            f'Insufficient holdings. You hold {p["total_quantity"]} shares, '
                            f'tried to sell {quantity}.'
                        )

                    # 2. Create order
                    cur.execute("""
                        INSERT INTO orders (user_id,stock_id,order_type,order_price,quantity,order_status,created_at)
                        VALUES (%s,%s,'SELL',%s,%s,'EXECUTED',NOW()) RETURNING order_id
                    """, (user_id, stock_id, exec_price, quantity))
                    order_id = cur.fetchone()['order_id']

                    # 3. Create trade
                    cur.execute("""
                        INSERT INTO trades (order_id,executed_price,executed_quantity,trade_time)
                        VALUES (%s,%s,%s,NOW()) RETURNING trade_id
                    """, (order_id, exec_price, quantity))
                    trade_id = cur.fetchone()['trade_id']

                    # 4. Update portfolio
                    new_qty = p['total_quantity'] - quantity
                    if new_qty == 0:
                        cur.execute('DELETE FROM portfolio WHERE portfolio_id=%s', (p['portfolio_id'],))
                        portfolio_id = None
                    else:
                        cur.execute(
                            'UPDATE portfolio SET total_quantity=%s WHERE portfolio_id=%s',
                            (new_qty, p['portfolio_id'])
                        )
                        portfolio_id = p['portfolio_id']

                    # 5. Credit wallet
                    cur.execute(
                        'SELECT wallet_id FROM wallet WHERE user_id=%s FOR UPDATE', (user_id,)
                    )
                    w = cur.fetchone()
                    if not w:
                        raise ValueError('Wallet not found.')
                    cur.execute(
                        'UPDATE wallet SET balance=balance+%s, last_updated=NOW() WHERE wallet_id=%s',
                        (total, w['wallet_id'])
                    )

                    # 6. Wallet transaction (non-fatal)
                    try:
                        cur.execute("""
                            INSERT INTO wallet_transactions (wallet_id,transaction_id,amount,transaction_type,created_at)
                            VALUES (%s,nextval('txn_seq'),%s,'CREDIT',NOW())
                        """, (w['wallet_id'], total))
                    except Exception:
                        try:
                            cur.execute("""
                                INSERT INTO wallet_transactions (wallet_id,amount,transaction_type,created_at)
                                VALUES (%s,%s,'CREDIT',NOW())
                            """, (w['wallet_id'], total))
                        except Exception:
                            pass

                    # 7. portfolio_transactions (non-fatal)
                    if portfolio_id:
                        try:
                            cur.execute("""
                                INSERT INTO portfolio_transactions (portfolio_id,order_id,trade_id,quantity_change,created_at)
                                VALUES (%s,%s,%s,%s,NOW())
                            """, (portfolio_id, order_id, trade_id, -quantity))
                        except Exception:
                            pass

                conn.commit()

        return jsonify({
            'message':  f'{order_type} successful — {quantity} shares @ ₹{exec_price}',
            'order_id': order_id,
            'trade_id': trade_id,
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f'[ORDER] {e}')
        return jsonify({'error': str(e)}), 400


# ── DELETE /api/orders/:id — cancel PENDING order ────────────
@orders_bp.delete('/<int:order_id>')
@require_auth
def cancel_order(order_id):
    try:
        rows = query("""
            UPDATE orders SET order_status='CANCELLED'
            WHERE  order_id=%s AND user_id=%s AND upper(order_status)='PENDING'
            RETURNING order_id
        """, (order_id, g.user['id']))
        if not rows:
            return jsonify({'error': 'Order not found or not in PENDING status.'}), 404
        return jsonify({'message': 'Order cancelled.', 'order_id': rows[0]['order_id']})
    except Exception as e:
        print(f'[CANCEL ORDER] {e}')
        return jsonify({'error': 'Failed to cancel order.'}), 500
