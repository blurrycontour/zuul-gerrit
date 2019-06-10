import React from "react"
import userManager from "./userManager"


class LoginButton extends React.Component {
   onLoginButtonClick(event) {
       event.preventDefault()
       userManager.signinRedirect();
   }

   render() {
       return (
           <div>
              <button onClick={this.onLoginButtonClick}>Sign in</button>
           </div>
       )
   }
}

export default LoginButton
