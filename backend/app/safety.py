"""Public-only fetcher. Connect to the validated IP, keeping TLS SNI/Host original.

DNS pre-checks alone are insufficient: a second resolver call could rebind to a private IP.
No proxy environment, cookies, authentication, or browser execution is used here.
"""
import http.client
import ipaddress
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser


class ResourceError(ValueError):
    pass


def validate_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise ValueError()
        if parts.username or parts.password or parts.port not in (None, 80, 443):
            raise ValueError()
        if any(ord(c) < 32 for c in url) or '\\' in url or '%' in parts.hostname:
            raise ValueError()
        host = parts.hostname.encode('idna').decode('ascii')
        if host.lower().rstrip('.') in ('localhost', 'metadata.google.internal') or host.lower().endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not public_address(address):
            raise ValueError()
        netloc = f'[{host}]' if ':' in host else host
        if parts.port:
            netloc += f':{parts.port}'
        return urlunsplit((parts.scheme, netloc, parts.path or '/', parts.query, ''))
    except (ValueError, UnicodeError):
        raise ResourceError('Only public HTTP(S) URLs on ports 80/443 without credentials are allowed.') from None


def public_address(address):
    if getattr(address, 'ipv4_mapped', None):
        return public_address(address.ipv4_mapped)
    if getattr(address, 'sixtofour', None):
        return public_address(address.sixtofour)
    return address.is_global and not (address.is_multicast or address.is_reserved or address.is_unspecified)


def resolve_public(url):
    url = validate_url(url)
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    try:
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)))
    except OSError:
        raise ResourceError('Resource hostname could not be resolved.') from None
    if not addresses or any(not public_address(ipaddress.ip_address(ip)) for ip in addresses):
        raise ResourceError('Resource resolves to a private, reserved, loopback, link-local or metadata address.')
    return url, addresses[0], port


def allowed_path(value, root):
    if not root:
        raise ResourceError('Local resources are disabled. Upload the file or configure ALLOWED_RESOURCE_DIR.')
    try:
        base = Path(root).resolve(strict=True)
        path = Path(value).resolve(strict=True)
        path.relative_to(base)
    except (ValueError, OSError):
        raise ResourceError('Local resource is missing or outside ALLOWED_RESOURCE_DIR.') from None
    if not path.is_file() or path.suffix.lower() not in ('.txt', '.pdf', '.html', '.htm'):
        raise ResourceError('Only explicitly authorized TXT, HTML and text PDF files are supported.')
    return path


class PublicFetcher:
    def __init__(self, config):
        self.config = config
        self.robots = {}

    def _once(self, url):
        url, ip, port = resolve_public(url)
        parts = urlsplit(url)
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=self.config.request_timeout)
        # Pin the connection to this exact validated address. TLS still verifies the original hostname.
        raw = socket.create_connection((ip, port), self.config.request_timeout)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) if parts.scheme == 'https' else raw
            path = parts.path + (('?' + parts.query) if parts.query else '')
            connection.request('GET', path, headers={'User-Agent': 'AdaptiveLearningBot/0.1', 'Accept-Encoding': 'identity', 'Accept': 'text/html,application/pdf,text/plain'})
            response = connection.getresponse()
            headers = dict((k.lower(), v) for k, v in response.getheaders())
            if response.status != 200:
                return response.status, headers, b''
            if headers.get('content-encoding', 'identity') != 'identity':
                raise ResourceError('Compressed responses are not supported by the bounded fetcher.')
            if int(headers.get('content-length', 0)) > self.config.max_download_bytes:
                raise ResourceError('Resource exceeds MAX_DOWNLOAD_BYTES.')
            chunks, size, started = [], 0, time.monotonic()
            while True:
                if time.monotonic() - started > self.config.request_timeout:
                    raise ResourceError('Download exceeded the time limit.')
                chunk = response.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.config.max_download_bytes:
                    raise ResourceError('Resource exceeds MAX_DOWNLOAD_BYTES.')
                chunks.append(chunk)
            return response.status, headers, b''.join(chunks)
        finally:
            connection.close()
            raw.close()

    def _request(self, url):
        for attempt in range(self.config.retries + 1):
            try:
                result = self._once(url)
                if result[0] not in (429, 500, 502, 503, 504):
                    return result
            except (OSError, http.client.HTTPException):
                if attempt == self.config.retries:
                    raise ResourceError('Public resource download failed after bounded retries.') from None
            if attempt < self.config.retries:
                time.sleep(min(2 ** attempt, 4))
        raise ResourceError('Public resource is rate limited or unavailable. Try later or supply a different source.')

    def _robots_allowed(self, url):
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.robots:
            status, _, body = self._request(origin + '/robots.txt')
            if status in (401, 403) or 300 <= status < 400:
                raise ResourceError('Access restrictions on robots.txt prevent fetching this site.')
            if status not in (200, 404, 410):
                raise ResourceError('robots.txt could not be checked; choose another accessible source.')
            parser = RobotFileParser()
            parser.parse(body.decode('utf-8', errors='replace').splitlines() if status == 200 else [])
            self.robots[origin] = parser
        if not self.robots[origin].can_fetch('AdaptiveLearningBot', url):
            raise ResourceError('This source disallows automated retrieval in robots.txt.')

    def fetch(self, url):
        for _ in range(5):
            url = validate_url(url)
            self._robots_allowed(url)
            status, headers, data = self._request(url)
            if status in (301, 302, 303, 307, 308):
                url = validate_url(urljoin(url, headers.get('location', '')))
                continue
            if status != 200:
                raise ResourceError(f'Source returned HTTP {status}; authentication and paywalls will not be bypassed.')
            return url, headers.get('content-type', '').split(';')[0], data
        raise ResourceError('Resource exceeded the redirect limit.')
