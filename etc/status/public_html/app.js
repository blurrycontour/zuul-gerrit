// Client script for Zuul status page
//
// Copyright 2012 OpenStack Foundation
// Copyright 2013 Timo Tijhof
// Copyright 2013 Wikimedia Foundation
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

(function ($) {
    var $container, $msg, $indicator, $queueInfo, $queueEventsNum,
        $queueResultsNum, $pipelines, $jq;
    var xhr, prevData, zuul,
        demo = location.search.match(/[?&]demo=([^?&]*)/),
        source = demo ?
            './status-' + (demo[1] || 'basic') + '.json-sample' :
            'status.json';
        if (demo[1] == 'openstack-live') {
             source = 'http://zuul.openstack.org/status.json';
        }

    zuul = {
        enabled: true,

        schedule: function () {
            if (!zuul.enabled) {
                setTimeout(zuul.schedule, 5000);
                return;
            }
            zuul.update().complete(function () {
                setTimeout(zuul.schedule, 5000);
            });
        },

        /** @return {jQuery.Promise} */
        update: function () {
            // Cancel the previous update if it hasn't completed yet.
            if (xhr) {
                xhr.abort();
            }

            zuul.emit('update-start');
            xhr = $.ajax({
                url: source,
                dataType: 'text',
                cache: false
            }).done(function (data) {
                data = data || '';

                if (data == prevData) {
                    // Nothing to update
                    return xhr;
                }
                prevData = data;
                data = JSON.parse(data);

                if ('message' in data) {
                    $msg.removeClass('alert-danger').addClass('alert-info');
                    $msg.text(data.message);
                    $msg.show();
                } else {
                    $msg.empty();
                    $msg.hide();
                }

                if ('zuul_version' in data) {
                    $('#zuul-version-span').text(data['zuul_version']);
                }
                if ('last_reconfigured' in data) {
                    var last_reconfigured =
                        new Date(data['last_reconfigured']);
                    $('#last-reconfigured-span').text(
                        last_reconfigured.toString());
                }

                $pipelines.html('');
                $.each(data.pipelines, function (i, pipeline) {
                    $pipelines.append(zuul.format.pipeline(pipeline));
                });

                $queueEventsNum.text(
                    data.trigger_event_queue ?
                        data.trigger_event_queue.length : '0'
                );
                $queueResultsNum.text(
                    data.result_event_queue ?
                        data.result_event_queue.length : '0'
                );
            })
            .fail(function (err, jqXHR, errMsg) {
                $msg.removeClass('alert-info').addClass('alert-danger');
                $msg.text(source + ': ' + errMsg).show();
            })
            .complete(function () {
                xhr = undefined;
                zuul.emit('update-end');
            });

            return xhr;
        },

        format: {
            change: function (change) {
                var $html = $('<div />');

                if (change.id.length === 40) {
                    change.id = change.id.substr(0, 7);
                }

                $html.addClass('panel panel-default zuul-change');

                var $change_header = $('<div />').html(change.project);
                $change_header.addClass('panel-heading');

                if (change.url !== null) {
                    var $id_span = $('<span />').append(
                        $('<a href="' + change.url + '" />').html(change.id)
                    );
                }
                else {
                    var $id_span = $('<span />').html(change.id);
                }
                $change_header.append($id_span.addClass('zuul-change-id'));
                $html.append($change_header);

                var $list = $('<ul />');
                $list.addClass('list-group');
                $.each(change.jobs, function (i, job) {
                    var $item = $('<li />');
                    $item.addClass('list-group-item');
                    $item.addClass('zuul-change-job');

                    if (job.url !== null) {
                        $job_line = $('<a href="' + job.url + '" />').
                            addClass('zuul-change-job-link');
                    }
                    else{
                        $job_line = $('<span />').
                            addClass('zuul-change-job-link');
                    }
                    $job_line.html(job.name);

                    var result = job.result ? job.result.toLowerCase() : null;
                    if (result === null) {
                        result = job.url ? 'in progress' : 'queued';
                    }
                    switch (result) {
                        case 'success':
                            resultClass = ' label-success';
                            break;
                        case 'failure':
                            resultClass = ' label-danger';
                            break;
                        case 'unstable':
                            resultClass = ' label-warning';
                            break;
                        case 'in progress':
                        case 'queued':
                        case 'lost':
                            resultClass = ' label-default';
                            break;
                    }
                    $job_line.append(
                        $('<span />').addClass('zuul-result label').
                            addClass(resultClass).html(result)
                    );

                    if (job.voting === false) {
                        $job_line.append(
                            $(' <span />').addClass('muted').
                                html(' (non-voting)')
                        );
                    }
                    $item.append($job_line);
                    $list.append($item);
                });

                $html.append($list);
                return $html;
            },

            pipeline: function (pipeline) {
                var $html = $('<div />');

                $html.addClass('zuul-pipeline col-md-4');
                $html.append(
                    $('<h3 />').html(pipeline.name)
                );
                if (typeof pipeline.description === 'string') {
                    $html.append(
                        $('<p />').append(
                            $('<small />').html(pipeline.description)
                        )
                    );
                }

                $.each(pipeline.change_queues,
                       function (queueNum, changeQueue) {
                    $.each(changeQueue.heads, function (headNum, changes) {
                        if (pipeline.change_queues.length > 1 &&
                            headNum === 0) {
                            var name = changeQueue.name;
                            if (name.length > 32) {
                                short_name = name.substr(0, 32) + '...';
                            }
                            $html.append(
                                $('<p />').html('Queue: ').append(
                                    $('<abbr />').attr('title', name).
                                        html(short_name)
                                )
                            );
                        }
                        $.each(changes, function (changeNum, change) {
                            $html.append(zuul.format.change(change))
                        });
                    });
                });
                return $html;
            }
        },

        emit: function () {
            $jq.trigger.apply($jq, arguments);
            return this;
        },
        on: function () {
            $jq.on.apply($jq, arguments);
            return this;
        },
        one: function () {
            $jq.one.apply($jq, arguments);
            return this;
        }
    };

    $jq = $(zuul);

    $jq.on('update-start', function () {
        $container.addClass('zuul-container-loading');
        $indicator.addClass('zuul-spinner-on');
    });

    $jq.on('update-end', function () {
        $container.removeClass('zuul-container-loading');
        setTimeout(function () {
            $indicator.removeClass('zuul-spinner-on');
        }, 550);
    });

    $jq.one('update-end', function () {
        // Do this asynchronous so that if the first update adds a message, it
        // will not animate while we fade in the content. Instead it simply
        // appears with the rest of the content.
        setTimeout(function () {
            // Fade in the content
            $container.addClass('zuul-container-ready');
        });
    });

    $(function ($) {
        $msg = $('<div />').addClass('alert').hide();
        $indicator = $('<button class="btn pull-right zuul-spinner">updating '
                       + '<span class="glyphicon glyphicon-refresh"></span>'
                       + '</button>');
        $queueInfo = $('<p>Queue lengths: <span>0</span> events, ' +
                       '<span>0</span> results.</p>');
        $queueEventsNum =  $queueInfo.find('span').eq(0);
        $queueResultsNum =  $queueEventsNum.next();
        $pipelines = $('<div class="row"></div>');
        $zuulVersion = $('<p>Zuul version: <span id="zuul-version-span">' +
                         '</span></p>');
        $lastReconf = $('<p>Last reconfigured: ' +
                        '<span id="last-reconfigured-span"></span></p>');

        $container = $('#zuul-container').append($msg, $indicator,
                                                 $queueInfo, $pipelines,
                                                 $zuulVersion, $lastReconf);

        zuul.schedule();

        $(document).on({
            'show.visibility': function () {
                zuul.enabled = true;
                zuul.update();
            },
            'hide.visibility': function () {
                zuul.enabled = false;
            }
        });
    });
}(jQuery));
