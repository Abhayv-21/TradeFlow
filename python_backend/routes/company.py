"""
routes/company.py  →  /api/company  (COMPANY role only)
A COMPANY user can only see data for their own stock_id.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from db import query, query_one
from middleware.auth import require_auth, require_role

company_bp = Blueprint('company', __name__)


def _get_company():
    return query_one("""
        SELECT cp.company_id, cp.stock_id, cp.company_name, cp.verified,
               s.symbol, s.company_name AS stock_display_name
        FROM   company_profiles cp
        JOIN   stocks s ON s.stock_id = cp.stock_id
        WHERE  cp.user_id = %s
    """, (g.user['id'],))


@company_bp.get('/profile')
@require_auth
@require_role('COMPANY')
def get_profile():
    try:
        cp = query_one("""
            SELECT cp.*, s.symbol, s.company_name AS stock_name, s.sector
            FROM   company_profiles cp
            JOIN   stocks s ON s.stock_id = cp.stock_id
            WHERE  cp.user_id = %s
        """, (g.user['id'],))
        if not cp:
            return jsonify({'error': 'Company profile not found. Contact admin.'}), 404
        return jsonify({'profile': dict(cp)})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch profile.'}), 500


@company_bp.put('/profile')
@require_auth
@require_role('COMPANY')
def update_profile():
    body = request.get_json() or {}
    allowed = ['contact_email', 'website', 'registered_address']
    clauses, params = [], []
    for field in allowed:
        if field in body:
            params.append(body[field]); clauses.append(f'{field}=%s')
    if not clauses:
        return jsonify({'error': 'No editable fields provided.'}), 400
    params.append(g.user['id'])
    try:
        rows = query(
            f'UPDATE company_profiles SET {",".join(clauses)} WHERE user_id=%s RETURNING *',
            params
        )
        if not rows:
            return jsonify({'error': 'Company profile not found.'}), 404
        return jsonify({'message': 'Profile updated.', 'profile': dict(rows[0])})
    except Exception as e:
        return jsonify({'error': 'Failed to update profile.'}), 500


@company_bp.get('/stock/overview')
@require_auth
@require_role('COMPANY')
def stock_overview():
    try:
        cp = _get_company()
        if not cp:
            return jsonify({'error': 'Company profile not found.'}), 404

        stock_id = cp['stock_id']

        # Get prev-day price separately to avoid LATERAL join
        prev_row = query_one("""
            SELECT price FROM stock_price_history
            WHERE  stock_id = %s AND price_timestamp < NOW() - INTERVAL '1 day'
            ORDER  BY price_timestamp DESC LIMIT 1
        """, (stock_id,))
        prev_price = float(prev_row['price']) if prev_row else 0.0

        overview = query_one("""
            SELECT
                s.stock_id, s.symbol, s.company_name,
                COALESCE(lp.latest_price, 0) AS current_price,
                (SELECT COUNT(DISTINCT user_id) FROM portfolio
                 WHERE  stock_id = s.stock_id AND total_quantity > 0) AS total_holders,
                (SELECT COALESCE(SUM(t.executed_quantity), 0)
                 FROM   trades t JOIN orders o ON o.order_id = t.order_id
                 WHERE  o.stock_id = s.stock_id
                   AND  date(t.trade_time) = CURRENT_DATE) AS today_volume,
                (SELECT COALESCE(SUM(t.executed_price * t.executed_quantity), 0)
                 FROM   trades t JOIN orders o ON o.order_id = t.order_id
                 WHERE  o.stock_id = s.stock_id
                   AND  date(t.trade_time) = CURRENT_DATE) AS today_value
            FROM   stocks s
            LEFT   JOIN v_stock_latest_price lp ON lp.stock_id = s.stock_id
            WHERE  s.stock_id = %s
        """, (stock_id,))

        sentiment = query_one(
            'SELECT * FROM v_company_stock_sentiment WHERE stock_id = %s',
            (stock_id,)
        )

        if overview:
            cur_price = float(overview['current_price'] or 0)
            overview = dict(overview)
            overview['prev_price'] = prev_price
            overview['change_pct'] = round(
                ((cur_price - prev_price) / prev_price * 100) if prev_price else 0, 2
            )

        return jsonify({
            'overview':  overview or {},
            'sentiment': dict(sentiment) if sentiment else {},
        })
    except Exception as e:
        print(f'[COMPANY OVERVIEW] {e}')
        return jsonify({'error': 'Failed to fetch stock overview.'}), 500


@company_bp.get('/stock/history')
@require_auth
@require_role('COMPANY')
def stock_history():
    days = min(int(request.args.get('days', 30)), 365)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        cp = _get_company()
        if not cp:
            return jsonify({'error': 'Company profile not found.'}), 404

        rows = query("""
            SELECT price, price_timestamp
            FROM   stock_price_history
            WHERE  stock_id = %s
              AND  price_timestamp >= %s
            ORDER  BY price_timestamp ASC
        """, (cp['stock_id'], cutoff))
        result = []
        for r in rows:
            d = dict(r)
            try:
                dt_obj = datetime.strptime(str(d['price_timestamp'])[:10], '%Y-%m-%d')
                d['date'] = dt_obj.strftime('%b %d')
            except Exception:
                d['date'] = str(d['price_timestamp'])[:10]
            result.append(d)
        return jsonify({'history': result})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch stock history.'}), 500


@company_bp.get('/stock/sentiment')
@require_auth
@require_role('COMPANY')
def stock_sentiment():
    try:
        cp = _get_company()
        if not cp:
            return jsonify({'error': 'Company profile not found.'}), 404
        row = query_one(
            'SELECT * FROM v_company_stock_sentiment WHERE stock_id = %s',
            (cp['stock_id'],)
        )
        return jsonify({'sentiment': dict(row) if row else {}})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch sentiment.'}), 500


@company_bp.get('/announcements')
@require_auth
@require_role('COMPANY')
def get_announcements():
    try:
        cp = _get_company()
        if not cp:
            return jsonify({'error': 'Company profile not found.'}), 404
        rows = query("""
            SELECT * FROM company_announcements
            WHERE  company_id = %s
            ORDER  BY created_at DESC
        """, (cp['company_id'],))
        return jsonify({'announcements': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch announcements.'}), 500


@company_bp.post('/announcements')
@require_auth
@require_role('COMPANY')
def create_announcement():
    body = request.get_json() or {}
    cp   = _get_company()
    if not cp:
        return jsonify({'error': 'Company profile not found.'}), 404

    required = ['title', 'content', 'announcement_type']
    if not all(body.get(k) for k in required):
        return jsonify({'error': 'title, content and announcement_type are required.'}), 400

    valid_types = ('DIVIDEND', 'SPLIT', 'BONUS', 'RESULTS', 'AGM', 'OTHER')
    ann_type = str(body['announcement_type']).upper()
    if ann_type not in valid_types:
        return jsonify({'error': f'announcement_type must be one of: {", ".join(valid_types)}'}), 400

    try:
        rows = query("""
            INSERT INTO company_announcements
                (company_id, title, content, announcement_type, effective_date, is_published)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (cp['company_id'], body['title'], body['content'], ann_type,
              body.get('effective_date'), 1 if body.get('is_published') else 0))
        return jsonify({'message': 'Announcement created.', 'announcement': dict(rows[0])}), 201
    except Exception as e:
        print(f'[COMPANY ANN CREATE] {e}')
        return jsonify({'error': 'Failed to create announcement.'}), 500


