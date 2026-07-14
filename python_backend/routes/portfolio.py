"""
routes/portfolio.py  →  /api/portfolio
"""

from flask import Blueprint, jsonify, g
from db import query, query_one
from middleware.auth import require_auth

portfolio_bp = Blueprint('portfolio', __name__)


@portfolio_bp.get('/')
@require_auth
def get_portfolio():
    try:
        portfolio_rows = query("""
            SELECT * FROM v_portfolio_detail
            WHERE  user_id = %s
            ORDER  BY current_value DESC
        """, (g.user['id'],))

        agg = query_one("""
            SELECT
                COALESCE(SUM(p.total_quantity *
                    COALESCE(lp.latest_price, p.avg_buy_price)), 0) AS portfolio_value,
                COALESCE(SUM(p.total_quantity *
                    (COALESCE(lp.latest_price, p.avg_buy_price) - p.avg_buy_price)), 0) AS profit_loss,
                COALESCE(SUM(p.total_quantity * p.avg_buy_price), 0) AS total_invested
            FROM   portfolio p
            LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = p.stock_id
            WHERE  p.user_id = %s
              AND  p.total_quantity > 0
        """, (g.user['id'],))

        return jsonify({
            'portfolio':       [dict(r) for r in portfolio_rows],
            'portfolio_value': float(agg['portfolio_value'] or 0),
            'profit_loss':     float(agg['profit_loss']     or 0),
            'total_invested':  float(agg['total_invested']  or 0),
        })
    except Exception as e:
        print(f'[PORTFOLIO] {e}')
        return jsonify({'error': 'Failed to fetch portfolio.'}), 500


@portfolio_bp.get('/summary')
@require_auth
def get_summary():
    try:
        row = query_one(
            'SELECT * FROM v_dashboard WHERE user_id = %s',
            (g.user['id'],)
        )
        return jsonify({'summary': dict(row) if row else {}})
    except Exception as e:
        print(f'[PORTFOLIO SUMMARY] {e}')
        return jsonify({'error': 'Failed to fetch portfolio summary.'}), 500
