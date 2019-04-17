from django.conf.urls import url

from .views import events
from .views.api.schedule import Schedule
from .views.api.reservation import Reservation

urlpatterns = [
    url(r'^$', events.index, name='ems_r25'),

    url(r'^api/v1/reservation/(?P<reservation_id>\d+)?$', Reservation().run),
    url(r'^api/v1/schedule/$', Schedule().run),
]
