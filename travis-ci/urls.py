from django.conf.urls import include, url

urlpatterns = [
    url(r'^', include('ems_r25.urls')),
]
