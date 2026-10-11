import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';
import { fetchSourceArchive } from '../runtime/fetch-archive.mjs';
import { archiveUrl, sourceRevision } from '../runtime/source-revision.mjs';
import {
  assertArchiveContentType,
  isGzipArchiveType,
} from '../runtime/materialize-source.mjs';

const run = promisify(execFile);

export const PUBLISH_DIR = '.nordman-site';

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`missing ${name}`);
  }
  return value;
}

export async function flattenArchiveRoot(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const visible = entries.filter((entry) => !entry.name.startsWith('.'));
  if (visible.length !== 1 || !visible[0].isDirectory()) {
    return false;
  }
  const nested = join(root, visible[0].name);
  for (const entry of await readdir(nested)) {
    await run('mv', [join(nested, entry), join(root, entry)]);
  }
  await rm(nested, { recursive: true, force: true });
  return true;
}

export async function publishAppSite(outDir = resolve(PUBLISH_DIR)) {
  const origin = requiredEnv('GRUND_URL').replace(/\/$/, '');
  const owner = requiredEnv('GRUND_OWNER');
  const name = requiredEnv('GRUND_NAME');
  const token = requiredEnv('GRUND_DEPLOY_TOKEN');
  const revision = sourceRevision(process.env.GRUND_SOURCE_REVISION);

  const response = await fetchSourceArchive(archiveUrl(origin, owner, name, revision), token);
  const type = response.headers.get('content-type') ?? '';
  assertArchiveContentType(type);
  if (!isGzipArchiveType(type)) {
    throw new Error(`expected tar.gz archive, got ${type || 'unknown'}`);
  }

  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });
  const archive = join(outDir, 'source.tar.gz');
  await writeFile(archive, Buffer.from(await response.arrayBuffer()));
  await run('tar', ['-xzf', archive, '-C', outDir]);
  await rm(archive, { force: true });
  const flattened = await flattenArchiveRoot(outDir);

  const html = await readFile(join(outDir, 'index.html'), 'utf8');
  const revisionMeta = readRevisionMeta(html);
  if (!revisionMeta) {
    throw new Error('index.html is missing the nordman-revision meta tag');
  }
  console.log(`revision: ${revision}`);
  console.error(
    `[info] [grund:app] published ${owner}/${name} { revision: ${revision}, flattened: ${flattened}, nordman-revision: ${revisionMeta} }`,
  );
}

export function readRevisionMeta(html) {
  const tag = String(html).match(/<meta\s+[^>]*name=["']nordman-revision["'][^>]*>/i);
  if (!tag) {
    return '';
  }
  const content = tag[0].match(/content=["']([^"']*)["']/);
  return content ? content[1] : '';
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  publishAppSite().catch((error) => {
    const message = error instanceof Error ? error.message : 'publish failed';
    console.error(`[warn] [grund:app] ${message}`);
    process.exit(1);
  });
}
