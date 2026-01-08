/**
 * Infrastructure Resource Handlers Registry
 *
 * This module provides a registry pattern for infrastructure resource handlers.
 * Handlers are NOT defined here - they self-register from their respective
 * component/feature directories.
 *
 * ## How It Works
 *
 * 1. Each resource type has its handler defined alongside its component
 * 2. Handlers self-register via `registerResourceHandler()` on import
 * 3. The registry is populated automatically when components are loaded
 *
 * ## File Structure
 *
 * ```
 * src/
 *   handlers/
 *     index.js              # Imports all handlers (triggers registration)
 *     cloudfront.js         # CloudFront handler
 *     alb.js                # ALB handler
 *     task.js               # ECS Task handler (composite ID example)
 *     ...
 * ```
 *
 * ## Handler Interface
 *
 * Each handler must implement:
 *
 * ```javascript
 * {
 *   // Required: Extract ID from resource data for URL
 *   // Can encode multiple values (e.g., "service:taskId")
 *   getId: (data) => string | null,
 *
 *   // Required: Find resource in infrastructure data by ID
 *   // Return null if resource is fetched separately (like tasks)
 *   findInInfra: (id, infraData) => object | null,
 *
 *   // Required: Get all resources of this type (for URLs without specific ID)
 *   findAll: (infraData) => object | array | null,
 *
 *   // Optional: Parse composite ID back to data object
 *   // Default: returns { id: rawId }
 *   // Use this when getId encodes multiple values
 *   parseId: (id) => object,
 * }
 * ```
 *
 * ## Creating a New Handler
 *
 * 1. Create a file in `src/handlers/` (e.g., `myresource.js`)
 * 2. Import and call `registerResourceHandler`:
 *
 * ```javascript
 * // src/handlers/myresource.js
 * import { registerResourceHandler } from '../utils/infraResourceHandlers'
 *
 * registerResourceHandler('myresource', {
 *   getId: (data) => data?.id,
 *   findInInfra: (id, infraData) => infraData?.myResources?.find(r => r.id === id),
 *   findAll: (infraData) => infraData?.myResources,
 * })
 * ```
 *
 * 3. Add the import to `src/handlers/index.js`:
 *
 * ```javascript
 * import './myresource'
 * ```
 *
 * ## Composite IDs (for resources needing metadata)
 *
 * Some resources need more than just an ID (e.g., ECS tasks need service name).
 * Use composite IDs:
 *
 * ```javascript
 * registerResourceHandler('task', {
 *   // Encode: "backend:abc123"
 *   getId: (data) => `${data.service}:${data.taskId}`,
 *
 *   // Decode back to object
 *   parseId: (id) => {
 *     const [service, taskId] = id.split(':')
 *     return { service, taskId, id: taskId }
 *   },
 *
 *   findInInfra: () => null, // Fetched via API
 *   findAll: () => null,
 * })
 * ```
 */

// ============================================================
// Handler Registry (populated by handler imports)
// ============================================================

export const resourceHandlers = {}

// ============================================================
// Public API Functions
// ============================================================

/**
 * Register a resource handler.
 * Called by handler modules to self-register.
 *
 * @param {string} type - Resource type name (e.g., 'task', 'subnet')
 * @param {object} handler - Handler object with getId, findInInfra, findAll, and optionally parseId
 */
export function registerResourceHandler(type, handler) {
  if (resourceHandlers[type]) {
    console.warn(`[infraResourceHandlers] Handler for '${type}' is being overwritten`)
  }
  resourceHandlers[type] = handler
}

/**
 * Get the resource ID from data using the appropriate handler.
 * The ID may be composite (encoding metadata) for certain resource types.
 *
 * @param {string} type - Resource type (e.g., 'task', 'subnet')
 * @param {object} data - Resource data object
 * @returns {string|null} - Resource ID for URL
 */
export function getResourceId(type, data) {
  const handler = resourceHandlers[type]
  if (!handler) {
    console.warn(`[infraResourceHandlers] No handler registered for type '${type}'`)
    return data?.id || null
  }
  return handler.getId(data)
}

/**
 * Parse a resource ID back to a data object.
 * For composite IDs, this extracts the encoded metadata.
 *
 * @param {string} type - Resource type (e.g., 'task', 'subnet')
 * @param {string} id - Resource ID from URL
 * @returns {object} - Parsed data object (at minimum { id })
 */
export function parseResourceId(type, id) {
  if (!id) return null
  const handler = resourceHandlers[type]
  // Use handler's parseId if available, otherwise default to { id }
  if (handler?.parseId) {
    return handler.parseId(id)
  }
  return { id }
}

/**
 * Find a resource in infrastructure data by type and ID.
 *
 * @param {string} type - Resource type
 * @param {string} id - Resource ID
 * @param {object} infraData - Infrastructure data for the environment
 * @returns {object|null} - Found resource or null
 */
export function findResource(type, id, infraData) {
  const handler = resourceHandlers[type]
  if (!handler) return null
  return handler.findInInfra(id, infraData)
}

/**
 * Get all resources of a type from infrastructure data.
 *
 * @param {string} type - Resource type
 * @param {object} infraData - Infrastructure data for the environment
 * @returns {object|array|null} - All resources of this type
 */
export function findAllResources(type, infraData) {
  const handler = resourceHandlers[type]
  if (!handler) return null
  return handler.findAll(infraData)
}

/**
 * Check if a handler is registered for a type.
 *
 * @param {string} type - Resource type
 * @returns {boolean} - True if handler exists
 */
export function hasHandler(type) {
  return !!resourceHandlers[type]
}

/**
 * Get list of all registered handler types.
 *
 * @returns {string[]} - Array of registered type names
 */
export function getRegisteredTypes() {
  return Object.keys(resourceHandlers)
}

export default resourceHandlers
