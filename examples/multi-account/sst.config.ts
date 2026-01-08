/// <reference path="../../.sst/platform/config.d.ts" />

/**
 * Multi-Account Dashborion Example (Homebox-style)
 *
 * This example shows how to deploy Dashborion for enterprise
 * multi-account setups with SAML SSO and cross-account monitoring.
 */

import { Dashborion } from '@dashborion/sst';
import { ecsPlugin } from '@dashborion/plugin-aws-ecs';

export default $config({
  app(input) {
    return {
      name: 'dashborion-homebox',
      home: 'aws',
      removal: input?.stage === 'production' ? 'retain' : 'remove',
    };
  },

  async run() {
    const stage = $app.stage;

    // Configuration varies by stage
    const stageConfig = {
      staging: {
        domain: 'dashboard.staging.homebox.kamorion.cloud',
      },
      production: {
        domain: 'dashboard.homebox.kamorion.cloud',
      },
    }[stage] ?? {
      domain: `dashboard-${stage}.homebox.kamorion.cloud`,
    };

    const dashboard = new Dashborion('Homebox', {
      domain: stageConfig.domain,

      auth: {
        provider: 'saml',
        saml: {
          entityId: 'homebox-dashboard-sso',
          idpMetadataFile: './idp-metadata/dashboard.xml',
        },
        sessionTtlSeconds: 3600 * 8,
        cookieDomain: '.homebox.kamorion.cloud',
      },

      plugins: [
        ecsPlugin({
          projects: {
            homebox: {
              displayName: 'Homebox',
              description: 'Homebox application services',
              environments: {
                staging: {
                  accountId: '702125625526',
                  region: 'eu-west-3',
                  clusterName: 'homebox-staging',
                  displayName: 'Staging',
                },
                preprod: {
                  accountId: '123456789012', // Replace with actual
                  region: 'eu-west-3',
                  clusterName: 'homebox-preprod',
                  displayName: 'Preprod',
                },
                production: {
                  accountId: '987654321098', // Replace with actual
                  region: 'eu-west-3',
                  clusterName: 'homebox-production',
                  displayName: 'Production',
                },
              },
            },
          },
          crossAccountRoles: {
            '702125625526': {
              readRoleArn: 'arn:aws:iam::702125625526:role/dashborion-read',
              actionRoleArn: 'arn:aws:iam::702125625526:role/dashborion-action',
            },
            '123456789012': {
              readRoleArn: 'arn:aws:iam::123456789012:role/dashborion-read',
            },
            '987654321098': {
              readRoleArn: 'arn:aws:iam::987654321098:role/dashborion-read',
            },
          },
          defaultRegion: 'eu-west-3',
          actionsEnabled: stage !== 'production', // Actions disabled in prod
          cacheTtlSeconds: 30,
        }),
      ],

      // Deployment mode
      mode: 'standalone',

      // AWS configuration
      aws: {
        region: 'eu-west-3',
        profile: 'homebox-shared-services/AdministratorAccess',
      },

      // Backend configuration
      backend: {
        codePath: '../../backend',
        memorySize: 512,
        timeout: 30,
        environment: {
          LOG_LEVEL: stage === 'production' ? 'INFO' : 'DEBUG',
        },
      },
    });

    return {
      url: dashboard.url,
      apiUrl: dashboard.apiUrl,
      cloudfrontId: dashboard.cloudfrontId,
      s3Bucket: dashboard.s3Bucket,
    };
  },
});
