// Copyright 2020 Red Hat, Inc
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

import PropTypes from 'prop-types'
import React from 'react'
import Select from 'react-select'
import { GlobeIcon } from '@patternfly/react-icons'
import { connect } from 'react-redux'

import { t } from '../locales/utils'

import { supportedLocales, fallbackLocale } from '../locales/config'
import { setLocaleWithFallback } from '../actions/i18n'

class LanguageSelector extends React.Component {
  static propTypes = {
    dispatch: PropTypes.func,
  }

  state = {
    availableLanguages: Object.keys(supportedLocales).map(key => (
      {value: key, label: supportedLocales[key]}
    )),
    defaultLanguage: {value: fallbackLocale, label: supportedLocales[fallbackLocale]}
  }

  componentDidMount () {
    this.loadState()
  }

  loadState = () => {
    const { defaultLanguage } = this.state
    let lg = localStorage.getItem('zuul_language') || ''
    if (lg) {
      this.updateState(
        {value: lg, label: supportedLocales[lg]}
      )
    } else {
      this.updateState(defaultLanguage)
    }
  }

  handleChange = (language) => {
    const lg =  language.value
    localStorage.setItem('zuul_language', lg)
    this.updateState(language)
  }

  updateState = (language) => {
    this.setState(
      {currentValue: language}
    )
    let lg = language.value
    let lgAction = setLocaleWithFallback(lg)
    this.props.dispatch(lgAction)
  }

  render () {
    // from selectTz
    const textColor = '#d1d1d1'
    const containerStyles= {
      border: 'solid #2b2b2b',
      borderWidth: '0 0 0 1px',
      cursor: 'pointer',
      display: 'initial',
      padding: '6px'
    }
    const customStyles = {
      container: () => ({
        display: 'inline-block',
      }),
      control: () => ({
        width: 'auto',
        display: 'flex'
      }),
      singleValue: () => ({
        color: textColor,
      }),
      input: (provided) => ({
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
        <GlobeIcon />
        <Select
          className="zuul-select-tz"
          styles={customStyles}
          value={this.state.currentValue}
          onChange={this.handleChange}
          options={this.state.availableLanguages}
          noOptionsMessage={() => t('No language found')}
          placeholder={t('Select language')}
          defaultValue={this.state.defaultLanguage}
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
    )
  }

}

export default connect(state => ({locale: state.i18n.locale}))(LanguageSelector)
