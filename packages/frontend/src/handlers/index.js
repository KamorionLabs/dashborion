/**
 * Infrastructure Resource Handlers
 *
 * This file imports all handlers to trigger their self-registration.
 * Import this file once at app startup (e.g., in main.jsx or App.jsx).
 *
 * To add a new handler:
 * 1. Create a new file in this directory (e.g., myresource.js)
 * 2. Add the import below
 *
 * See infraResourceHandlers.js for documentation on creating handlers.
 */

// CDN
import './cdn'

// Load Balancer
import './loadbalancer'

// Database (RDS, ElastiCache)
import './database'

// Storage (S3)
import './storage'

// Network (VPC, Subnets, Route Tables, Endpoints, etc.)
import './network'

// ECS (Tasks with composite IDs)
import './ecs'
