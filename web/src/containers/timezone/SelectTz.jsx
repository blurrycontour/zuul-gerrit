
import PropTypes from 'prop-types'
import React from 'react';
import Select from 'react-select';
import moment from 'moment-timezone';
import { Icon } from 'patternfly-react'
import { connect, Provider } from 'react-redux'
import { setTimezoneAction } from '../../actions/timezone';

class SelectTz extends React.Component {
   static propTypes = {
      dispatch: PropTypes.func
  }

  state = {
    availableTz: moment.tz.names().map(item => ({value: item, label: item})),
    defaultValue: {value: 'UTC', label: 'UTC'}
  }

  componentDidMount () {
    this.loadState()
  }

  handleChange = (selectedTz) => {
    const tz = selectedTz.value

    this.setCookie("zuul_tz_string", tz)
    this.updateState(tz)
  }

  setCookie (name, value) {
    document.cookie = name + '=' + value + '; path=/'
  }

  loadState = () => {
    function readCookie (name, defaultValue) {
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
      return defaultValue
    }
    let tz = readCookie('zuul_tz_string', '')
    if (tz) {
      this.updateState(tz)
    }
  }

  updateState = (tz) => {

    this.setState({
      currentValue: {value: tz, label: tz}
    })

    let timezoneAction = setTimezoneAction(tz)
    this.props.dispatch(timezoneAction)
  }

  render() {
    const textColor = "#d1d1d1"
    const containerStyles= {
      display: 'initial',
      border: 'solid #2b2b2b',
      borderWidth: '0 0 0 1px',
      padding: '6px',
      fontSize: '11px',
      '&:hover': {
        background: 'rgba(255,255,255,.14)',
        borderLeftColor: '#373737',
        outline: '0',
      }
    }
    const iconStyles = {
      padding: '5px'
    }
    const customStyles = {
      container: () => ({
        display: 'inline-block',
      }),
      control: (provided, state) => ({
        width: 'auto',
        display: 'flex'
      }),
      singleValue: (provided, state) => ({
        color: textColor,
      }),
      input: (provided, state) => ({
        ...provided,
        color: textColor
      }),
      dropdownIndicator:(provided) => ({
        ...provided,
        padding: '3px'
      }),
      indicatorSeparator: () => {},
      menu: (provided) => ({
        ...provided,
        width: 'auto',
        right: '0',
        top: '22px',
      })
    }
    return (
        <div style={containerStyles}>
        <Icon style={iconStyles} type="fa" name="clock-o" />
        <Select
            styles={customStyles}
            autoFqocus={this.props.autoFocus}
            value={this.state.currentValue}
            onChange={this.handleChange}
            options={this.state.availableTz}
            noOptionsMessage={() => 'No api found'}
            placeholder={'Select Tz'}
            defaultValue={this.state.defaultValue}
            theme={(theme) => ({
              ...theme,
              borderRadius: 0,
              spacing: {
              ...theme.spacing,
                baseUnit: 2,
              },
            })}
          />
        </div>
    );
  }
}

export default connect()(SelectTz);
