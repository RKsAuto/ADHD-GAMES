"""
Vercel entry point.

Vercel runs the app as a serverless function, so a few things differ from a
long-running server:
  * the app directory is read-only — the JSON backup files go to /tmp, which
    is per-invocation and disposable, so MONGO_URI is REQUIRED here;
  * there is no process to keep warm, so the keep-awake self-ping is off.
Both are set below before the app is imported.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('LOCAL_DATA_DIR', '/tmp')
os.environ.setdefault('SELF_PING_MINUTES', '0')

from server import app  # noqa: E402  (must follow the env setup above)

# Vercel's Python runtime serves this WSGI callable.
app = app
