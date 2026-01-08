/// <reference path="../../.sst/platform/config.d.ts" />

/**
 * Simple Dashborion Example
 *
 * This example shows how to deploy a basic Dashborion instance
 * with the ECS plugin for monitoring AWS ECS services.
 */

import { Dashborion } from '@dashborion/sst';
import { ecsPlugin } from '@dashborion/plugin-aws-ecs';

export default $config({
  app(input) {
    return {
      name: 'dashborion-example',
      home: 'aws',
      removal: input?.stage === 'production' ? 'retain' : 'remove',
    };
  },

  async run() {
    // Create the Dashborion dashboard
    const dashboard = new Dashborion('Dashboard', {
      // Domain for the dashboard
      domain: 'dashboard.example.com',

      // Authentication configuration
      auth: {
        provider: 'saml',
        saml: {
          entityId: 'dashborion-example',
          idpMetadataFile: './idp-metadata.xml',
        },
        sessionTtlSeconds: 3600 * 8, // 8 hours
      },

      // Plugins configuration
      plugins: [
        ecsPlugin({
          projects: {
            myapp: {
              displayName: 'My Application',
              environments: {
                staging: {
                  accountId: '111111111111',
                  region: 'eu-west-1',
                  clusterName: 'myapp-staging',
                },
                production: {
                  accountId: '222222222222',
                  region: 'eu-west-1',
                  clusterName: 'myapp-production',
                },
              },
            },
          },
          crossAccountRoles: {
            '111111111111': {
              readRoleArn: 'arn:aws:iam::111111111111:role/dashborion-read',
            },
            '222222222222': {
              readRoleArn: 'arn:aws:iam::222222222222:role/dashborion-read',
            },
          },
          actionsEnabled: false, // Read-only mode
        }),
      ],

      // Backend configuration
      backend: {
        codePath: '../../backend',
        memorySize: 256,
        timeout: 30,
      },
    });

    // Return outputs
    return {
      url: dashboard.url,
      apiUrl: dashboard.apiUrl,
      cloudfrontId: dashboard.cloudfrontId,
    };
  },
});
