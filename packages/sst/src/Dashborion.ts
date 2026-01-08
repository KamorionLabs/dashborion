/**
 * Dashborion SST Component
 *
 * Main component for deploying a Dashborion infrastructure dashboard.
 *
 * @example
 * ```typescript
 * import { Dashborion } from '@dashborion/sst';
 *
 * const dashboard = new Dashborion('Dashboard', {
 *   domain: 'dashboard.example.com',
 *   auth: {
 *     provider: 'saml',
 *     saml: { entityId: 'my-dashboard-sso' },
 *   },
 *   idpMetadataPath: './idp-metadata.xml',
 *   config: {
 *     projects: {
 *       myapp: {
 *         displayName: 'My Application',
 *         environments: {
 *           staging: { accountId: '111111111111', region: 'eu-west-1', clusterName: 'myapp-staging' },
 *           production: { accountId: '222222222222', region: 'eu-west-1', clusterName: 'myapp-prod' },
 *         },
 *       },
 *     },
 *     crossAccountRoles: {
 *       '111111111111': { readRoleArn: 'arn:aws:iam::111111111111:role/dashborion-read' },
 *       '222222222222': { readRoleArn: 'arn:aws:iam::222222222222:role/dashborion-read' },
 *     },
 *     features: { ecs: true, pipelines: true, infrastructure: true },
 *   },
 * });
 * ```
 */

import * as pulumi from '@pulumi/pulumi';
import * as aws from '@pulumi/aws';
import * as fs from 'fs';
import type { DashborionConfig } from '@dashborion/core';
import type { DashborionArgs, DashborionOutputs } from './types.js';

export class Dashborion extends pulumi.ComponentResource {
  /** Dashboard URL */
  public readonly url: pulumi.Output<string>;

  /** CloudFront distribution ID */
  public readonly cloudfrontId: pulumi.Output<string>;

  /** API Gateway URL */
  public readonly apiUrl: pulumi.Output<string>;

  /** S3 bucket name */
  public readonly s3Bucket: pulumi.Output<string>;

