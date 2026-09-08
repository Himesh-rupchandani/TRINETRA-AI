import { RouterProvider } from 'react-router-dom';
import { AppProviders } from './providers';
import { router } from './router';

export default function App() {
  return (
    <AppProviders>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[2000] focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-xs focus:font-semibold focus:text-white"
      >
        Skip to main content
      </a>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
