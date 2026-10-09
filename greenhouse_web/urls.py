from django.urls import include, path


urlpatterns = [
    path("", include("digital_twin.urls")),
]
