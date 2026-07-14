"""
routes/auth.py  →  /api/auth
"""

from flask import Blueprint, request, jsonify, g
from db import query, query_one
from middleware.auth import sign_token, require_auth

auth_bp = Blueprint('auth', __name__)


@auth_bp.post('/login')
def login():
    body     = request.get_json() or {}
    email    = (body.get('email')    or '').strip()
    password =  body.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    try:
        user = query_one(
            """
            SELECT user_id, name, email, password, kyc_status,
                   COALESCE(role, 'USER') AS role
            FROM   users
            WHERE  lower(email) = lower(%s)
            """,
            (email,)
        )

        if not user:
            return jsonify({'error': 'Invalid email or password.'}), 401

        # Plain-text password check (same as Node version)
        if password != user['password']:
            return jsonify({'error': 'Invalid email or password.'}), 401

        # Record login (best-effort)
        try:
            query('SELECT RecordUserLogin(%s)', (user['user_id'],))
        except Exception:
            pass

        token = sign_token(user)

        resp = {
            'token': token,
            'user': {
                'id':    user['user_id'],
                'email': user['email'],
                'name':  user['name'],
                'role':  user['role'] or 'USER',
            },
        }

        # If COMPANY user, also return company_id
        if user['role'] == 'COMPANY':
            cp = query_one(
                'SELECT company_id FROM company_profiles WHERE user_id = %s',
                (user['user_id'],)
            )
            if cp:
                resp['user']['company_id'] = cp['company_id']

        return jsonify(resp)

    except Exception as e:
        print(f'[AUTH] login error: {e}')
        return jsonify({'error': 'Login failed. Please try again.'}), 500


@auth_bp.get('/me')
@require_auth
def me():
    return jsonify({'user': g.user})
