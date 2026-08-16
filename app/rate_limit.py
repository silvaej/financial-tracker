from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared Limiter instance -- imported by both app/main.py (to wire up the
# exception handler/middleware) and individual routers (to decorate specific
# routes with @limiter.limit(...)). A separate module avoids a circular
# import between the two.
#
# In-memory storage (slowapi's default) resets per process, which is a real
# gap on Vercel's serverless deployment (cold starts get a fresh counter) --
# acceptable for a first pass per issue #72's own scoping (a lightweight
# per-IP limit on just the unauthenticated auth surface), not a guarantee
# against a sufficiently patient distributed attacker. Revisit with a shared
# store (e.g. Redis) if this app's actual abuse patterns ever call for it.
limiter = Limiter(key_func=get_remote_address)