@company_bp.put('/announcements/<int:ann_id>')
@require_auth
@require_role('COMPANY')
def update_announcement(ann_id):
    body = request.get_json() or {}
    cp   = _get_company()
    if not cp:
        return jsonify({'error': 'Company profile not found.'}), 404

    allowed = ['title', 'content', 'announcement_type', 'effective_date', 'is_published']
    clauses, params = [], []
    for field in allowed:
        if field in body:
            val = body[field]
            if field == 'announcement_type': val = str(val).upper()
            if field == 'is_published':       val = 1 if val else 0
            params.append(val); clauses.append(f'{field}=%s')
    if not clauses:
        return jsonify({'error': 'No fields to update.'}), 400

    params += [ann_id, cp['company_id']]
    try:
        rows = query(
            f'UPDATE company_announcements SET {",".join(clauses)} '
            f'WHERE announcement_id=%s AND company_id=%s RETURNING *',
            params
        )
        if not rows:
            return jsonify({'error': 'Announcement not found.'}), 404
        return jsonify({'message': 'Announcement updated.', 'announcement': dict(rows[0])})
    except Exception as e:
        return jsonify({'error': 'Failed to update announcement.'}), 500


@company_bp.delete('/announcements/<int:ann_id>')
@require_auth
@require_role('COMPANY')
def delete_announcement(ann_id):
    cp = _get_company()
    if not cp:
        return jsonify({'error': 'Company profile not found.'}), 404
    try:
        rows = query("""
            DELETE FROM company_announcements
            WHERE  announcement_id=%s AND company_id=%s AND is_published=0
            RETURNING announcement_id
        """, (ann_id, cp['company_id']))
        if not rows:
            return jsonify({'error': 'Announcement not found or already published (cannot delete).'}), 404
        return jsonify({'message': 'Announcement deleted.'})
    except Exception as e:
        return jsonify({'error': 'Failed to delete announcement.'}), 500


@company_bp.get('/financials')
@require_auth
@require_role('COMPANY')
def get_financials():
    try:
        cp = _get_company()
        if not cp:
            return jsonify({'error': 'Company profile not found.'}), 404
        rows = query("""
            SELECT * FROM company_financials
            WHERE  company_id = %s
            ORDER  BY fiscal_year DESC, quarter DESC
        """, (cp['company_id'],))
        return jsonify({'financials': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch financials.'}), 500


@company_bp.post('/financials')
@require_auth
@require_role('COMPANY')
def create_financial():
    body = request.get_json() or {}
    cp   = _get_company()
    if not cp:
        return jsonify({'error': 'Company profile not found.'}), 404

    required = ['quarter', 'fiscal_year', 'revenue', 'net_profit', 'eps']
    if not all(body.get(k) for k in required):
        return jsonify({'error': 'quarter, fiscal_year, revenue, net_profit, eps are required.'}), 400

    quarter = str(body['quarter']).upper()
    if quarter not in ('Q1', 'Q2', 'Q3', 'Q4'):
        return jsonify({'error': 'quarter must be Q1, Q2, Q3 or Q4.'}), 400

    try:
        rows = query("""
            INSERT INTO company_financials
                (company_id, quarter, fiscal_year, revenue, net_profit, eps, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, quarter, fiscal_year) DO UPDATE
                SET revenue=excluded.revenue, net_profit=excluded.net_profit,
                    eps=excluded.eps, published_at=NOW()
            RETURNING *
        """, (cp['company_id'], quarter, int(body['fiscal_year']),
              float(body['revenue']), float(body['net_profit']), float(body['eps'])))
        return jsonify({'message': 'Financial result saved.', 'financial': dict(rows[0])}), 201
    except Exception as e:
        print(f'[COMPANY FINANCIALS] {e}')
        return jsonify({'error': 'Failed to save financial data.'}), 500
