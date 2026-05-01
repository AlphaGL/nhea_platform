"""
geo_utils.py
============
Lightweight IP geolocation using the free ip-api.com endpoint.
No API key required for non-commercial use (up to 45 req/min).

Usage:
    from .geo_utils import get_geo_data, get_client_ip

    ip   = get_client_ip(request)
    geo  = get_geo_data(ip)
    # geo = {'country': 'Nigeria', 'region': 'Lagos', 'city': 'Lagos',
    #         'lat': 6.45, 'lon': 3.4, 'isp': '...'}
"""

import requests
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

GEO_CACHE_PREFIX = "nhea_geo_"
GEO_CACHE_TTL    = 60 * 60 * 6   # 6 hours


def get_client_ip(request) -> str:
    """Extract the real client IP from the request (handles proxies/Vercel)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = request.META.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip.strip()
    return request.META.get('REMOTE_ADDR', '')


def get_geo_data(ip: str) -> dict:
    """
    Return geo data dict for the given IP.
    Falls back to empty dict on any error.
    Caches results to avoid hammering the API.
    """
    if not ip or ip in ('127.0.0.1', '::1', 'testserver'):
        return {}

    cache_key = f"{GEO_CACHE_PREFIX}{ip.replace('.', '_').replace(':', '_')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={'fields': 'status,country,regionName,city,lat,lon,isp,query'},
            timeout=3,
        )
        data = resp.json()
        if data.get('status') == 'success':
            result = {
                'country': data.get('country', ''),
                'region':  data.get('regionName', ''),
                'city':    data.get('city', ''),
                'lat':     data.get('lat'),
                'lon':     data.get('lon'),
                'isp':     data.get('isp', ''),
            }
            cache.set(cache_key, result, GEO_CACHE_TTL)
            return result
    except Exception as exc:
        logger.warning("Geo lookup failed for %s: %s", ip, exc)

    cache.set(cache_key, {}, 60 * 10)   # cache miss for 10 min
    return {}