  constructor(
    name: string,
    args: DashborionArgs,
    opts?: pulumi.ComponentResourceOptions
  ) {
    super('dashborion:index:Dashborion', name, {}, opts);

    const mode = args.mode ?? 'standalone';
    const region = args.aws?.region ?? args.config.region ?? 'eu-west-3';
    const enableAuth = args.auth?.provider !== 'none' && args.auth?.provider !== undefined;

    // Provider for us-east-1 (required for Lambda@Edge and CloudFront certificates)
    const usEast1Provider = new aws.Provider(`${name}-us-east-1`, {
      region: 'us-east-1',
      ...(args.aws?.profile ? { profile: args.aws.profile } : {}),
    }, { parent: this });

    // Generate configuration for backend
    const backendConfig = this.generateBackendConfig(args.config);

    // Create resources based on mode
    let frontendBucket: aws.s3.Bucket | undefined;
    let distribution: aws.cloudfront.Distribution | undefined;
    let apiGateway: aws.apigatewayv2.Api | undefined;
    let backendLambda: aws.lambda.Function | undefined;
    let authLambda: aws.lambda.Function | undefined;

    // Load IDP metadata if SAML auth is configured
    let idpMetadataXml = '';
    if (args.auth?.provider === 'saml' && args.idpMetadataPath) {
      try {
        idpMetadataXml = fs.readFileSync(args.idpMetadataPath, 'utf-8');
      } catch (e) {
        console.warn(`Failed to read IDP metadata from ${args.idpMetadataPath}`);
      }
    }

    if (mode === 'standalone' || mode === 'semi-managed') {
      // Create S3 bucket for frontend
      frontendBucket = new aws.s3.Bucket(
        `${name}-frontend`,
        {
          bucket: `dashborion-${name.toLowerCase()}-frontend`,
          tags: {
            Project: 'dashborion',
            Component: name,
          },
        },
        { parent: this }
      );

      // Create CloudFront OAC
      const oac = new aws.cloudfront.OriginAccessControl(
        `${name}-oac`,
        {
          name: `dashborion-${name.toLowerCase()}-oac`,
          originAccessControlOriginType: 's3',
          signingBehavior: 'always',
          signingProtocol: 'sigv4',
        },
        { parent: this }
      );

      // Create Lambda@Edge for authentication (if enabled)
      let lambdaAssociations: aws.types.input.cloudfront.DistributionDefaultCacheBehaviorLambdaFunctionAssociation[] = [];

      if (enableAuth && args.auth?.provider === 'saml') {
        // Create Lambda@Edge execution role
        const edgeRole = new aws.iam.Role(
          `${name}-edge-role`,
          {
            assumeRolePolicy: JSON.stringify({
              Version: '2012-10-17',
              Statement: [
                {
                  Action: 'sts:AssumeRole',
                  Effect: 'Allow',
                  Principal: {
                    Service: ['lambda.amazonaws.com', 'edgelambda.amazonaws.com'],
                  },
                },
              ],
            }),
            tags: {
              Project: 'dashborion',
              Component: name,
            },
          },
          { parent: this }
        );

        new aws.iam.RolePolicyAttachment(
          `${name}-edge-basic`,
          {
            role: edgeRole.name,
            policyArn: 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
          },
          { parent: this }
        );

        // Auth protect Lambda@Edge (viewer-request)
        authLambda = new aws.lambda.Function(
          `${name}-auth-protect`,
          {
            name: `dashborion-${name.toLowerCase()}-auth-protect`,
            runtime: aws.lambda.Runtime.NodeJS20dX,
            handler: 'index.handler',
            code: new pulumi.asset.FileArchive(args.authLambda?.codePath ?? './packages/auth/dist'),
            role: edgeRole.arn,
            memorySize: 128,
            timeout: 5,
            publish: true, // Required for Lambda@Edge
            environment: {
              variables: {
                COOKIE_NAME: args.authLambda?.cookieName ?? 'dashborion_session',
                COOKIE_DOMAIN: args.domain ?? '',
                SP_ENTITY_ID: args.auth?.saml?.entityId ?? 'dashborion',
                IDP_METADATA_XML: idpMetadataXml,
                SIGN_AUTHN_REQUESTS: 'false',
                EXCLUDED_PATHS: '/saml/acs,/saml/metadata.xml,/health,/api/',
              },
            },
            tags: {
              Project: 'dashborion',
              Component: name,
            },
          },
          { parent: this, provider: usEast1Provider }
        );

        lambdaAssociations = [
          {
            eventType: 'viewer-request',
            lambdaArn: authLambda.qualifiedArn,
            includeBody: false,
          },
        ];
      }

      // Certificate and aliases for custom domain
      let viewerCertificate: aws.types.input.cloudfront.DistributionViewerCertificate;
      let aliases: string[] | undefined;

      if (args.domain && args.external?.certificateArn) {
        viewerCertificate = {
          acmCertificateArn: args.external.certificateArn,
          sslSupportMethod: 'sni-only',
          minimumProtocolVersion: 'TLSv1.2_2021',
        };
        aliases = [args.domain];
      } else {
        viewerCertificate = {
          cloudfrontDefaultCertificate: true,
        };
      }

      // Create CloudFront distribution
      distribution = new aws.cloudfront.Distribution(
        `${name}-cdn`,
        {
          enabled: true,
          defaultRootObject: 'index.html',
          aliases,
          origins: [
            {
              domainName: frontendBucket.bucketRegionalDomainName,
              originId: 's3-origin',
              originAccessControlId: oac.id,
            },
          ],
          defaultCacheBehavior: {
            targetOriginId: 's3-origin',
            viewerProtocolPolicy: 'redirect-to-https',
            allowedMethods: ['GET', 'HEAD', 'OPTIONS'],
            cachedMethods: ['GET', 'HEAD'],
            forwardedValues: {
              queryString: false,
              cookies: { forward: enableAuth ? 'all' : 'none' },
            },
            lambdaFunctionAssociations: lambdaAssociations,
          },
          restrictions: {
            geoRestriction: {
              restrictionType: 'none',
            },
          },
          viewerCertificate,
          customErrorResponses: [
            {
              errorCode: 404,
              responseCode: 200,
              responsePagePath: '/index.html',
            },
            {
              errorCode: 403,
              responseCode: 200,
              responsePagePath: '/index.html',
            },
          ],
          tags: {
            Project: 'dashborion',
            Component: name,
          },
        },
        { parent: this }
      );

      // S3 bucket policy for CloudFront access
      new aws.s3.BucketPolicy(
        `${name}-bucket-policy`,
        {
          bucket: frontendBucket.id,
          policy: pulumi.all([frontendBucket.arn, distribution.arn]).apply(
            ([bucketArn, distributionArn]) =>
              JSON.stringify({
                Version: '2012-10-17',
                Statement: [
                  {
                    Sid: 'AllowCloudFrontAccess',
                    Effect: 'Allow',
                    Principal: {
                      Service: 'cloudfront.amazonaws.com',
                    },
                    Action: 's3:GetObject',
                    Resource: `${bucketArn}/*`,
                    Condition: {
                      StringEquals: {
                        'AWS:SourceArn': distributionArn,
                      },
                    },
                  },
                ],
              })
          ),
        },
        { parent: this }
      );
    }

    // Create backend Lambda
    const lambdaRole =
      args.external?.lambdaRoleArn ?
        pulumi.output(args.external.lambdaRoleArn)
      : this.createLambdaRole(name, args.config);

    backendLambda = new aws.lambda.Function(
      `${name}-backend`,
      {
        name: `dashborion-${name.toLowerCase()}-api`,
        runtime: aws.lambda.Runtime.Python3d12,
        handler: 'handler.handler',
        code: new pulumi.asset.FileArchive(args.backend?.codePath ?? './backend'),
        role: lambdaRole,
        memorySize: args.backend?.memorySize ?? 256,
        timeout: args.backend?.timeout ?? 30,
        architectures: ['arm64'],
        environment: {
          variables: {
            DASHBORION_CONFIG: JSON.stringify(backendConfig),
            CORS_ORIGINS: args.domain ? `https://${args.domain}` : '*',
            ...args.backend?.environment,
          },
        },
        tags: {
          Project: 'dashborion',
          Component: name,
        },
      },
      { parent: this }
    );

    // Create API Gateway
    apiGateway = new aws.apigatewayv2.Api(
      `${name}-api`,
      {
        name: `dashborion-${name.toLowerCase()}-api`,
        protocolType: 'HTTP',
        corsConfiguration: {
          allowOrigins: args.domain ? [`https://${args.domain}`] : ['*'],
          allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
          allowHeaders: ['Content-Type', 'Authorization'],
          maxAge: 300,
        },
        tags: {
          Project: 'dashborion',
          Component: name,
        },
      },
      { parent: this }
    );

    // Lambda integration
    const lambdaIntegration = new aws.apigatewayv2.Integration(
      `${name}-integration`,
      {
        apiId: apiGateway.id,
        integrationType: 'AWS_PROXY',
        integrationUri: backendLambda.invokeArn,
        payloadFormatVersion: '2.0',
      },
      { parent: this }
    );

    // Default route
    new aws.apigatewayv2.Route(
      `${name}-route`,
      {
        apiId: apiGateway.id,
        routeKey: '$default',
        target: pulumi.interpolate`integrations/${lambdaIntegration.id}`,
      },
      { parent: this }
    );

    // API Gateway stage
    new aws.apigatewayv2.Stage(
      `${name}-stage`,
      {
        apiId: apiGateway.id,
        name: '$default',
        autoDeploy: true,
      },
      { parent: this }
    );

    // Lambda permission for API Gateway
    new aws.lambda.Permission(
      `${name}-api-permission`,
      {
        action: 'lambda:InvokeFunction',
        function: backendLambda.name,
        principal: 'apigateway.amazonaws.com',
        sourceArn: pulumi.interpolate`${apiGateway.executionArn}/*/*`,
      },
      { parent: this }
    );

    // Set outputs
    this.url = distribution?.domainName
      ? pulumi.interpolate`https://${distribution.domainName}`
      : pulumi.output('http://localhost:3000');

    this.cloudfrontId = distribution?.id ?? pulumi.output('');
    this.apiUrl = pulumi.interpolate`${apiGateway.apiEndpoint}`;
    this.s3Bucket = frontendBucket?.bucket ?? pulumi.output('');

    // Register outputs
    this.registerOutputs({
      url: this.url,
      cloudfrontId: this.cloudfrontId,
      apiUrl: this.apiUrl,
      s3Bucket: this.s3Bucket,
    });
  }

