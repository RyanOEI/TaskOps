from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Notification

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/', methods=['GET'])
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 15
    pagination = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc(), Notification.id.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template(
        'notifications/index.html',
        notifications=pagination.items,
        pagination=pagination,
        unread_count=unread_count
    )


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()

    if request.is_json:
        return jsonify({'status': 'success', 'message': 'Notification marked as read'})

    target = notification.target_url or url_for('notifications.index')
    return redirect(target)


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()

    if request.is_json:
        return jsonify({'status': 'success', 'message': 'All notifications marked as read'})

    flash('All notifications marked as read.', 'info')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
def unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'unread_count': count})
