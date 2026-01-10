/**
 * Tags helper for Dashborion
 * Merges custom tags with default tags for all resources
 */

import { InfraConfig } from "./config";

export interface TagsHelper {
  /** Get all tags (default + custom) */
  all: () => Record<string, string>;
  /** Get tags with additional overrides */
  with: (overrides: Record<string, string>) => Record<string, string>;
  /** Get tags for a specific component */
  component: (component: string) => Record<string, string>;
}

/**
 * Create tags helper from config
 */
export function createTags(config: InfraConfig, stage: string): TagsHelper {
  const customTags = config.tags || {};
  const app = config.naming?.app || "dashborion";

  const defaultTags: Record<string, string> = {
    Project: app,
    Stage: stage,
  };

  return {
    all: (): Record<string, string> => ({
      ...defaultTags,
      ...customTags,
    }),

    with: (overrides: Record<string, string>): Record<string, string> => ({
      ...defaultTags,
      ...customTags,
      ...overrides,
    }),

    component: (component: string): Record<string, string> => ({
      ...defaultTags,
      ...customTags,
      Component: component,
    }),
  };
}
