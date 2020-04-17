
import { TIMEZONE_SET } from '../actions/timezone'

export default (state = "UTC", action) => {
    switch (action.type) {
      case TIMEZONE_SET:
        return action.timezone
      default:
        return state
    }
  }
