"""A nearby station is a suggestion, and coordinates must use the same system."""
import math

from ecology.models import Place, Station, WaterBody

MATCH_RADIUS_M = 2000.0


def published_water_bodies():
    return WaterBody.objects.filter(place__is_published=True, place__kind__in=[Place.Kind.RIVER, Place.Kind.LAKE]).select_related('place', 'place__region')


def public_stations():
    return Station.objects.filter(is_active=True, kind=Station.Kind.WATER, place__is_published=True,
                                  water_body__place__is_published=True,
                                  water_body__place__kind__in=[Place.Kind.RIVER, Place.Kind.LAKE])


def haversine(lat1, lon1, lat2, lon2):
    radians = math.pi / 180
    a = math.sin((lat2 - lat1) * radians / 2) ** 2 + math.cos(lat1 * radians) * math.cos(lat2 * radians) * math.sin((lon2 - lon1) * radians / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1, max(0, a))))


def match_water_body(latitude, longitude, coordinate_system):
    if coordinate_system not in {'GCJ02', 'WGS84'} or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (latitude, longitude)):
        raise ValueError('Invalid coordinates')
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Invalid coordinates')
    candidates = public_stations().filter(place__coordinate_system=coordinate_system, place__latitude__isnull=False,
                                         place__longitude__isnull=False).select_related('place', 'water_body__place')
    best, best_distance = None, MATCH_RADIUS_M
    for station in candidates.order_by('pk'):
        point = station.place
        distance = haversine(latitude, longitude, point.latitude, point.longitude)
        if distance < best_distance:
            best, best_distance = station, distance
    if best is None:
        return None
    return {'water_body_id': str(best.water_body_id), 'water_body_name': best.water_body.place.name,
            'station_id': str(best.pk), 'distance_m': round(best_distance), 'suggestion_only': True}
