"""Background execution for durable discovery work."""

# Worker processes never import the HTTP app, so register every mapped table here;
# otherwise flushes fail to resolve foreign keys such as discovery_scans.user_id.
from app.db import models  # noqa: F401
