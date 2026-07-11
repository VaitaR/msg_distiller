import type { Meta, StoryObj } from '@storybook/react-vite'

import { EmptyState } from './empty-state'

const meta = {
  title: 'Events/States/EmptyState',
  component: EmptyState,
  args: {
    title: 'No events in this queue',
    description: 'Change the filter or widen the search window to see more results.',
  },
  decorators: [
    (Story) => (
      <div className="max-w-xl p-6">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof EmptyState>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}