/**
 * Frontend Plugin interfaces for Dashborion
 *
 * These interfaces define the contract between the frontend shell
 * and the plugins that provide features (ECS, Pipelines, Infrastructure, etc.)
 */

// Generic component type (works with React, Preact, etc.)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ComponentType<P = unknown> = (props: P) => any;

/**
 * Position where a widget can be rendered
 */
export type WidgetPosition =
  | 'dashboard'           // Main dashboard grid
  | 'service-detail'      // Service detail panel
  | 'sidebar'             // Right sidebar
  | 'header'              // Top header area
  | 'bottom-panel';       // Bottom panel (logs, etc.)

/**
 * Widget component props provided by the shell
 */
export interface WidgetProps {
  /** Current project ID */
  projectId: string;
  /** Current environment */
  environment: string;
  /** Plugin configuration */
  config: Record<string, unknown>;
  /** Refresh trigger */
  refreshKey?: number;
  /** Callback to request navigation */
  onNavigate?: (path: string) => void;
  /** Callback to show details panel */
  onShowDetails?: (data: unknown) => void;
}

/**
 * Page component props provided by the shell
 */
export interface PageProps {
  /** Route parameters */
  params: Record<string, string>;
  /** Query parameters */
  query: Record<string, string>;
  /** Plugin configuration */
  config: Record<string, unknown>;
  /** Callback to navigate */
  onNavigate?: (path: string) => void;
}

/**
 * Widget definition
 */
export interface FrontendWidget {
  /** Unique widget ID */
  id: string;
  /** Display name */
  name: string;
  /** React component */
  component: ComponentType<WidgetProps>;
  /** Positions where this widget can be rendered */
  positions: WidgetPosition[];
  /** Default size in grid units (width, height) */
  defaultSize?: { width: number; height: number };
  /** Priority for ordering (lower = first) */
  priority?: number;
}

/**
 * Page definition
 */
export interface FrontendPage {
  /** Unique page ID */
  id: string;
  /** Route path (supports params like :env, :service) */
  path: string;
  /** Page title */
  title: string;
  /** React component */
  component: ComponentType<PageProps>;
  /** Icon component for navigation */
  icon?: ComponentType<{ className?: string }>;
  /** Show in sidebar navigation */
  showInNav?: boolean;
  /** Navigation order (lower = first) */
  navOrder?: number;
  /** Parent page ID for nested navigation */
  parentId?: string;
}

/**
 * Detail panel definition (for right-side panels)
 */
export interface FrontendDetailPanel {
  /** Unique panel ID */
  id: string;
  /** Panel title */
  title: string;
  /** React component */
  component: ComponentType<{ data: unknown; onClose: () => void }>;
  /** Panel width */
  width?: number;
}

/**
 * Navigation item for sidebar
 */
export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon?: ComponentType<{ className?: string }>;
  children?: NavItem[];
}

/**
 * Frontend plugin definition
 */
export interface FrontendPluginDefinition {
  /** Unique plugin identifier (must match backend plugin id) */
  id: string;

  /** Display name */
  name: string;

  /** Plugin version */
  version: string;

  /** Widgets provided by this plugin */
  widgets?: FrontendWidget[];

  /** Pages provided by this plugin */
  pages?: FrontendPage[];

  /** Detail panels provided by this plugin */
  detailPanels?: FrontendDetailPanel[];

  /** Navigation items to add to sidebar */
  navItems?: NavItem[];

  /** Initialize plugin (called once at startup) */
  initialize?: (config: Record<string, unknown>) => Promise<void>;

  /** Cleanup plugin (called on unmount) */
  cleanup?: () => Promise<void>;
}

/**
 * Plugin registry interface
 */
export interface PluginRegistry {
  /** Register a plugin */
  register(plugin: FrontendPluginDefinition): void;

  /** Get all registered plugins */
  getPlugins(): FrontendPluginDefinition[];

  /** Get a plugin by ID */
  getPlugin(id: string): FrontendPluginDefinition | undefined;

  /** Get all widgets for a position */
  getWidgetsForPosition(position: WidgetPosition): FrontendWidget[];

  /** Get all pages */
  getAllPages(): FrontendPage[];

  /** Get all nav items */
  getAllNavItems(): NavItem[];

  /** Get a detail panel by ID */
  getDetailPanel(id: string): FrontendDetailPanel | undefined;
}
