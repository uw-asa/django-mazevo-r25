from django import forms
from django.contrib import admin

from .models import MazevoRoomSpace, MazevoStatusMap


class MazevoRoomSpaceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MazevoRoomSpaceForm, self).__init__(*args, **kwargs)

        room_id_widget = forms.Select()
        room_id_widget.choices = []
        for room in MazevoRoomSpace.room_names:
            room_id_widget.choices.append(
                (room, "{} ({})".format(room, MazevoRoomSpace.room_names[room]))
            )

        self.fields["room_id"].label = "Mazevo Room"
        self.fields["room_id"].widget = room_id_widget
        self.fields["room_id"].disabled = True

        space_id_widget = forms.Select()
        space_id_widget.choices = [(None, "Not Defined")]
        for space in MazevoRoomSpace.space_names:
            space_id_widget.choices.append(
                (space, "{} ({})".format(space, MazevoRoomSpace.space_names[space]))
            )

        self.fields["space_id"].label = "R25 Space"
        self.fields["space_id"].widget = space_id_widget


class MazevoRoomSpaceAdmin(admin.ModelAdmin):
    list_display = ("room_id", "space_id", "room_name", "space_name", "date_changed")
    form = MazevoRoomSpaceForm


admin.site.register(MazevoRoomSpace, MazevoRoomSpaceAdmin)


class MazevoStatusMapForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MazevoStatusMapForm, self).__init__(*args, **kwargs)

        status_id_widget = forms.Select()
        status_id_widget.choices = []
        for status in MazevoStatusMap.status_names:
            status_id_widget.choices.append(
                (status, "{} ({})".format(status, MazevoStatusMap.status_names[status]))
            )

        self.fields["status_id"].label = "Mazevo Status"
        self.fields["status_id"].widget = status_id_widget
        self.fields["status_id"].disabled = True

        event_type_id_widget = forms.Select()
        event_type_id_widget.choices = [(MazevoStatusMap.EVENT_TYPE_UNDEFINED, "Not Defined")]
        for event_type in MazevoStatusMap.event_type_names:
            event_type_id_widget.choices.append(
                (
                    event_type,
                    "{} ({})".format(
                        event_type, MazevoStatusMap.event_type_names[event_type]
                    ),
                )
            )

        self.fields["event_type_id"].label = "R25 Event Type"
        self.fields["event_type_id"].widget = event_type_id_widget


class MazevoStatusMapAdmin(admin.ModelAdmin):
    list_display = (
        "status_id",
        "event_type_id",
        "status_name",
        "action",
        "event_type_name",
    )
    form = MazevoStatusMapForm


admin.site.register(MazevoStatusMap, MazevoStatusMapAdmin)