  /**
   * Generate configuration for the backend Lambda
   */
  private generateBackendConfig(config: DashborionConfig): object {
    // The backend expects the full config as JSON
    return config;
  }

  /**
   * Create Lambda execution role with cross-account permissions
   */
  private createLambdaRole(
    name: string,
    config: DashborionConfig
  ): pulumi.Output<string> {
    // Extract cross-account role ARNs
    const crossAccountRoles: string[] = [];

    if (config.crossAccountRoles) {
      for (const role of Object.values(config.crossAccountRoles)) {
        crossAccountRoles.push(role.readRoleArn);
        if (role.actionRoleArn) {
          crossAccountRoles.push(role.actionRoleArn);
        }
      }
    }

    const role = new aws.iam.Role(
      `${name}-lambda-role`,
      {
        assumeRolePolicy: JSON.stringify({
          Version: '2012-10-17',
          Statement: [
            {
              Action: 'sts:AssumeRole',
              Effect: 'Allow',
              Principal: {
                Service: 'lambda.amazonaws.com',
              },
            },
          ],
        }),
        tags: {
          Project: 'dashborion',
          Component: name,
        },
      },
      { parent: this }
    );

    // Basic Lambda execution policy
    new aws.iam.RolePolicyAttachment(
      `${name}-lambda-basic`,
      {
        role: role.name,
        policyArn: 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
      },
      { parent: this }
    );

    // Cross-account assume role policy
    if (crossAccountRoles.length > 0) {
      new aws.iam.RolePolicy(
        `${name}-cross-account`,
        {
          role: role.name,
          policy: JSON.stringify({
            Version: '2012-10-17',
            Statement: [
              {
                Effect: 'Allow',
                Action: 'sts:AssumeRole',
                Resource: crossAccountRoles,
              },
            ],
          }),
        },
        { parent: this }
      );
    }

    return role.arn;
  }
}
