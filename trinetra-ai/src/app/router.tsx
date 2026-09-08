import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom';
import { AppShell } from '@/layout/AppShell';
import { LoadingRows } from '@/ui/Feedback';
import { RouteError } from '@/app/RouteError';

/* Route-level code splitting keeps the initial control-room load small. */
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const Cameras = lazy(() => import('@/pages/Cameras'));
const CameraDetail = lazy(() => import('@/pages/CameraDetail'));
const Vehicles = lazy(() => import('@/pages/Vehicles'));
const VideoAnalysis = lazy(() => import('@/pages/VideoAnalysis'));
const VehicleInvestigation = lazy(() => import('@/pages/VehicleInvestigation'));
const Alerts = lazy(() => import('@/pages/Alerts'));
const Events = lazy(() => import('@/pages/Events'));
const GIS = lazy(() => import('@/pages/GIS'));
const Registry = lazy(() => import('@/pages/Registry'));
const Watchlist = lazy(() => import('@/pages/Watchlist'));
const SystemHealth = lazy(() => import('@/pages/SystemHealth'));
const Profile = lazy(() => import('@/pages/Profile'));
const NotFound = lazy(() => import('@/pages/NotFound'));

const page = (el: React.ReactNode) => (
  <Suspense
    fallback={
      <div className="p-6 lg:p-8">
        <div className="rounded-lg border border-line bg-surface-1">
          <LoadingRows label="Loading module" rows={5} />
        </div>
      </div>
    }
  >
    {el}
  </Suspense>
);

const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: page(<Dashboard />) },
      { path: 'cameras', element: page(<Cameras />) },
      { path: 'cameras/:cameraId', element: page(<CameraDetail />) },
      { path: 'vehicles', element: page(<Vehicles />) },
      { path: 'vehicles/:plate', element: page(<VehicleInvestigation />) },
      { path: 'video-analysis', element: page(<VideoAnalysis />) },
      { path: 'alerts', element: page(<Alerts />) },
      { path: 'events', element: page(<Events />) },
      { path: 'gis', element: page(<GIS />) },
      { path: 'registry', element: page(<Registry />) },
      { path: 'watchlist', element: page(<Watchlist />) },
      { path: 'system', element: page(<SystemHealth />) },
      { path: 'profile', element: page(<Profile />) },
      { path: 'dashboard', element: <Navigate to="/" replace /> },
      { path: '*', element: page(<NotFound />) },
    ],
  },
];

export const router = createBrowserRouter(routes);
