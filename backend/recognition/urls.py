from django.urls import path
from .views import JobDetail, JobList

urlpatterns = [path('recognition-jobs/', JobList.as_view()), path('recognition-jobs/<uuid:pk>/', JobDetail.as_view())]

