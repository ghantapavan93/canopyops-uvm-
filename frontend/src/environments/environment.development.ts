/** Dev environment (ng serve). Points straight at the local FastAPI container. */
export const environment = {
  production: false,
  // Same relative base as prod; the dev server proxies /api → :8000
  // (proxy.conf.json), mirroring the nginx proxy in the Docker image.
  apiBase: '/api',
};
