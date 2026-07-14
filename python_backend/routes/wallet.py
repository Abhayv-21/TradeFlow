"""
routes/wallet.py  →  /api/wallet
"""

from flask import Blueprint, request, jsonify, g
from db import query, query_one, get_conn
from middleware.auth import require_auth

wallet_bp = Blueprint('wallet', __name__)


@wallet_bp.get('/')
@require_auth
def get_wallet():
    try:
        row = query_one(
            'SELECT wallet_id, user_id, balance, last_updated FROM wallet WHERE user_id = %s',
            (g.user['id'],)
        )
        if not row:
            return jsonify({'error': 'Wallet not found.'}), 404
        return jsonify({'wallet': dict(row)})
    except Exception as e:
        print(f'[WALLET] {e}')
        return jsonify({'error': 'Failed to fetch wallet.'}), 500


@wallet_bp.get('/transactions')
@require_auth
def get_transactions():
    try:
        rows = query("""
            SELECT wt.transaction_id, wt.amount, wt.transaction_type, wt.created_at
            FROM   wallet_transactions wt
            JOIN   wallet w ON w.wallet_id = wt.wallet_id
            WHERE  w.user_id = %s
            ORDER  BY wt.created_at DESC
            LIMIT  200
        """, (g.user['id'],))
        return jsonify({'transactions': [dict(r) for r in rows]})
    except Exception as e:
        print(f'[WALLET TXN] {e}')
        return jsonify({'error': 'Failed to fetch transactions.'}), 500


@wallet_bp.post('/deposit')
@require_auth
def deposit():
    body   = request.get_json() or {}
    amount = float(body.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive.'}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT wallet_id, balance FROM wallet WHERE user_id = %s FOR UPDATE',
                            (g.user['id'],))
                w = cur.fetchone()
                if not w:
                    conn.rollback()
                    return jsonify({'error': 'Wallet not found.'}), 404

                cur.execute(
                    'UPDATE wallet SET balance = balance + %s, last_updated = NOW() WHERE wallet_id = %s',
                    (amount, w['wallet_id'])
                )
                # Record transaction (try with sequence, fall back without)
                try:
                    cur.execute("""
                        INSERT INTO wallet_transactions (wallet_id, transaction_id, amount, transaction_type, created_at)
                        VALUES (%s, nextval('txn_seq'), %s, 'CREDIT', NOW())
                    """, (w['wallet_id'], amount))
                except Exception:
                    cur.execute("""
                        INSERT INTO wallet_transactions (wallet_id, amount, transaction_type, created_at)
                        VALUES (%s, %s, 'CREDIT', NOW())
                    """, (w['wallet_id'], amount))

                conn.commit()
                cur.execute('SELECT balance FROM wallet WHERE wallet_id = %s', (w['wallet_id'],))
                new_balance = cur.fetchone()['balance']

        return jsonify({
            'message':     f'₹{amount:,.2f} deposited successfully.',
            'new_balance': float(new_balance),
        })
    except Exception as e:
        print(f'[DEPOSIT] {e}')
        return jsonify({'error': str(e)}), 500


@wallet_bp.post('/withdraw')
@require_auth
def withdraw():
    body   = request.get_json() or {}
    amount = float(body.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be positive.'}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT wallet_id, balance FROM wallet WHERE user_id = %s FOR UPDATE',
                            (g.user['id'],))
                w = cur.fetchone()
                if not w:
                    conn.rollback()
                    return jsonify({'error': 'Wallet not found.'}), 404

                if float(w['balance']) < amount:
                    conn.rollback()
                    return jsonify({'error': f'Insufficient balance. Available: ₹{float(w["balance"]):,.2f}'}), 400

                cur.execute(
                    'UPDATE wallet SET balance = balance - %s, last_updated = NOW() WHERE wallet_id = %s',
                    (amount, w['wallet_id'])
                )
                try:
                    cur.execute("""
                        INSERT INTO wallet_transactions (wallet_id, transaction_id, amount, transaction_type, created_at)
                        VALUES (%s, nextval('txn_seq'), %s, 'DEBIT', NOW())
                    """, (w['wallet_id'], amount))
                except Exception:
                    cur.execute("""
                        INSERT INTO wallet_transactions (wallet_id, amount, transaction_type, created_at)
                        VALUES (%s, %s, 'DEBIT', NOW())
                    """, (w['wallet_id'], amount))

                conn.commit()
                cur.execute('SELECT balance FROM wallet WHERE wallet_id = %s', (w['wallet_id'],))
                new_balance = cur.fetchone()['balance']

        return jsonify({
            'message':     f'₹{amount:,.2f} withdrawn successfully.',
            'new_balance': float(new_balance),
        })
    except Exception as e:
        print(f'[WITHDRAW] {e}')
        return jsonify({'error': str(e)}), 500
