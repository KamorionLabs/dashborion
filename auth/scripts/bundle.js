/**
 * Bundle Lambda@Edge handlers using esbuild
 *
 * Creates separate directories for each handler with index.js
 * for Lambda@Edge deployment via SST/Pulumi FileArchive.
 *
 * Configuration is injected at build time since Lambda@Edge
 * does not support environment variables.
 */

const esbuild = require('esbuild');
const path = require('path');
const fs = require('fs');

const handlers = ['protect', 'acs', 'metadata'];
const distDir = path.join(__dirname, '..', 'dist');

// Load configuration from DASHBORION_CONFIG_DIR
function loadConfig() {
  const configDir = process.env.DASHBORION_CONFIG_DIR;
  if (!configDir) {
    console.warn('Warning: DASHBORION_CONFIG_DIR not set, using default config');
    return {
      auth: {
        cookieDomain: '.homebox.kamorion.cloud',
        sessionTtlSeconds: 3600,
        excludedPaths: ['/health', '/api/health', '/saml/metadata', '/api/auth/device/code', '/api/auth/device/token'],
        saml: {
          entityId: 'dashborion',
          acsPath: '/saml/acs',
          metadataPath: '/saml/metadata',
        },
      },
      frontend: {
        cloudfrontDomain: 'dashboard.homebox.kamorion.cloud',
      },
    };
  }

  const configPath = path.join(configDir, 'infra.config.json');
  if (!fs.existsSync(configPath)) {
    throw new Error(`Config file not found: ${configPath}`);
  }

  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  console.log(`Loaded config from: ${configPath}`);

  // Load IdP metadata XML if specified
  if (config.auth?.saml?.idpMetadataFile) {
    const metadataPath = path.join(configDir, config.auth.saml.idpMetadataFile);
    if (fs.existsSync(metadataPath)) {
      config.auth.saml.idpMetadataXml = fs.readFileSync(metadataPath, 'utf8');
      console.log(`Loaded IdP metadata from: ${metadataPath}`);
    } else {
      console.warn(`Warning: IdP metadata file not found: ${metadataPath}`);
    }
  }

  return config;
}

// Clean and recreate dist directory
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true });
}

async function bundle() {
  console.log('Bundling Lambda@Edge handlers for SST deployment...\n');

  const config = loadConfig();
  const authConfig = config.auth || {};
  const samlConfig = authConfig.saml || {};
  const cloudfrontDomain = config.frontend?.cloudfrontDomain || '';

  // Build time config injection
  // Lambda@Edge does not support environment variables, so we inject at build time
  const define = {
    'process.env.NODE_ENV': '"production"',
    'process.env.COOKIE_NAME': JSON.stringify('dashborion_session'),
    'process.env.COOKIE_DOMAIN': JSON.stringify(authConfig.cookieDomain || ''),
    'process.env.IDP_METADATA_XML': JSON.stringify(samlConfig.idpMetadataXml || ''),
    'process.env.SP_ENTITY_ID': JSON.stringify(samlConfig.entityId || 'dashborion'),
    'process.env.SIGN_AUTHN_REQUESTS': JSON.stringify('false'),
    'process.env.EXCLUDED_PATHS': JSON.stringify(
      (authConfig.excludedPaths || []).join(',') || '/saml/acs,/saml/metadata.xml,/health'
    ),
    'process.env.SESSION_TTL_SECONDS': JSON.stringify(String(authConfig.sessionTtlSeconds || 3600)),
    'process.env.SESSION_ENCRYPTION_KEY': JSON.stringify(authConfig.sessionEncryptionKey || ''),
    'process.env.CLOUDFRONT_DOMAIN': JSON.stringify(cloudfrontDomain),
    'process.env.ACS_PATH': JSON.stringify(samlConfig.acsPath || '/saml/acs'),
    'process.env.METADATA_PATH': JSON.stringify(samlConfig.metadataPath || '/saml/metadata'),
  };

  console.log('Build-time configuration:');
  console.log(`  COOKIE_DOMAIN: ${authConfig.cookieDomain}`);
  console.log(`  SP_ENTITY_ID: ${samlConfig.entityId}`);
  console.log(`  CLOUDFRONT_DOMAIN: ${cloudfrontDomain}`);
  console.log(`  EXCLUDED_PATHS: ${(authConfig.excludedPaths || []).join(',')}`);
  console.log(`  IDP_METADATA: ${samlConfig.idpMetadataXml ? 'loaded (' + samlConfig.idpMetadataXml.length + ' chars)' : 'not loaded'}`);
  console.log(`  SESSION_ENCRYPTION_KEY: ${authConfig.sessionEncryptionKey ? 'configured (32 bytes)' : 'NOT CONFIGURED'}`);
  console.log('');

  for (const handler of handlers) {
    const handlerDir = path.join(distDir, handler);
    fs.mkdirSync(handlerDir, { recursive: true });

    console.log(`Bundling ${handler} handler...`);

    await esbuild.build({
      entryPoints: [path.join(__dirname, '..', 'src', 'handlers', `${handler}.ts`)],
      bundle: true,
      platform: 'node',
      target: 'node20',
      // Output as index.js for Lambda handler: index.handler
      outfile: path.join(handlerDir, 'index.js'),
      minify: true,
      sourcemap: false, // Lambda@Edge doesn't support source maps well
      external: [], // Bundle all dependencies
      treeShaking: true,
      define,
      // Lambda@Edge limits: 1MB for viewer-request, 50MB for origin-request
      logLevel: 'info',
    });

    // Get bundle size
    const stats = fs.statSync(path.join(handlerDir, 'index.js'));
    const sizeKB = (stats.size / 1024).toFixed(2);
    console.log(`  -> dist/${handler}/index.js (${sizeKB} KB)`);

    // Lambda@Edge viewer-request limit is 1MB
    if (handler !== 'acs' && stats.size > 1024 * 1024) {
      console.warn(`  Warning: ${handler} exceeds 1MB viewer-request limit!`);
    }
  }

  console.log('\nAll handlers bundled successfully!');
  console.log('\nDirectory structure:');
  console.log('  auth/dist/');
  for (const handler of handlers) {
    console.log(`    - ${handler}/index.js`);
  }
}

bundle().catch((err) => {
  console.error('Bundle failed:', err);
  process.exit(1);
});
