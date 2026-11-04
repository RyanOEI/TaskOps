from datetime import datetime, timezone
import logging
from app.extensions import db
from app.models.activity import TaskActivity

logger = logging.getLogger(__name__)


def log_activity(task_id: int, user_id: int, action: str, details: str = None):
    """Record an audit trail activity entry for a task."""
    try:
        activity = TaskActivity(
            task_id=task_id,
            user_id=user_id,
            action=action,
            details=details,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Failed to record task activity: {e}")

