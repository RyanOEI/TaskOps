import json
import logging
from flask import current_app
from pywebpush import webpush, WebPushException
from app.extensions import db
from app.models import Notification, PushSubscription, User, Team, RoleEnum

logger = logging.getLogger(__name__)


def _send_web_push(subscription, payload_dict):
    """Attempt Web Push dispatch to a single PushSubscription with automatic 404/410 pruning."""
    try:
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_claims = {"sub": current_app.config.get('VAPID_CLAIM_EMAIL', 'mailto:admin@example.com')}
        if not vapid_private_key:
            current_app.logger.warning("[WebPush] VAPID_PRIVATE_KEY is missing or empty. Cannot send web push.")
            return

        sub_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth
            }
        }
        # CRITICAL: ttl must be > 0 (86400s = 24h) so FCM/APNS queues and delivers
        # the notification even when the user's browser/phone is closed or screen off!
        resp = webpush(
            subscription_info=sub_info,
            data=json.dumps(payload_dict),
            vapid_private_key=vapid_private_key,
            vapid_claims=vapid_claims,
            ttl=86400,
            headers={
                "Urgency": "high"
            }
        )
        current_app.logger.info(
            f"[WebPush] Successfully sent push to user {subscription.user_id} (subscription #{subscription.id}). HTTP {resp.status_code if resp else 'OK'}"
        )
    except WebPushException as ex:
        # If subscription is no longer valid or unsubscribed, delete it
        if ex.response is not None and ex.response.status_code in (404, 410):
            try:
                db.session.delete(subscription)
                db.session.commit()
                current_app.logger.info(f"[WebPush] Pruned expired subscription #{subscription.id} for user {subscription.user_id} (status {ex.response.status_code})")
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(f"[WebPush] Failed to delete stale subscription #{subscription.id}: {e}")
        else:
            response_body = ex.response.text if ex.response is not None else 'No response body'
            current_app.logger.error(
                f"[WebPush] WebPushException for user {subscription.user_id}: {ex}. Service response: {response_body}"
            )
    except Exception as e:
        current_app.logger.error(
            f"[WebPush] Unexpected error sending web push to user {subscription.user_id}: {e}",
            exc_info=True
        )


def notify_user(user_id, title, message, target_url=None):
    """Creates a Notification DB record and triggers Web Push to all active subscriptions of user."""
    user = db.session.get(User, user_id)
    if not user:
        current_app.logger.warning(f"[WebPush] notify_user called for non-existent user_id: {user_id}")
        return

    # 1. Create In-App Notification record
    notification = Notification(
        user_id=user.id,
        title=title,
        message=message,
        target_url=target_url or '/'
    )
    db.session.add(notification)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[WebPush] Failed to save in-app notification: {e}")
        return

    # 2. Dispatch Web Push to user subscriptions
    payload = {
        "title": title,
        "body": message,
        "url": target_url or '/'
    }
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    if not subscriptions:
        current_app.logger.info(
            f"[WebPush] User #{user.id} (@{user.username}) has 0 active push subscription(s) registered in database."
        )
        return

    current_app.logger.info(
        f"[WebPush] Dispatching web push to {len(subscriptions)} subscription(s) for user #{user.id} (@{user.username})."
    )
    for sub in subscriptions:
        _send_web_push(sub, payload)


def notify_team(team_id, title, message, target_url=None):
    """Notifies every active member in the specified team."""
    team = db.session.get(Team, team_id)
    if not team:
        return
    for member in team.members:
        if member.is_active:
            notify_user(member.id, title, message, target_url)


def notify_all_admins(title, message, target_url=None):
    """Notifies every active admin user in the system."""
    admins = User.query.filter_by(role=RoleEnum.ADMIN, is_active=True).all()
    for admin in admins:
        notify_user(admin.id, title, message, target_url)

