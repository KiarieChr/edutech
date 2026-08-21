from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JournalEntryViewSet

router = DefaultRouter()
router.register(r'journals', JournalEntryViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
