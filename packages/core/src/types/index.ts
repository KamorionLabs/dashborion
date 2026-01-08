/**
 * Shared types for Dashborion
 */

// Re-export data types from interfaces
export type {
  Service,
  ServiceDetails,
  ServiceStatus,
  HealthStatus,
  Task,
  TaskDefinition,
  Container,
  Deployment,
  ServiceEvent,
  ServiceMetrics,
  Pipeline,
  PipelineExecution,
  PipelineStage,
  PipelineStatus,
  ContainerImage,
  InfraResource,
  InfraResourceType,
  TimelineEvent,
  TimelineEventType,
} from '../interfaces/plugin.js';

// Re-export configuration types
export type {
  ProjectConfig,
  EnvironmentConfig,
  CrossAccountRole,
} from '../config/types.js';

/**
 * API response types
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ApiError;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

/**
 * Pagination types
 */
export interface PaginationParams {
  page?: number;
  limit?: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  hasMore: boolean;
}

/**
 * User types
 */
export interface User {
  id: string;
  email: string;
  name?: string;
  groups?: string[];
  roles?: string[];
}

/**
 * Session types
 */
export interface Session {
  user: User;
  expiresAt: Date;
  createdAt: Date;
}

/**
 * AWS-specific types (used by plugins)
 */
export interface AwsCredentials {
  accessKeyId?: string;
  secretAccessKey?: string;
  sessionToken?: string;
  region: string;
}
