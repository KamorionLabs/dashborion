/**
 * Bundle Lambda@Edge handlers using esbuild
 *
 * Creates separate directories for each handler with index.js
 * for Lambda@Edge deployment via SST/Pulumi FileArchive.
 */

const esbuild = require('esbuild');
const path = require('path');
const fs = require('fs');

const handlers = ['protect', 'acs', 'metadata'];
const distDir = path.join(__dirname, '..', 'dist');

// Clean and recreate dist directory
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true });
}

async function bundle() {
  console.log('Bundling Lambda@Edge handlers for SST deployment...\n');

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
      define: {
        'process.env.NODE_ENV': '"production"',
      },
      // Lambda@Edge limits: 1MB for viewer-request, 50MB for origin-request
      logLevel: 'info',
    });

    // Get bundle size
    const stats = fs.statSync(path.join(handlerDir, 'index.js'));
    const sizeKB = (stats.size / 1024).toFixed(2);
    console.log(`  -> dist/${handler}/index.js (${sizeKB} KB)`);

    // Lambda@Edge viewer-request limit is 1MB
    if (handler !== 'acs' && stats.size > 1024 * 1024) {
      console.warn(`  ⚠️  Warning: ${handler} exceeds 1MB viewer-request limit!`);
    }
  }

  console.log('\n✓ All handlers bundled successfully!');
  console.log('\nDirectory structure:');
  console.log('  auth/dist/');
  for (const handler of handlers) {
    console.log(`    └── ${handler}/index.js`);
  }
}

bundle().catch((err) => {
  console.error('Bundle failed:', err);
  process.exit(1);
});
