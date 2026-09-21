/** Public backend URLs only — never construct a camera URL containing credentials. */
export function apiUrl(path: string, base = '/api'): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

/**
 * FastAPI tickets return backend-root-relative paths (/api/... or /sentinel/...).
 * On a Vercel + Render split these belong to Render, not window.location.origin.
 * Keep local/same-origin deployments working without hardcoding any hostname.
 */
export function backendRootUrl(path: string, apiBase = '/api'): string {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) {
    try {
      const url = new URL(path);
      return url.username || url.password ? '' : path;
    } catch { return ''; }
  }
  if (path.startsWith('//') || /^[a-z][a-z0-9+.-]*:/i.test(path)) return '';
  if (!/^https?:\/\//i.test(apiBase)) return path;
  const base = new URL(apiBase);
  const mount = /\/api(?:\/v\d+)?\/?$/.test(base.pathname)
    ? base.pathname.replace(/\/api(?:\/v\d+)?\/?$/, '') : '';
  return new URL(`${mount}/${path.replace(/^\/+/, '')}`, base.origin).toString();
}

/** Retain a remote /sentinel proxy's origin, prefix and port for HLS fallback. */
export function sentinelHlsUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = /\/stream\/([^/?#]+)\/whep(?:[/?#]|$)/.exec(url);
  if (!match) return null;
  const hlsPath = `/live/stream/${match[1]}/index.m3u8`;
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      const proxy = /^(.*\/sentinel)\/stream\//.exec(parsed.pathname);
      return proxy ? `${parsed.origin}${proxy[1]}${hlsPath}` : `${parsed.protocol}//${parsed.hostname}${hlsPath}`;
    } catch { return null; }
  }
  const proxy = /^(.*\/sentinel)\/stream\//.exec(url);
  return proxy ? `${proxy[1]}${hlsPath}` : hlsPath;
}
