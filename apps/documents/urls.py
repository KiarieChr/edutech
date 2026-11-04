from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DocumentTemplateViewSet, document_branding_context

router = DefaultRouter()
router.register(r"templates", DocumentTemplateViewSet, basename="document-template")

urlpatterns = [
    path("branding-context/", document_branding_context, name="document-branding-context"),
    path("", include(router.urls)),
]
