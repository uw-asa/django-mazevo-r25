from django import forms
from django.contrib import admin

from .models import MazevoRoomSpace, room_names, space_names

class MazevoRoomSpaceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MazevoRoomSpaceForm, self).__init__(*args, **kwargs)

        room_id_widget = forms.Select()
        room_id_widget.choices = []
        for room in room_names:
            room_id_widget.choices.append((room, "{} ({})".format(room, room_names[room])))

        self.fields['room_id'].label = 'Mazevo Room'
        self.fields['room_id'].widget = room_id_widget
        self.fields['room_id'].disabled = True

        space_id_widget = forms.Select()
        space_id_widget.choices = [(None, 'Not Defined')]
        for space in space_names:
            space_id_widget.choices.append((space, "{} ({})".format(space, space_names[space])))

        self.fields['space_id'].label = 'R25 Space'
        self.fields['space_id'].widget = space_id_widget

class MazevoRoomSpaceAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'space_id', 'room_name', 'space_name', 'date_changed')
    form = MazevoRoomSpaceForm

admin.site.register(MazevoRoomSpace, MazevoRoomSpaceAdmin)
