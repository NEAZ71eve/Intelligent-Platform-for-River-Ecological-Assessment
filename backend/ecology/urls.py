from django.urls import path

from . import views

urlpatterns = [
    path("regions/", views.RegionList.as_view(), name="region-list"),
    path("places/", views.PlaceList.as_view(), name="place-list"),
    path("places/<uuid:pk>/", views.PlaceDetail.as_view(), name="place-detail"),
    path("maps/", views.MapList.as_view(), name="map-list"),
    path("stations/", views.StationList.as_view(), name="station-list"),
    path("metrics/", views.MetricList.as_view(), name="metric-list"),
    path("data-sources/", views.SourceList.as_view(), name="data-source-list"),
    path("observations/", views.ObservationList.as_view(), name="observation-list"),
    path("weather/", views.EnvironmentalSummary.as_view(), name="weather"),
    path("air-quality/", views.AirQuality.as_view(), name="air-quality"),
    path("weather-alerts/", views.WeatherAlerts.as_view(), name="weather-alerts"),
    path("dashboard/", views.Dashboard.as_view(), name="dashboard"),
]
