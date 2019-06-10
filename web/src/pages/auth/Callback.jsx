import React from "react";
import { connect } from "react-redux";
import { CallbackComponent } from "redux-oidc";
import userManager from "../../userManager";
import { fetchUserAuthorizations } from '../../actions/auth'


class AuthCallbackPage extends React.Component {
  successCallback = (user) => {
      this.props.dispatch(fetchUserAuthorizations(user))
      this.props.history.push('/')
  }

  errorCallback = (error) => {
      this.props.history.push('/')
  }

  render() {
    return (
      <CallbackComponent
        userManager={userManager}
        successCallback={this.successCallback}
        errorCallback={this.errorCallback}
        >
        <div>You will be redirected shortly...</div>
      </CallbackComponent>
    );
  }
}

export default connect()(AuthCallbackPage);
