from django.urls import path
from .views import LocationList, WeatherSummary

urlpatterns = [
    path('locations/', LocationList.as_view(), name='weather-data-locations'),
    path('summary/', WeatherSummary.as_view(), name='weather-data-summary'),
]
