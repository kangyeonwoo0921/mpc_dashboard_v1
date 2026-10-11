from django.urls import path

from .views import ghi_forecast, live_snapshot, mpc_recommendation, radiation_v1, solar_state, viewer


urlpatterns = [
    path("", viewer, name="digital-twin-viewer"),
    path("api/digital-twin/live/", live_snapshot, name="digital-twin-live"),
    path("api/digital-twin/solar/", solar_state, name="digital-twin-solar"),
    path("api/digital-twin/radiation/v1/", radiation_v1, name="digital-twin-radiation-v1"),
    path("api/mpc/recommendation/", mpc_recommendation, name="mpc-recommendation"),  # MOCK until mpc_lab is ready
    path("api/forecast/ghi/", ghi_forecast, name="ghi-forecast"),
]
