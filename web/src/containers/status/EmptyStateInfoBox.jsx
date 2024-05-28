import React from 'react'
import PropTypes from 'prop-types'

import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateIcon,
  EmptyStateSecondaryActions,
  Title,
} from '@patternfly/react-core'
import { StreamIcon } from '@patternfly/react-icons'

function EmptyStateInfoBox({ onClearFiltersCallback }) {
  return (
    <EmptyState>
      <EmptyStateIcon icon={StreamIcon} />
      <Title headingLevel="h1">No items found</Title>
      <EmptyStateBody>
        No items match this filter criteria. Remove some filters or
        clear all to show results.
      </EmptyStateBody>
      <EmptyStateSecondaryActions>
        <Button variant="link" onClick={onClearFiltersCallback}>
          Clear all filters
        </Button>
      </EmptyStateSecondaryActions>
    </EmptyState>
  )
}

EmptyStateInfoBox.propTypes = {
    onClearFiltersCallback: PropTypes.func,
}

export default EmptyStateInfoBox
