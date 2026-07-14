"""
middleware/auth.py — JWT authentication helpers for TradeFlow Python backend.
"""

import os
import jwt
from functools import wraps
from flask import request, jsonify, g

SECRET  = os.getenv('JWT_SECRET', 'tradeflow_dev_secret')
ALGORITHM = 'HS256'

VALID_ROLES = {'USER', 'ADMIN', 'COMPANY', 'TRADER', 'ANALYST'}


def sign_token(user: dict) -> str:
    """
    Create a signed JWT for the given user dict.
    user must have: user_id (or id), email, name, role
    """
    import time
    payload = {
        'id':    user.get('user_id') or user.get('id'),
        'email': user.get('email'),
        'name':  user.get('name'),
        'role':  user.get('role', 'USER'),
        'exp':   int(time.time()) + 8 * 3600,   # 8 hours
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def require_auth(f):
    """
    Decorator: verifies JWT in Authorization header.
    On success, sets g.user = decoded payload dict.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required.'}), 401
        token = header[7:]
        try:
            payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
            g.user  = payload          # { id, email, name, role }
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired. Please log in again.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid or expired token.'}), 401
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """
    Decorator factory: ensures g.user.role is in the allowed roles list.
    Must be used AFTER @require_auth.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = (g.user or {}).get('role', '')
            if user_role not in roles:
                return jsonify({
                    'error': f'Requires role: {" or ".join(roles)}'
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
