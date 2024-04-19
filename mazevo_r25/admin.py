from django import forms
from django.contrib import admin
from django.db import models
from django.forms.widgets import Select

from .more_r25 import get_space_list
from .models import MazevoRoomSpace

class MazevoRoomSpaceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MazevoRoomSpaceForm, self).__init__(*args, **kwargs)

        space_id_widget = forms.Select()
        space_id_widget.choices = get_space_list()
        space_id_widget.choices.insert(0, (None, 'Not Defined'))

        self.fields['space_id'].label = 'R25 Space'
        self.fields['space_id'].widget = space_id_widget


class MazevoRoomSpaceAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'space_id', 'date_changed')
    list_editable = ('space_id',)
    form = MazevoRoomSpaceForm

admin.site.register(MazevoRoomSpace, MazevoRoomSpaceAdmin)
