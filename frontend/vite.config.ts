import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const pdfRoot = dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'));
const pdfAssets = ['cmaps', 'standard_fonts', 'wasm', 'iccs'].flatMap(directory =>
  readdirSync(join(pdfRoot, directory)).map(name => ({
    fileName: `pdfjs-assets/${directory}/${name}`, source: readFileSync(join(pdfRoot, directory, name)),
  })));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  return {
    plugins: [react(), {
      name: 'local-pdf-assets',
      generateBundle() { for (const asset of pdfAssets) this.emitFile({ type: 'asset', ...asset }); },
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const asset = pdfAssets.find(item => `/${item.fileName}` === request.url?.split('?')[0]);
          if (!asset) return next();
          response.setHeader('Content-Type', asset.fileName.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream');
          response.end(asset.source);
        });
      },
    }],
    server: {
      proxy: { '/api': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
    },
    build: { sourcemap: false },
  };
});
