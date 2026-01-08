/**
 * Common data types for Dashborion
 *
 * These types represent the data structures used across
 * frontend and backend for services, tasks, events, etc.
 */

/**
 * Service status
 */
export type ServiceStatus = 'running' | 'stopped' | 'pending' | 'failed' | 'unknown';

/**
 * Health status
 */
export type HealthStatus = 'healthy' | 'unhealthy' | 'unknown';

/**
 * Service summary
 */
export interface Service {
  id: string;
  name: string;
  status: ServiceStatus;
  desiredCount?: number;
  runningCount?: number;
  pendingCount?: number;
  lastDeployment?: Date;
  healthStatus?: HealthStatus;
}

/**
 * Service details (extended)
 */
export interface ServiceDetails extends Service {
  clusterName?: string;
  taskDefinition?: TaskDefinition;
  tasks?: Task[];
  deployments?: Deployment[];
  events?: ServiceEvent[];
  metrics?: ServiceMetrics;
  consoleUrl?: string;
  accountId?: string;
}

/**
 * Task definition
 */
export interface TaskDefinition {
  arn?: string;
  family?: string;
  revision?: number;
  image?: string;
  cpu?: string;
  memory?: string;
}

/**
 * Task instance
 */
export interface Task {
  id: string;
  status: string;
  desiredStatus?: string;
  health?: HealthStatus;
  revision?: number;
  isLatest?: boolean;
  az?: string;
  subnetId?: string;
  cpu?: string;
  memory?: string;
  startedAt?: Date;
  stoppedAt?: Date;
  containers?: Container[];
}

/**
 * Container
 */
export interface Container {
  name: string;
  image: string;
  status: string;
  healthStatus?: string;
  lastStatus?: string;
}

/**
 * Deployment
 */
export interface Deployment {
  status: string;
  taskDefinition?: string;
  revision?: number;
  desiredCount?: number;
  runningCount?: number;
  pendingCount?: number;
  rolloutState?: string;
  createdAt?: Date;
  updatedAt?: Date;
}

/**
 * Service event
 */
export interface ServiceEvent {
  id: string;
  timestamp: Date;
  message: string;
  type?: 'info' | 'warning' | 'error';
}

/**
 * Service metrics
 */
export interface ServiceMetrics {
  cpuUtilization?: number;
  memoryUtilization?: number;
  requestCount?: number;
  errorRate?: number;
}

/**
 * Pipeline status
 */
export type PipelineStatus = 'Succeeded' | 'Failed' | 'InProgress' | 'Stopped' | 'Unknown';

/**
 * Pipeline execution
 */
export interface PipelineExecution {
  executionId: string;
  status: PipelineStatus;
  startedAt?: Date;
  finishedAt?: Date;
  durationSeconds?: number;
  commitSha?: string;
  commitMessage?: string;
  commitAuthor?: string;
  commitUrl?: string;
  consoleUrl?: string;
  triggerType?: string;
}

/**
 * Pipeline stage
 */
export interface PipelineStage {
  name: string;
  status: string;
}

/**
 * Pipeline
 */
export interface Pipeline {
  name: string;
  pipelineType: 'build' | 'deploy';
  service?: string;
  environment?: string;
  version?: number;
  stages?: PipelineStage[];
  lastExecution?: PipelineExecution;
  executions?: PipelineExecution[];
  buildLogs?: string[];
  consoleUrl?: string;
}

/**
 * Container image
 */
export interface ContainerImage {
  digest: string;
  tags: string[];
  pushedAt?: Date;
  sizeBytes?: number;
  sizeMb?: number;
}

/**
 * Infrastructure resource types
 */
export type InfraResourceType = 'alb' | 'targetGroup' | 'rds' | 'elasticache' | 'cloudfront' | 'vpc' | 'subnet';

/**
 * Infrastructure resource
 */
export interface InfraResource {
  type: InfraResourceType;
  id: string;
  name: string;
  status?: string;
  details?: Record<string, unknown>;
}

/**
 * Event types for timeline
 */
export type TimelineEventType = 'deployment' | 'build' | 'scale' | 'restart' | 'error' | 'manual';

/**
 * Timeline event
 */
export interface TimelineEvent {
  id: string;
  type: TimelineEventType;
  timestamp: Date;
  service?: string;
  environment?: string;
  message: string;
  user?: string;
  details?: Record<string, unknown>;
}
