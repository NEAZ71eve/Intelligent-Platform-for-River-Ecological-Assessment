from django.urls import path
from . import views

urlpatterns = [
    path('assessment-jobs/', views.JobList.as_view(), name='assessment-job-list'),
    path('assessment-jobs/<uuid:pk>/', views.JobDetail.as_view(), name='assessment-job-detail'),
    path('water-bodies/', views.WaterBodyList.as_view(), name='assessment-water-bodies'),
    path('nearby-water-bodies/', views.NearbyWaterBodies.as_view(), name='assessment-nearby-water-bodies'),
]
