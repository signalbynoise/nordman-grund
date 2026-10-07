import { mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fetchSourceArchive } from './fetch-archive.mjs';
import {
  SOURCE_ARCHIVE_NAME,
  assertArchiveContentType,
  isGzipArchiveType,
  materializeFetchedSource,
} from './materialize-source.mjs';
import { archiveUrl, sourceRevision } from './source-revision.mjs';

const run = promisify(execFile);

function readArg(name, fallback) {
  const flag = `--${name}`;
  const index = process.argv.indexOf(flag);
  if (index !== -1 && process.argv[index + 1]) {
    return process.argv[index + 1];
  }
  return fallback;
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`missing ${name}`);
  }
  return value;
}

const origin = requiredEnv('GRUND_URL').replace(/\/$/, '');
const owner = requiredEnv('GRUND_OWNER');
const name = requiredEnv('GRUND_NAME');
const token = requiredEnv('GRUND_DEPLOY_TOKEN');
const revision = sourceRevision(process.env.GRUND_SOURCE_REVISION);
const outDir = resolve(readArg('out', process.env.GRUND_SOURCE_DIR ?? '.grund-src'));

const response = await fetchSourceArchive(archiveUrl(origin, owner, name, revision), token);

const type = response.headers.get('content-type') ?? '';
assertArchiveContentType(type);

async function prepareOutDir(dir) {
  try {
    const entries = await readdir(dir);
    await Promise.all(
      entries.map((entry) => rm(resolve(dir, entry), { recursive: true, force: true })),
    );
  } catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') {
      await mkdir(dir, { recursive: true });
      return;
    }
    throw error;
  }
}

await prepareOutDir(outDir);
if (!isGzipArchiveType(type)) {
  throw new Error(`expected tar.gz archive, got ${type || 'unknown'}`);
}

const archive = resolve(outDir, SOURCE_ARCHIVE_NAME);
await writeFile(archive, Buffer.from(await response.arrayBuffer()));
await run('tar', ['-xzf', archive, '-C', outDir]);
await rm(archive, { force: true });

const stamp = await materializeFetchedSource(outDir, name);
console.error(
  `[info] [runtime:fetch] extracted ${owner}/${name} { out: ${outDir}, ref: ${revision}, revision: ${revision}, files: ${stamp.files}, hidden: ${stamp.hidden}, flattened: ${stamp.flattened}, assembled: ${stamp.assembled}, installedConfig: ${stamp.installedConfig} }`,
);
