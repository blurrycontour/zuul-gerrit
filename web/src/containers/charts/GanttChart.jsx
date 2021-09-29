// Copyright 2021 Red Hat, Inc
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


import * as React from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'

import * as moment from 'moment'
import 'moment-duration-format'

import { Chart, ChartBar, ChartAxis, ChartLegend, ChartTooltip } from '@patternfly/react-charts'

import { buildResultLegendData, buildsBarStyle } from './Misc'


function BuildsetGanttChart(props) {
    const { builds, timezone } = props
    const sortedByStartTime = builds.sort((a, b) => {
        if (a.start_time > b.start_time) {
            return -1
        }
        if (a.start_time < b.start_time) {
            return 1
        }
        return 0
    })
    const origin = moment.utc(sortedByStartTime[builds.length - 1].start_time).tz(timezone)

    const longestJobName = builds.reduce((a, build) => (a.length < build.job_name.length ? build.job_name : a), '')

    const data = sortedByStartTime.map((build) => {
        return {
            x: build.job_name,
            y0: (moment.utc(build.start_time).tz(timezone) - origin) / 1000,
            y: (moment.utc(build.end_time).tz(timezone) - origin) / 1000,
            result: build.result,
            started: moment.utc(build.start_time).tz(timezone).format('YYYY-MM-DD HH:mm:ss'),
            ended: moment.utc(build.end_time).tz(timezone).format('YYYY-MM-DD HH:mm:ss'),
        }
    })

    const legendData = builds.map((build) => (
        build.result
    )).filter((result, idx, self) => { return self.indexOf(result) === idx }
    ).map((legend) => ({ name: legend }))

    const uniqueResults = builds.map(
        (build) => (build.result)
    ).filter((result, idx, self) => {
        return self.indexOf(result) === idx
    })

    const chartLegend = buildResultLegendData.filter((legend) => { return uniqueResults.indexOf(legend.name) > -1 })


    return (
        <div style={{ height: Math.max(400, 20 * builds.length) + 'px', width: '900px' }}>
            <Chart
                horizontal
                domainPadding={{ x: 20 }}
                width={750}
                height={Math.max(400, 20 * builds.length)}
                padding={{
                    bottom: 80,
                    left: 8 * longestJobName.length,
                    right: 80,
                    top: 80,
                }}
                legendOrientation='horizontal'
                legendPosition='top'
                legendData={legendData}
                legendComponent={<ChartLegend data={chartLegend} itemsPerRow={4} />}

            >
                <ChartAxis />
                <ChartAxis
                    dependentAxis
                    showGrid
                    tickFormat={(t) => {
                        let format
                        switch (true) {
                            case (t < 180):
                                format = 's [sec]'
                                break
                            case (t < 7200):
                                format = 'm [min]'
                                break
                            default:
                                format = 'h [hr] m [min]'
                        }
                        return moment.duration(t, 'seconds').format(format)
                    }}
                    fixLabelOverlap={true}
                    style={{ tickLabels: { angle: -25, padding: 1, verticalAnchor: 'middle', textAnchor: 'end' } }} />
                <ChartBar
                    data={data}
                    style={buildsBarStyle}
                    labelComponent={
                        <ChartTooltip constrainToVisibleArea />}
                    labels={({ datum }) => `${datum.result}\nStarted ${datum.started}\nEnded ${datum.ended}`}
                />
            </ Chart>
        </div>
    )

}

BuildsetGanttChart.propTypes = {
    builds: PropTypes.array.isRequired,
    timezone: PropTypes.string,
}

export default connect((state) => ({
    timezone: state.timezone,
}))(BuildsetGanttChart)