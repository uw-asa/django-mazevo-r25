/*jslint browser: true, plusplus: true */
/*global jQuery, Handlebars, moment */


var EMSWhenIWork = (function ($) {
    "use strict";

    var term_lookahead = 4;

    // prep for api post/put
    function csrfSafeMethod(method) {
        // these HTTP methods do not require CSRF protection
        return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
    }

    function search_in_progress(selector) {
        var tpl = Handlebars.compile($("#ajax-waiting").html());
        $(selector).html(tpl());
    }

    function event_search_in_progress() {
        $("form.event-search button").attr('disabled', 'disabled');
        search_in_progress(".event-search-result");
    }

    function event_search_complete() {
        $("form.event-search button").removeAttr('disabled');
    }

    function button_loading(node) {
        var cluster = node.closest('.schedule-button-cluster');

        $('.btn.group > button', cluster).attr('disabled', 'disabled');
        $('.loading', cluster).show();
    }

    function button_stop_loading(node) {
        var cluster = node.closest('.schedule-button-cluster');

        $('.loading', cluster).hide();
        $('.btn.group > button', cluster).removeAttr('disabled');
    }

    function api_path(service, params) {
        var query;

        var url = window.scheduler.app_url + 'api/v1/' + service;

        if (params) {
            query = [];
            $.each(params, function (k, v) {
                query.push(k + '=' + encodeURIComponent(v));
            });
            url += '?' + query.join('&');
        }

        return url;
    }

    function update_schedule_buttons(event) {
        var schedule_cluster,
            button_group,
            event_search = false;

        if (event) {
            button_group = $('.btn-group[data-reservation-name="' + event.reservation.name + '"]');
            schedule_cluster = button_group.closest('.schedule-button-cluster');
            event_search = (schedule_cluster.parents('div.event-search').length > 0);

            schedule_cluster.find('.loading').hide();

            if (event.reservation.id) {
                button_group.removeClass('unscheduled');
                button_group.addClass('scheduled');
            } else {
                button_group.removeClass('scheduled');
                button_group.addClass('unscheduled');
            }
        }

        if ($('.list-group .btn-group.unscheduled button').not(':disabled').length) {
            $('.batchswitch button').removeAttr('disabled');
        } else {
            $('.batchswitch button').attr('disabled', 'disabled');
        }
    }

    function paint_serviceorder_schedule(events) {
        var tpl = Handlebars.compile($('#event-search-result-template').html()),
            context = {
                unscheduled: false,
                search_startdate: moment($('input#startdate.input-date').val()).format('MMMM D, YYYY'),
                search_enddate: moment($('input#enddate.input-date').val()).format('MMMM D, YYYY'),
                schedule: []
            };

        window.scheduler.events = {};

        events.sort(function(a,b) {
            return moment(a.reservation.start_time).unix() - moment(b.reservation.start_time).unix();
        });

        $.each(events, function() {

            var event_start_date = moment(this.reservation.start_time),
                event_end_date = moment(this.reservation.end_time),
                now = moment();

            window.scheduler.events[this.reservation.name] = this;

            if (!context.unscheduled) {
                context.unscheduled = (this.reservation.id === null);
            }

            context.schedule.push({
                month_num: event_start_date.format('M'),
                day: event_start_date.format('D'),
                weekday: event_start_date.format('ddd'),
                start_time: event_start_date.format('h:mm a'),
                end_time: event_end_date.format('h:mm a'),
                room: this.room,
                name: this.name,
                reservation_name: this.reservation.name,
                reservation_id: this.reservation.id,
                site_id: this.reservation.site_id,
                in_the_past: false,
                disabled: (this.schedulable &&
                           (this.reservation.id || true) &&
                           event_start_date.isAfter(now)) ? '' : 'disabled',
            });
        });

        if (context.schedule.length) {
            $('.event-search-result').html(tpl(context));
            update_schedule_buttons();
        } else {
            tpl = Handlebars.compile($('#event-search-result-empty-template').html());
            $('.event-search-result').html(tpl({
                search_startdate: moment($('input#startdate.input-date').val()).format('MMMM D, YYYY'),
                search_enddate: moment($('input#enddate.input-date').val()).format('MMMM D, YYYY')
            }));
        }
    }

    function failure_modal(title, default_text, xhr) {
        var tpl = Handlebars.compile($('#ajax-fail-tmpl').html()),
            modal_container,
            failure_text = default_text,
            err;

        if (xhr.hasOwnProperty('responseText')) {
            try {
                err = JSON.parse(xhr.responseText);

                if (err.hasOwnProperty('error')) {
                    failure_text = err.error;
                }
            } catch (ignore) {
            }
        }

        $('body').append(tpl({
            failure_title: title,
            failure_message: failure_text,
            full_failure_message: xhr.responseText
        }));

        modal_container = $('#failure-modal');
        modal_container.modal();
        modal_container.on('hidden.bs.modal', function () {
            $(this).remove();
        });
    }

    function event_search_failure(xhr) {
        $(".event-search-result").empty();
        failure_modal('Service Order Search Failure',
                      'Please try again later.',
                      xhr);
    }

    function do_event_search(ev) {

        var startdate = $('input#startdate.input-date').val(),
            enddate = $('input#enddate.input-date').val();

        ev.preventDefault();

        $.ajax({
            type: 'GET',
            url: api_path('events/',
                          {
                              StartDate: startdate,
                              EndDate: enddate,
                          }),
            beforeSend: event_search_in_progress,
            complete: event_search_complete
        })
            .fail(event_search_failure)
            .done(function (msg) {
                paint_serviceorder_schedule(msg);
            });

    }

    function schedule_r25_reservation(r25_event) {
        var request_data = {
                name: r25_event.reservation.name,
                user_id: r25_event.reservation.user_id,
                account_id: r25_event.reservation.account_id,
                site_id: r25_event.reservation.site_id,
                location_id: r25_event.reservation.location_id,
                position_id: r25_event.reservation.position_id,
                start_time: r25_event.reservation.start_time,
                end_time: r25_event.reservation.end_time
            },
            button = $('.btn-group[data-reservation-name="' +
                       r25_event.reservation.name +
                       '"] > button:first-child');

        if (r25_event.reservation.id) {
            return;
        }

        button_loading(button);

        $.ajax({
            type: 'POST',
            url: api_path('reservation/'),
            processData: false,
            contentType: 'application/json',
            data: JSON.stringify(request_data)
        }).fail(function (xhr) {
            button_stop_loading(button);
            if (xhr.status == 409) {
                var response = JSON.parse(xhr.responseText),
                    format = 'h:mm a';

                failure_modal('Cannot Schedule Shift',
                              'This request conflicts with<p style="text-align: center;">' +
                              response.conflict_name +
                              '</p>scheduled from ' +
                              moment(response.conflict_start).format(format) +
                              ' until ' +
                              moment(response.conflict_end).format(format),
                              {});
            } else {
                failure_modal('Cannot Schedule Shift',
                              'Please try again later.',
                              xhr);
            }
        }).done(function (msg) {
            if (msg.hasOwnProperty('reservation_id')) {
                r25_event.reservation.id = msg.reservation_id;
                update_schedule_buttons(r25_event);
            }
        });
    }

    function remove_r25_reservation(r25_event, button) {
        button_loading(button);
        $.ajax({
            type: 'DELETE',
            url: api_path('reservation/' + r25_event.reservation.id,
                          {
                              name: r25_event.reservation.name,
                          })
        })
            .fail(function (xhr) {
                button_stop_loading(button);
                failure_modal('Cannot Delete Shift',
                              'Please try again later',
                              xhr);
            })
            .done(function (msg) {
                if (msg.hasOwnProperty('deleted_reservation_id') &&
                        msg.deleted_reservation_id == r25_event.reservation.id) {
                    r25_event.reservation.id = null;
                    update_schedule_buttons(r25_event);
                }
            });
    }

    function r25_event(node) {
        return window.scheduler.events[node
                                       .closest('.btn-group')
                                       .attr('data-reservation-name')];
    }

    function r25_set_schedule(e) {
        var pe = r25_event($(e.target));

        schedule_r25_reservation(pe);
    }

    function r25_clear_schedule(e) {
        /* jshint validthis: true */
        var button = $(this),
            pe = r25_event(button);

        if (pe.reservation.id) {
            remove_r25_reservation(pe, button);
        }
    }

    function r25_schedule_all(e) {
        /* jshint validthis: true */
        var button = $(this),
            pe;

        $('.list-group .btn-group.unscheduled > button:first-child').not(':disabled').each(function () {
            pe = r25_event($(this));
            schedule_r25_reservation(pe);
        });

        update_schedule_buttons();
    }

    function schedule_help(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function initialize() {
        $.ajaxSetup({
            crossDomain: false, // obviates need for sameOrigin test
            beforeSend: function (xhr, settings) {
                if (!csrfSafeMethod(settings.type)) {
                    xhr.setRequestHeader("X-CSRFToken", window.scheduler.csrftoken);
                }
            }
        });

        $("form.event-search").submit(do_event_search);
        Handlebars.registerPartial('reservation-list', $('#reservation-list-partial').html());
        Handlebars.registerPartial('schedule-button', $('#schedule-button-partial').html());
        $('body')
            .delegate('.batchswitch .btn-group > button:first-child', 'click', r25_schedule_all)
            .delegate('.list-group .btn-group.unscheduled > button:first-child', 'click', r25_set_schedule)
            .delegate('.list-group .btn-group.scheduled > button:first-child', 'click', r25_clear_schedule);
    }

    $(document).ready(initialize);

    //return {
    //    initialize: initialize
    //};
}(jQuery));
