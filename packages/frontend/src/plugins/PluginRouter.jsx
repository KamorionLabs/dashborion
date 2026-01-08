/**
 * Plugin Router for Dashborion Frontend
 *
 * Dynamic router that loads pages from registered plugins.
 * Uses react-router-dom for URL-based navigation.
 */

import { Suspense, useMemo } from 'react';
import {
  Routes,
  Route,
  useParams,
  useSearchParams,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { usePluginPages, usePlugins } from './PluginContext';

/**
 * Page loading fallback
 */
function PageLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      <span className="ml-3 text-gray-400">Loading...</span>
    </div>
  );
}

/**
 * Page error display
 */
function PageError({ error, pageId }) {
  return (
    <div className="bg-red-900/20 border border-red-500 rounded-lg p-6 m-4">
      <h2 className="text-red-400 font-semibold text-lg">Page Error</h2>
      <p className="text-red-300 mt-2">
        Failed to render page: {pageId}
      </p>
      {error && (
        <pre className="text-xs text-red-200 mt-4 p-3 bg-red-900/30 rounded overflow-auto">
          {error.message || String(error)}
        </pre>
      )}
    </div>
  );
}

/**
 * Not found page
 */
function NotFoundPage() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <h2 className="text-2xl font-semibold text-gray-300">Page Not Found</h2>
      <p className="text-gray-500 mt-2">
        The page <code className="text-gray-400">{location.pathname}</code> does not exist.
      </p>
      <button
        onClick={() => navigate('/')}
        className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
      >
        Go to Dashboard
      </button>
    </div>
  );
}

/**
 * Page wrapper that provides common props to page components
 */
function PageWrapper({ page, config }) {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Convert searchParams to plain object
  const query = useMemo(() => {
    const obj = {};
    searchParams.forEach((value, key) => {
      obj[key] = value;
    });
    return obj;
  }, [searchParams]);

  const Component = page.component;

  if (!Component) {
    return <PageError pageId={page.id} error={new Error('No component defined')} />;
  }

  const pageProps = {
    params,
    query,
    config: config[page.pluginId] || {},
    location,
    onNavigate: (path) => navigate(path),
  };

  try {
    return (
      <Suspense fallback={<PageLoading />}>
        <Component {...pageProps} />
      </Suspense>
    );
  } catch (error) {
    return <PageError pageId={page.id} error={error} />;
  }
}

/**
 * Plugin Router component
 *
 * Renders routes from all registered plugins.
 * Must be used inside a BrowserRouter.
 */
export function PluginRouter({ config = {}, defaultElement = null }) {
  const pages = usePluginPages();
  const { initialized } = usePlugins();

  // Sort pages by path specificity (more specific first)
  const sortedPages = useMemo(() => {
    return [...pages].sort((a, b) => {
      // Count path segments
      const aSegments = a.path.split('/').filter(Boolean).length;
      const bSegments = b.path.split('/').filter(Boolean).length;
      // More segments = more specific = should come first
      return bSegments - aSegments;
    });
  }, [pages]);

  if (!initialized) {
    return <PageLoading />;
  }

  return (
    <Routes>
      {/* Default/home route */}
      {defaultElement && (
        <Route path="/" element={defaultElement} />
      )}

      {/* Plugin pages */}
      {sortedPages.map((page) => (
        <Route
          key={`${page.pluginId}-${page.id}`}
          path={page.path}
          element={<PageWrapper page={page} config={config} />}
        />
      ))}

      {/* Catch-all for 404 */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

/**
 * Hook to get current route params with type safety
 */
export function useRouteParams() {
  const params = useParams();
  return {
    project: params.project,
    environment: params.env || params.environment,
    service: params.service,
    pipeline: params.pipeline,
    ...params,
  };
}

/**
 * Hook to navigate with project/env context preserved
 */
export function usePluginNavigate() {
  const navigate = useNavigate();
  const { project, environment } = useRouteParams();

  return {
    navigate,
    // Navigate within current project/env
    toService: (service) => navigate(`/${project}/${environment}/services/${service}`),
    toServices: () => navigate(`/${project}/${environment}/services`),
    toPipeline: (pipeline) => navigate(`/${project}/${environment}/pipelines/${pipeline}`),
    toPipelines: () => navigate(`/${project}/${environment}/pipelines`),
    toInfrastructure: () => navigate(`/${project}/${environment}/infrastructure`),
    toEvents: () => navigate(`/${project}/${environment}/events`),
    // Navigate to different env
    toEnvironment: (env) => navigate(`/${project}/${env}`),
    // Navigate to different project
    toProject: (proj) => navigate(`/${proj}`),
    // Go home
    toHome: () => navigate('/'),
  };
}

export default PluginRouter;
