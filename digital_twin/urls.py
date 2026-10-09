from django.urls import path

from .views import live_snapshot, radiation_v1, solar_state, viewer


urlpatterns = [
    path("", viewer, name="digital-twin-viewer"),
    path("api/digital-twin/live/", live_snapshot, name="digital-twin-live"),
    path("api/digital-twin/solar/", solar_state, name="digital-twin-solar"),
    path("api/digital-twin/radiation/v1/", radiation_v1, name="digital-twin-radiation-v1"),
]
