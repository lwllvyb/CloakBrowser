/**
 * Shared proxy URL parsing for Playwright and Puppeteer wrappers.
 */

export interface ParsedProxy {
  server: string;
  username?: string;
  password?: string;
}

/**
 * Prepend http:// to schemeless proxy URLs so parsers can extract hostname.
 * Used by geoip resolution which only needs a valid hostname, not auth fields.
 */
export function ensureProxyScheme(proxyUrl: string): string {
  return proxyUrl.includes("://") ? proxyUrl : `http://${proxyUrl}`;
}

/**
 * Parse a proxy URL, extracting credentials into separate fields.
 *
 * Handles: "http://user:pass@host:port" -> { server: "http://host:port", username: "user", password: "pass" }
 * Also handles: no credentials, URL-encoded special chars, socks5://, missing port,
 * and bare proxy strings without a scheme (e.g. "user:pass@host:port" -> treated as http).
 */
/** Proxy dict shape accepted by Playwright/Puppeteer wrappers. */
export type ProxyDict = { server: string; bypass?: string; username?: string; password?: string };

/** Result of resolveProxyConfig — either Playwright dict OR Chrome arg, never both. */
export interface ProxyConfig {
  /** Playwright proxy option (for HTTP proxies). */
  proxyOption?: ParsedProxy;
  /** Chrome CLI args (for SOCKS5 proxies, e.g. ["--proxy-server=socks5://..."]). */
  proxyArgs: string[];
}

/**
 * Check if a proxy uses the SOCKS5 protocol.
 */
export function isSocksProxy(proxy: string | ProxyDict | undefined | null): boolean {
  if (!proxy) return false;
  const url = typeof proxy === "string" ? proxy : proxy.server;
  return /^socks5h?:\/\//i.test(url);
}

/**
 * Reconstruct a SOCKS5 URL with inline credentials from a proxy dict.
 */
export function reconstructSocksUrl(proxy: ProxyDict): string {
  const url = new URL(proxy.server);
  if (proxy.username) {
    url.username = encodeURIComponent(proxy.username);
    if (proxy.password) url.password = encodeURIComponent(proxy.password);
  }
  return url.href.replace(/\/$/, "");
}

/**
 * Resolve proxy into Playwright option and/or Chrome args.
 *
 * Playwright rejects SOCKS5 proxies with credentials in its proxy dict,
 * so SOCKS5 is passed via --proxy-server Chrome arg instead.
 */
export function resolveProxyConfig(proxy: string | ProxyDict | undefined): ProxyConfig {
  if (!proxy) return { proxyArgs: [] };

  if (isSocksProxy(proxy)) {
    // SOCKS5: bypass Playwright, pass directly to Chrome via --proxy-server.
    if (typeof proxy === "string") {
      return { proxyArgs: [`--proxy-server=${proxy}`] };
    }
    const socksUrl = reconstructSocksUrl(proxy);
    const args = [`--proxy-server=${socksUrl}`];
    if (proxy.bypass) args.push(`--proxy-bypass-list=${proxy.bypass}`);
    return { proxyArgs: args };
  }

  // HTTP/HTTPS: use Playwright's proxy dict
  if (typeof proxy === "string") {
    return { proxyOption: parseProxyUrl(proxy), proxyArgs: [] };
  }
  return { proxyOption: proxy as ParsedProxy, proxyArgs: [] };
}

export function parseProxyUrl(proxy: string): ParsedProxy {
  let url: URL;
  // Bare format: "user:pass@host:port" — new URL() throws without a scheme.
  const normalized =
    proxy.includes("@") && !proxy.includes("://") ? `http://${proxy}` : proxy;
  try {
    url = new URL(normalized);
  } catch {
    // Not a parseable URL (e.g. bare "host:port") — pass through as-is
    return { server: proxy };
  }

  if (!url.username) {
    return { server: proxy };
  }

  // Rebuild server URL without credentials
  const server = `${url.protocol}//${url.hostname}${url.port ? `:${url.port}` : ""}`;

  const result: ParsedProxy = {
    server,
    username: decodeURIComponent(url.username),
  };
  if (url.password) {
    result.password = decodeURIComponent(url.password);
  }

  return result;
}
