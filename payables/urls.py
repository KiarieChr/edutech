from rest_framework.routers import DefaultRouter
from .views import VendorViewSet, BillViewSet

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)
router.register(r'bills', BillViewSet)

urlpatterns = router.urls
