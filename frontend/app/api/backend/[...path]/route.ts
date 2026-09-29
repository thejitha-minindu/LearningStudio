import { NextRequest } from 'next/server';
export const runtime = 'nodejs';

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const base = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
  const headers: Record<string, string> = {
    'X-Learner-ID': 'demo-learner',
    'X-Dev-Token': process.env.DEV_API_TOKEN || 'local-development-only',
  };
  const type = request.headers.get('content-type');
  if (type) headers['Content-Type'] = type;
  const limit = Number(process.env.MAX_DOWNLOAD_BYTES || 5000000) + 65536;
  if (Number(request.headers.get('content-length') || 0) > limit) return Response.json({ detail: 'Upload too large.' }, { status: 413 });
  try {
    const chunks: Uint8Array[] = [];
    let length = 0;
    if (request.body) {
      const reader = request.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.length;
        if (length > limit) { await reader.cancel(); return Response.json({ detail: 'Upload too large.' }, { status: 413 }); }
        chunks.push(value);
      }
    }
    const response = await fetch(`${base}/${path.map(encodeURIComponent).join('/')}`, {
      method: request.method, headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : Buffer.concat(chunks),
      cache: 'no-store', signal: AbortSignal.timeout(180000),
    });
    return new Response(await response.arrayBuffer(), { status: response.status, headers: { 'Content-Type': response.headers.get('content-type') || 'application/json' } });
  } catch {
    return Response.json({ detail: 'Backend unavailable or timed out. Start the API and check BACKEND_URL. Retrying the same task or answer ID is safe.' }, { status: 503 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH };
