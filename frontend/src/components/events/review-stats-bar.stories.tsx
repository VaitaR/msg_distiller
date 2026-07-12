import type { Meta, StoryObj } from '@storybook/react-vite'

import { ReviewStatsBar } from './review-stats-bar'

const meta = {
  title: 'Events/ReviewStatsBar',
  component: ReviewStatsBar,
  args: {
    stats: {
      needs_review: 5,
      approved: 3,
      published: 3,
      rejected: 2,
      archived: 2,
    },
  },
  decorators: [
    (Story) => (
      <div className="p-6">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ReviewStatsBar>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
