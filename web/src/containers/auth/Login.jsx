import React from 'react'
import { connect } from 'react-redux'
import { Button } from 'patternfly-react'
import userManager from '../../userManager'

class LoginButton extends React.Component {
    onLoginButtonClick(event) {
      event.preventDefault()
      userManager.signinRedirect()
    }

    render () {
        return (
            <Button onClick={this.onLoginButtonClick}>Log in</Button>
        )
    }
}

export default connect()(LoginButton)
