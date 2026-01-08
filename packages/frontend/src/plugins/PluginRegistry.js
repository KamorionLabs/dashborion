/**
 * Plugin Registry for Dashborion Frontend
 *
 * Central registry for all frontend plugins. Plugins register their
 * widgets, pages, and navigation items here.
 */

class PluginRegistryClass {
  constructor() {
    this.plugins = new Map();
    this.initialized = false;
  }

  /**
   * Register a plugin
   * @param {import('@dashborion/core').FrontendPluginDefinition} plugin
   */
  register(plugin) {
    if (this.plugins.has(plugin.id)) {
      console.warn(`[PluginRegistry] Plugin "${plugin.id}" is already registered, skipping`);
      return;
    }

    console.log(`[PluginRegistry] Registering plugin: ${plugin.name} (${plugin.id})`);
    this.plugins.set(plugin.id, plugin);
  }

  /**
   * Initialize all registered plugins
   * @param {Record<string, unknown>} config - Plugin configurations by plugin ID
   */
  async initialize(config = {}) {
    if (this.initialized) {
      console.warn('[PluginRegistry] Already initialized');
      return;
    }

    for (const [id, plugin] of this.plugins) {
      if (plugin.initialize) {
        try {
          console.log(`[PluginRegistry] Initializing plugin: ${id}`);
          await plugin.initialize(config[id] || {});
        } catch (error) {
          console.error(`[PluginRegistry] Failed to initialize plugin ${id}:`, error);
        }
      }
    }

    this.initialized = true;
    console.log(`[PluginRegistry] Initialized ${this.plugins.size} plugins`);
  }

  /**
   * Cleanup all plugins
   */
  async cleanup() {
    for (const [id, plugin] of this.plugins) {
      if (plugin.cleanup) {
        try {
          await plugin.cleanup();
        } catch (error) {
          console.error(`[PluginRegistry] Failed to cleanup plugin ${id}:`, error);
        }
      }
    }
    this.initialized = false;
  }

  /**
   * Get all registered plugins
   * @returns {import('@dashborion/core').FrontendPluginDefinition[]}
   */
  getPlugins() {
    return Array.from(this.plugins.values());
  }

  /**
   * Get a plugin by ID
   * @param {string} id
   * @returns {import('@dashborion/core').FrontendPluginDefinition | undefined}
   */
  getPlugin(id) {
    return this.plugins.get(id);
  }

  /**
   * Get all widgets for a specific position
   * @param {import('@dashborion/core').WidgetPosition} position
   * @returns {import('@dashborion/core').FrontendWidget[]}
   */
  getWidgetsForPosition(position) {
    const widgets = [];

    for (const plugin of this.plugins.values()) {
      if (plugin.widgets) {
        for (const widget of plugin.widgets) {
          if (widget.positions.includes(position)) {
            widgets.push({
              ...widget,
              pluginId: plugin.id,
            });
          }
        }
      }
    }

    // Sort by priority (lower first)
    return widgets.sort((a, b) => (a.priority || 100) - (b.priority || 100));
  }

  /**
   * Get all pages from all plugins
   * @returns {Array<import('@dashborion/core').FrontendPage & { pluginId: string }>}
   */
  getAllPages() {
    const pages = [];

    for (const plugin of this.plugins.values()) {
      if (plugin.pages) {
        for (const page of plugin.pages) {
          pages.push({
            ...page,
            pluginId: plugin.id,
          });
        }
      }
    }

    return pages;
  }

  /**
   * Get all navigation items from all plugins
   * @returns {import('@dashborion/core').NavItem[]}
   */
  getAllNavItems() {
    const navItems = [];

    for (const plugin of this.plugins.values()) {
      if (plugin.navItems) {
        navItems.push(...plugin.navItems);
      }
    }

    return navItems;
  }

  /**
   * Get a detail panel by ID
   * @param {string} id
   * @returns {import('@dashborion/core').FrontendDetailPanel | undefined}
   */
  getDetailPanel(id) {
    for (const plugin of this.plugins.values()) {
      if (plugin.detailPanels) {
        const panel = plugin.detailPanels.find(p => p.id === id);
        if (panel) return panel;
      }
    }
    return undefined;
  }
}

// Singleton instance
export const PluginRegistry = new PluginRegistryClass();

export default PluginRegistry;
