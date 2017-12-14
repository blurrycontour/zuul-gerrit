// jquery plugin for Zuul status page
//
// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
// Copyright 2012 OpenStack Foundation
// Copyright 2013 Timo Tijhof
// Copyright 2013 Wikimedia Foundation
// Copyright 2014 Rackspace Australia
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
//
// @licend  The above is the entire license notice
// for the JavaScript code in this page.

import RedImage from './images/red.png'
import GreyImage from './images/grey.png'
import GreenImage from './images/green.png'
import BlackImage from './images/black.png'
import LineImage from './images/line.png'
import LineAngleImage from './images/line-angle.png'
import LineTImage from './images/line-t.png';

(function ($) {
  'use strict'

  function set_cookie (name, value) {
    document.cookie = name + '=' + value + '; path=/'
  }

  function read_cookie (name, default_value) {
    let nameEQ = name + '='
    let ca = document.cookie.split(';')
    for (let i = 0; i < ca.length; i++) {
      let c = ca[i]
      while (c.charAt(0) === ' ') {
        c = c.substring(1, c.length)
      }
      if (c.indexOf(nameEQ) === 0) {
        return c.substring(nameEQ.length, c.length)
      }
    }
    return default_value
  }

  $.zuul = function (options) {
    options = $.extend({
      'enabled': true,
      'graphite_url': '',
      'source': 'status.json',
      'source_data': null,
      'msg_id': '#zuul_msg',
      'pipelines_id': '#zuul_pipelines',
      'queue_events_num': '#zuul_queue_events_num',
      'queue_management_events_num': '#zuul_queue_management_events_num',
      'queue_results_num': '#zuul_queue_results_num'
    }, options)

    let collapsed_exceptions = []
    let current_filter = read_cookie('zuul_filter_string', '')
    let change_set_in_url = window.location.href.split('#')[1]
    if (change_set_in_url) {
      current_filter = change_set_in_url
    }
    let $jq

    let xhr,
      zuul_graph_update_count = 0,
      zuul_sparkline_urls = {}

    function get_sparkline_url (pipeline_name) {
      if (options.graphite_url !== '') {
        if (!(pipeline_name in zuul_sparkline_urls)) {
          zuul_sparkline_urls[pipeline_name] = $.fn.graphite
                        .geturl({
                          url: options.graphite_url,
                          from: '-8hours',
                          width: 100,
                          height: 26,
                          margin: 0,
                          hideLegend: true,
                          hideAxes: true,
                          hideGrid: true,
                          target: [
                            'color(stats.gauges.zuul.pipeline.' + pipeline_name +
                                ".current_changes, '6b8182')"
                          ]
                        })
        }
        return zuul_sparkline_urls[pipeline_name]
      }
      return false
    }

    let format = {
      job: function (job) {
        let $job_line = $('<span />')

        if (job.result !== null) {
          $job_line.append(
                        $('<a />')
                            .addClass('zuul-job-name')
                            .attr('href', job.report_url)
                            .text(job.name)
                    )
        } else if (job.url !== null) {
          $job_line.append(
                        $('<a />')
                            .addClass('zuul-job-name')
                            .attr('href', job.url)
                            .text(job.name)
                    )
        } else {
          $job_line.append(
                        $('<span />')
                            .addClass('zuul-job-name')
                            .text(job.name)
                    )
        }

        $job_line.append(this.job_status(job))

        if (job.voting === false) {
          $job_line.append(
                        $(' <small />')
                            .addClass('zuul-non-voting-desc')
                            .text(' (non-voting)')
                    )
        }

        $job_line.append($('<div style="clear: both"></div>'))
        return $job_line
      },

      job_status: function (job) {
        let result = job.result ? job.result.toLowerCase() : null
        if (result === null) {
          result = job.url ? 'in progress' : 'queued'
        }

        if (result === 'in progress') {
          return this.job_progress_bar(job.elapsed_time,
                                                        job.remaining_time)
        } else {
          return this.status_label(result)
        }
      },

      status_label: function (result) {
        let $status = $('<span />')
        $status.addClass('zuul-job-result label')

        switch (result) {
          case 'success':
            $status.addClass('label-success')
            break
          case 'failure':
            $status.addClass('label-danger')
            break
          case 'unstable':
            $status.addClass('label-warning')
            break
          case 'skipped':
            $status.addClass('label-info')
            break
          // 'in progress' 'queued' 'lost' 'aborted' ...
          default:
            $status.addClass('label-default')
        }
        $status.text(result)
        return $status
      },

      job_progress_bar: function (elapsed_time, remaining_time) {
        let progress_percent = 100 * (elapsed_time / (elapsed_time +
                                                              remaining_time))
        let $bar_inner = $('<div />')
                    .addClass('progress-bar')
                    .attr('role', 'progressbar')
                    .attr('aria-valuenow', 'progressbar')
                    .attr('aria-valuemin', progress_percent)
                    .attr('aria-valuemin', '0')
                    .attr('aria-valuemax', '100')
                    .css('width', progress_percent + '%')

        let $bar_outter = $('<div />')
                    .addClass('progress zuul-job-result')
                    .append($bar_inner)

        return $bar_outter
      },

      enqueue_time: function (ms) {
        // Special format case for enqueue time to add style
        let hours = 60 * 60 * 1000
        let now = Date.now()
        let delta = now - ms
        let status = 'text-success'
        let text = this.time(delta, true)
        if (delta > (4 * hours)) {
          status = 'text-danger'
        } else if (delta > (2 * hours)) {
          status = 'text-warning'
        }
        return '<span class="' + status + '">' + text + '</span>'
      },

      time: function (ms, words) {
        if (typeof (words) === 'undefined') {
          words = false
        }
        let seconds = (+ms) / 1000
        let minutes = Math.floor(seconds / 60)
        let hours = Math.floor(minutes / 60)
        seconds = Math.floor(seconds % 60)
        minutes = Math.floor(minutes % 60)
        let r = ''
        if (words) {
          if (hours) {
            r += hours
            r += ' hr '
          }
          r += minutes + ' min'
        } else {
          if (hours < 10) {
            r += '0'
          }
          r += hours + ':'
          if (minutes < 10) {
            r += '0'
          }
          r += minutes + ':'
          if (seconds < 10) {
            r += '0'
          }
          r += seconds
        }
        return r
      },

      change_total_progress_bar: function (change) {
        let job_percent = Math.floor(100 / change.jobs.length)
        let $bar_outter = $('<div />')
                    .addClass('progress zuul-change-total-result')

        $.each(change.jobs, function (i, job) {
          let result = job.result ? job.result.toLowerCase() : null
          if (result === null) {
            result = job.url ? 'in progress' : 'queued'
          }

          if (result !== 'queued') {
            let $bar_inner = $('<div />')
                            .addClass('progress-bar')

            switch (result) {
              case 'success':
                $bar_inner.addClass('progress-bar-success')
                break
              case 'lost':
              case 'failure':
                $bar_inner.addClass('progress-bar-danger')
                break
              case 'unstable':
                $bar_inner.addClass('progress-bar-warning')
                break
              case 'in progress':
              case 'queued':
                break
            }
            $bar_inner.attr('title', job.name)
                            .css('width', job_percent + '%')
            $bar_outter.append($bar_inner)
          }
        })
        return $bar_outter
      },

      change_header: function (change) {
        let change_id = change.id || 'NA'

        let $change_link = $('<small />')
        if (change.url !== null) {
          let github_id = change_id.match(/^([0-9]+),([0-9a-f]{40})$/)
          if (github_id) {
            $change_link.append(
                            $('<a />').attr('href', change.url).append(
                                $('<abbr />')
                                    .attr('title', change_id)
                                    .text('#' + github_id[1])
                            )
                        )
          } else if (/^[0-9a-f]{40}$/.test(change_id)) {
            let change_id_short = change_id.slice(0, 7)
            $change_link.append(
                            $('<a />').attr('href', change.url).append(
                                $('<abbr />')
                                    .attr('title', change_id)
                                    .text(change_id_short)
                            )
                        )
          } else {
            $change_link.append(
                            $('<a />').attr('href', change.url).text(change_id)
                        )
          }
        } else {
          if (change_id.length === 40) {
            change_id = change_id.substr(0, 7)
          }
          $change_link.text(change_id)
        }

        let $change_progress_row_left = $('<div />')
                    .addClass('col-xs-4')
                    .append($change_link)
        let $change_progress_row_right = $('<div />')
                    .addClass('col-xs-8')
                    .append(this.change_total_progress_bar(change))

        let $change_progress_row = $('<div />')
                    .addClass('row')
                    .append($change_progress_row_left)
                    .append($change_progress_row_right)

        let $project_span = $('<span />')
                    .addClass('change_project')
                    .text(change.project)

        let $left = $('<div />')
                    .addClass('col-xs-8')
                    .append($project_span, $change_progress_row)

        let remaining_time = this.time(
                        change.remaining_time, true)
        let enqueue_time = this.enqueue_time(
                        change.enqueue_time)
        let $remaining_time = $('<small />').addClass('time')
                    .attr('title', 'Remaining Time').html(remaining_time)
        let $enqueue_time = $('<small />').addClass('time')
                    .attr('title', 'Elapsed Time').html(enqueue_time)

        let $right = $('<div />')
        if (change.live === true) {
          $right.addClass('col-xs-4 text-right')
                        .append($remaining_time, $('<br />'), $enqueue_time)
        }

        let $header = $('<div />')
                    .addClass('row')
                    .append($left, $right)
        return $header
      },

      change_list: function (jobs) {
        let format = this
        let $list = $('<ul />')
                    .addClass('list-group zuul-patchset-body')

        $.each(jobs, function (i, job) {
          let $item = $('<li />')
                        .addClass('list-group-item')
                        .addClass('zuul-change-job')
                        .append(format.job(job))
          $list.append($item)
        })

        return $list
      },

      change_panel: function (change) {
        let $header = $('<div />')
                    .addClass('panel-heading zuul-patchset-header')
                    .append(this.change_header(change))

        let panel_id = change.id ? change.id.replace(',', '_')
                                         : change.project.replace('/', '_') +
                                           '-' + change.enqueue_time
        let $panel = $('<div />')
                    .attr('id', panel_id)
                    .addClass('panel panel-default zuul-change')
                    .append($header)
                    .append(this.change_list(change.jobs))

        $header.click(this.toggle_patchset)
        return $panel
      },

      change_status_icon: function (change) {
        let icon_file = GreenImage
        let icon_title = 'Succeeding'

        if (change.active !== true) {
          // Grey icon
          icon_file = GreyImage
          icon_title = 'Waiting until closer to head of queue to' +
                        ' start jobs'
        } else if (change.live !== true) {
          // Grey icon
          icon_file = GreyImage
          icon_title = 'Dependent change required for testing'
        } else if (change.failing_reasons &&
                         change.failing_reasons.length > 0) {
          let reason = change.failing_reasons.join(', ')
          icon_title = 'Failing because ' + reason
          if (reason.match(/merge conflict/)) {
            // Black icon
            icon_file = BlackImage
          } else {
            // Red icon
            icon_file = RedImage
          }
        }

        let $icon = $('<img />')
                    .attr('src', icon_file)
                    .attr('title', icon_title)
                    .css('margin-top', '-6px')

        return $icon
      },

      change_with_status_tree: function (change, change_queue) {
        let $change_row = $('<tr />')

        for (let i = 0; i < change_queue._tree_columns; i++) {
          let $tree_cell = $('<td />')
                        .css('height', '100%')
                        .css('padding', '0 0 10px 0')
                        .css('margin', '0')
                        .css('width', '16px')
                        .css('min-width', '16px')
                        .css('overflow', 'hidden')
                        .css('vertical-align', 'top')

          if (i < change._tree.length && change._tree[i] !== null) {
            $tree_cell.css('background-image',
                                       'url(' + LineImage + ')')
                            .css('background-repeat', 'repeat-y')
          }

          if (i === change._tree_index) {
            $tree_cell.append(
                            this.change_status_icon(change))
          }
          if (change._tree_branches.indexOf(i) !== -1) {
            let $image = $('<img />')
                            .css('vertical-align', 'baseline')
            if (change._tree_branches.indexOf(i) ===
                            change._tree_branches.length - 1) {
              // Angle line
              $image.attr('src', LineAngleImage)
            } else {
              // T line
              $image.attr('src', LineTImage)
            }
            $tree_cell.append($image)
          }
          $change_row.append($tree_cell)
        }

        let change_width = 360 - 16 * change_queue._tree_columns
        let $change_column = $('<td />')
                    .css('width', change_width + 'px')
                    .addClass('zuul-change-cell')
                    .append(this.change_panel(change))

        $change_row.append($change_column)

        let $change_table = $('<table />')
                    .addClass('zuul-change-box')
                    .css('-moz-box-sizing', 'content-box')
                    .css('box-sizing', 'content-box')
                    .append($change_row)

        return $change_table
      },

      pipeline_sparkline: function (pipeline_name) {
        if (options.graphite_url !== '') {
          let $sparkline = $('<img />')
                        .addClass('pull-right')
                        .attr('src', get_sparkline_url(pipeline_name))
          return $sparkline
        }
        return false
      },

      pipeline_header: function (pipeline, count) {
        // Format the pipeline name, sparkline and description
        let $header_div = $('<div />')
                    .addClass('zuul-pipeline-header')

        let $heading = $('<h3 />')
                    .css('vertical-align', 'middle')
                    .text(pipeline.name)
                    .append(
                        $('<span />')
                            .addClass('badge pull-right')
                            .css('vertical-align', 'middle')
                            .css('margin-top', '0.5em')
                            .text(count)
                    )
                    .append(this.pipeline_sparkline(pipeline.name))

        $header_div.append($heading)

        if (typeof pipeline.description === 'string') {
          let descr = $('<small />')
          $.each(pipeline.description.split(/\r?\n\r?\n/), function (index, descr_part) {
            descr.append($('<p />').text(descr_part))
          })
          $header_div.append(
                        $('<p />').append(descr)
                    )
        }
        return $header_div
      },

      pipeline: function (pipeline, count) {
        let format = this
        let $html = $('<div />')
                    .addClass('zuul-pipeline col-md-4')
                    .append(this.pipeline_header(pipeline, count))

        $.each(pipeline.change_queues,
                       function (queue_i, change_queue) {
                         $.each(change_queue.heads, function (head_i, changes) {
                           if (pipeline.change_queues.length > 1 &&
                            head_i === 0) {
                             let name = change_queue.name
                             let short_name = name
                             if (short_name.length > 32) {
                               short_name = short_name.substr(0, 32) + '...'
                             }
                             $html.append(
                                $('<p />')
                                    .text('Queue: ')
                                    .append(
                                        $('<abbr />')
                                            .attr('title', name)
                                            .text(short_name)
                                    )
                            )
                           }

                           $.each(changes, function (change_i, change) {
                             let $change_box =
                                format.change_with_status_tree(
                                    change, change_queue)
                             $html.append($change_box)
                             format.display_patchset($change_box)
                           })
                         })
                       })
        return $html
      },

      toggle_patchset: function (e) {
        // Toggle showing/hiding the patchset when the header is clicked.
        if (e.target.nodeName.toLowerCase() === 'a') {
                    // Ignore clicks from gerrit patch set link
          return
        }

        // Grab the patchset panel
        let $panel = $(e.target).parents('.zuul-change')
        let $body = $panel.children('.zuul-patchset-body')
        $body.toggle(200)
        let collapsed_index = collapsed_exceptions.indexOf(
                    $panel.attr('id'))
        if (collapsed_index === -1) {
          // Currently not an exception, add it to list
          collapsed_exceptions.push($panel.attr('id'))
        } else {
          // Currently an except, remove from exceptions
          collapsed_exceptions.splice(collapsed_index, 1)
        }
      },

      display_patchset: function ($change_box, animate) {
        // Determine if to show or hide the patchset and/or the results
        // when loaded

        // See if we should hide the body/results
        let $panel = $change_box.find('.zuul-change')
        let panel_change = $panel.attr('id')
        let $body = $panel.children('.zuul-patchset-body')
        let expand_by_default = $('#expand_by_default')
                    .prop('checked')

        let collapsed_index = collapsed_exceptions
                    .indexOf(panel_change)

        if (expand_by_default && collapsed_index === -1 ||
                    !expand_by_default && collapsed_index !== -1) {
          // Expand by default, or is an exception
          $body.show(animate)
        } else {
          $body.hide(animate)
        }

        // Check if we should hide the whole panel
        let panel_project = $panel.find('.change_project').text()
                    .toLowerCase()

        let panel_pipeline = $change_box
                    .parents('.zuul-pipeline')
                    .find('.zuul-pipeline-header > h3')
                    .html()
                    .toLowerCase()

        if (current_filter !== '') {
          let show_panel = false
          let filter = current_filter.trim().split(/[\s,]+/)
          $.each(filter, function (index, f_val) {
            if (f_val !== '') {
              f_val = f_val.toLowerCase()
              if (panel_project.indexOf(f_val) !== -1 ||
                      panel_pipeline.indexOf(f_val) !== -1 ||
                      panel_change.indexOf(f_val) !== -1) {
                show_panel = true
              }
            }
          })
          if (show_panel === true) {
            $change_box.show(animate)
          } else {
            $change_box.hide(animate)
          }
        } else {
          $change_box.show(animate)
        }
      }
    }

    let app = {
      schedule: function (app) {
        app = app || this
        if (!options.enabled) {
          setTimeout(function () { app.schedule(app) }, 5000)
          return
        }
        app.update().always(function () {
          setTimeout(function () { app.schedule(app) }, 5000)
        })

        // Only update graphs every minute
        if (zuul_graph_update_count > 11) {
          zuul_graph_update_count = 0
          zuul.update_sparklines()
        }
      },
      injest: function (data, $msg) {
        if ('message' in data) {
          $msg.removeClass('alert-danger')
                        .addClass('alert-info')
                        .text(data.message)
                        .show()
        } else {
          $msg.empty()
                        .hide()
        }

        if ('zuul_version' in data) {
          $('#zuul-version-span').text(data.zuul_version)
        }
        if ('last_reconfigured' in data) {
          let last_reconfigured =
                        new Date(data.last_reconfigured)
          $('#last-reconfigured-span').text(
                        last_reconfigured.toString())
        }

        let $pipelines = $(options.pipelines_id)
        $pipelines.html('')
        $.each(data.pipelines, function (i, pipeline) {
          let count = app.create_tree(pipeline)
          $pipelines.append(
                        format.pipeline(pipeline, count))
        })

        $(options.queue_events_num).text(
                    data.trigger_event_queue
                        ? data.trigger_event_queue.length : '0'
                )
        $(options.queue_results_num).text(
                    data.result_event_queue
                        ? data.result_event_queue.length : '0'
                )
      },
      /** @return {jQuery.Promise} */
      update: function () {
        // Cancel the previous update if it hasn't completed yet.
        if (xhr) {
          xhr.abort()
        }

        this.emit('update-start')
        let app = this

        let $msg = $(options.msg_id)
        if (options.source_data !== null) {
          app.injest(options.source_data, $msg)
          return
        }
        xhr = $.getJSON(options.source)
                    .done(function (data) {
                      app.injest(data, $msg)
                    })
                    .fail(function (jqXHR, statusText, errMsg) {
                      if (statusText === 'abort') {
                        return
                      }
                      $msg.text(options.source + ': ' + errMsg)
                            .addClass('alert-danger')
                            .removeClass('zuul-msg-wrap-off')
                            .show()
                    })
                    .always(function () {
                      xhr = undefined
                      app.emit('update-end')
                    })

        return xhr
      },

      update_sparklines: function () {
        $.each(zuul_sparkline_urls, function (name, url) {
          let newimg = new Image()
          let parts = url.split('#')
          newimg.src = parts[0] + '#' + new Date().getTime()
          $(newimg).load(function () {
            zuul_sparkline_urls[name] = newimg.src
          })
        })
      },

      emit: function () {
        $jq.trigger.apply($jq, arguments)
        return this
      },
      on: function () {
        $jq.on.apply($jq, arguments)
        return this
      },
      one: function () {
        $jq.one.apply($jq, arguments)
        return this
      },

      control_form: function () {
        // Build the filter form filling anything from cookies

        let $control_form = $('<form />')
                    .attr('role', 'form')
                    .addClass('form-inline')
                    .submit(this.handle_filter_change)

        $control_form
                    .append(this.filter_form_group())
                    .append(this.expand_form_group())

        return $control_form
      },

      filter_form_group: function () {
        // Update the filter form with a clear button if required

        let $label = $('<label />')
                    .addClass('control-label')
                    .attr('for', 'filter_string')
                    .text('Filters')
                    .css('padding-right', '0.5em')

        let $input = $('<input />')
                    .attr('type', 'text')
                    .attr('id', 'filter_string')
                    .addClass('form-control')
                    .attr('title',
                          'project(s), pipeline(s) or review(s) comma ' +
                          'separated')
                    .attr('value', current_filter)

        $input.change(this.handle_filter_change)

        let $clear_icon = $('<span />')
                    .addClass('form-control-feedback')
                    .addClass('glyphicon glyphicon-remove-circle')
                    .attr('id', 'filter_form_clear_box')
                    .attr('title', 'clear filter')
                    .css('cursor', 'pointer')

        $clear_icon.click(function () {
          $('#filter_string').val('').change()
        })

        if (current_filter === '') {
          $clear_icon.hide()
        }

        let $form_group = $('<div />')
                    .addClass('form-group has-feedback')
                    .append($label, $input, $clear_icon)
        return $form_group
      },

      expand_form_group: function () {
        let expand_by_default = (
                    read_cookie('zuul_expand_by_default', false) === 'true')

        let $checkbox = $('<input />')
                    .attr('type', 'checkbox')
                    .attr('id', 'expand_by_default')
                    .prop('checked', expand_by_default)
                    .change(this.handle_expand_by_default)

        let $label = $('<label />')
                    .css('padding-left', '1em')
                    .html('Expand by default: ')
                    .append($checkbox)

        let $form_group = $('<div />')
                    .addClass('checkbox')
                    .append($label)
        return $form_group
      },

      handle_filter_change: function () {
        // Update the filter and save it to a cookie
        current_filter = $('#filter_string').val()
        set_cookie('zuul_filter_string', current_filter)
        if (current_filter === '') {
          $('#filter_form_clear_box').hide()
        } else {
          $('#filter_form_clear_box').show()
        }

        $('.zuul-change-box').each(function (index, obj) {
          let $change_box = $(obj)
          format.display_patchset($change_box, 200)
        })
        return false
      },

      handle_expand_by_default: function (e) {
        // Handle toggling expand by default
        set_cookie('zuul_expand_by_default', e.target.checked)
        collapsed_exceptions = []
        $('.zuul-change-box').each(function (index, obj) {
          let $change_box = $(obj)
          format.display_patchset($change_box, 200)
        })
      },

      create_tree: function (pipeline) {
        let count = 0
        let pipeline_max_tree_columns = 1
        $.each(pipeline.change_queues, function (change_queue_i,
                                                           change_queue) {
          let tree = []
          let max_tree_columns = 1
          let changes = []
          let last_tree_length = 0
          $.each(change_queue.heads, function (head_i, head) {
            $.each(head, function (change_i, change) {
              changes[change.id] = change
              change._tree_position = change_i
            })
          })
          $.each(change_queue.heads, function (head_i, head) {
            $.each(head, function (change_i, change) {
              if (change.live === true) {
                count += 1
              }
              let idx = tree.indexOf(change.id)
              if (idx > -1) {
                change._tree_index = idx
                // remove...
                tree[idx] = null
                while (tree[tree.length - 1] === null) {
                  tree.pop()
                }
              } else {
                change._tree_index = 0
              }
              change._tree_branches = []
              change._tree = []
              if (typeof (change.items_behind) === 'undefined') {
                change.items_behind = []
              }
              change.items_behind.sort(function (a, b) {
                return (changes[b]._tree_position -
                                        changes[a]._tree_position)
              })
              $.each(change.items_behind, function (i, id) {
                tree.push(id)
                if (tree.length > last_tree_length &&
                                    last_tree_length > 0) {
                  change._tree_branches.push(
                                        tree.length - 1)
                }
              })
              if (tree.length > max_tree_columns) {
                max_tree_columns = tree.length
              }
              if (tree.length > pipeline_max_tree_columns) {
                pipeline_max_tree_columns = tree.length
              }
              change._tree = tree.slice(0)  // make a copy
              last_tree_length = tree.length
            })
          })
          change_queue._tree_columns = max_tree_columns
        })
        pipeline._tree_columns = pipeline_max_tree_columns
        return count
      }
    }

    $jq = $(app)
    return {
      options: options,
      format: format,
      app: app,
      jq: $jq
    }
  }
}(jQuery))
