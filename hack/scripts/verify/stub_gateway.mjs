/**
 * Local stub of the Sentinel media gateway — used ONLY to verify that the vite
 * dev proxy still injects the gateway credentials after the credential scrub.
 *
 * It never echoes a credential: the received Authorization header is reduced to
 * a SHA-256 digest (plus "is it Basic?" and its length) so the verifier can
 * compare digests without any secret appearing in a response body, a log line or
 * the terminal.
 */
import http from 'node:http';
import crypto from 'node:crypto';

const PORT = Number(process.env.STUB_PORT || 8899);

const server = http.createServer((req, res) => {
  const auth = req.headers['authorization'] || '';
  const digest = auth ? crypto.createHash('sha256').update(auth).digest('hex') : '';
  const headers = {
    'x-stub-path': req.url || '',
    'x-stub-has-authorization': auth.startsWith('Basic ') ? 'true' : 'false',
    'x-stub-auth-sha256': digest,
    'x-stub-auth-length': String(auth.length),
  };

  if ((req.url || '').startsWith('/live/')) {
    res.writeHead(200, { ...headers, 'content-type': 'application/vnd.apple.mpegurl' });
    res.end('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:2\n#STUB\n');
    return;
  }

  res.writeHead(201, {
    ...headers,
    'content-type': 'application/json',
    location: `${req.url}-session`,
  });
  res.end(JSON.stringify({ stub: true, path: req.url, authDigest: digest }));
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[stub-gateway] listening on 127.0.0.1:${PORT}`);
});
