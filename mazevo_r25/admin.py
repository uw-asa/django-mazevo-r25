from django.contrib import admin

from . import models

class MazevoRoomSpaceAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'space_id', 'date_changed')
    list_editable = ('space_id',)

admin.site.register(models.MazevoRoomSpace, MazevoRoomSpaceAdmin)
