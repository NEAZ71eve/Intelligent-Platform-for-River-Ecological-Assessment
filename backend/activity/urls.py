from django.urls import path
from .views import FeedbackView, HistoryDetail, HistoryView, RecordDetail, RecordsView, VisitDetail, VisitsView

urlpatterns = [path('favorites/', RecordsView.as_view()), path('favorites/<uuid:pk>/', RecordDetail.as_view()),
               path('histories/', HistoryView.as_view()), path('histories/<uuid:pk>/', HistoryDetail.as_view()),
               path('visits/', VisitsView.as_view()), path('visits/<uuid:pk>/', VisitDetail.as_view()), path('feedback/', FeedbackView.as_view())]

