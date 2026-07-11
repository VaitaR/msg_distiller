import { Navigate, createBrowserRouter } from 'react-router-dom'

import { AppShell } from '../components/layout/app-shell'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <Navigate to="/review" replace />,
      },
      {
        path: 'review',
        lazy: async () => {
          const module = await import('../pages/review-queue/page')
          return { Component: module.ReviewQueuePage }
        },
      },
      {
        path: 'timeline',
        lazy: async () => {
          const module = await import('../pages/timeline/page')
          return { Component: module.TimelinePage }
        },
      },
    ],
  },
])