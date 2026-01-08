/**
 * ECS Resource Handlers (Tasks)
 *
 * Tasks use composite IDs to encode both service name and task ID:
 * URL: ?resource=task&id=backend:abc123
 *                       ^^^^^^^ ^^^^^^^
 *                       service taskId
 */
import { registerResourceHandler } from '../utils/infraResourceHandlers'

registerResourceHandler('task', {
  // Encode service and fullId in a composite ID: "backend:ea5b1d2b-1234-5678-9abc-def012345678"
  // IMPORTANT: Use fullId (36 chars) not taskId (8 chars) - AWS API requires full task ID
  getId: (data) => {
    const service = data?.service || data?.serviceName
    // Prioritize fullId over taskId since AWS API needs the complete 32-36 char ID
    const taskId = data?.fullId || data?.taskId || data?.id
    // Only create composite ID if we have both parts
    return service && taskId ? `${service}:${taskId}` : taskId
  },

  // Parse composite ID back to data object
  parseId: (id) => {
    if (id?.includes(':')) {
      const colonIndex = id.indexOf(':')
      const service = id.substring(0, colonIndex)
      const taskId = id.substring(colonIndex + 1)
      // Return both fullId and taskId for compatibility with TaskDetails.jsx
      return { service, fullId: taskId, taskId, id: taskId }
    }
    // Fallback: just an ID without service
    return { id }
  },

  // Tasks are fetched via API, not from infrastructure data
  findInInfra: () => null,
  findAll: () => null,
})
