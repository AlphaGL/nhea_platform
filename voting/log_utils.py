"""
log_utils.py
============
Convenience wrapper for writing ActivityLog entries throughout views.py.

Usage:
    from .log_utils import log_action

    log_action(
        request,
        action='VOTE_CAST',
        description=f'Voted for {nominee.name} in {category.name}',
        actor=voter,
        target=nominee,
    )
"""

from .models import ActivityLog
from .geo_utils import get_client_ip, get_geo_data


def log_action(
    request,
    action: str,
    description: str = '',
    actor=None,
    target=None,
):
    """
    Write a single ActivityLog row.

    Parameters
    ----------
    request     : Django HttpRequest
    action      : One of ActivityLog.ACTION_CHOICES keys
    description : Human-readable note
    actor       : Voter instance (or None for anonymous/system actions)
    target      : Any Django model instance to record as the affected object
    """
    ip  = get_client_ip(request)
    geo = get_geo_data(ip)

    target_model = target.__class__.__name__ if target else None
    target_id    = str(target.pk)           if target else None
    target_repr  = str(target)[:255]        if target else None

    ua = request.META.get('HTTP_USER_AGENT', '')[:500]

    ActivityLog.objects.create(
        actor       = actor,
        action      = action,
        description = description,
        ip_address  = ip or None,
        country     = geo.get('country') or None,
        region      = geo.get('region')  or None,
        city        = geo.get('city')    or None,
        user_agent  = ua or None,
        target_model = target_model,
        target_id    = target_id,
        target_repr  = target_repr,
    )