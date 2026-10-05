import { createWriteStream } from 'node:fs';
import { readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

export const SOURCE_ARCHIVE_NAME = 'source.tar.gz';
export const SOURCE_ARCHIVE_PART_PREFIX = 'source.tar.gz.part.';
export const SOURCE_STAMP_NAME = '.grund-source.json';
export const CHAT_CONFIG_FILE = 'librechat.nordman.yaml';
export const CHAT_RUNTIME_CONFIG = 'librechat.yaml';
export const HIDDEN_APPLE_DOUBLE = '._';
export const HIDDEN_DS_STORE = '.DS_Store';

const CHAT_REQUIRED = ['package.json', CHAT_CONFIG_FILE, 'api/server/index.js'];
const DEFAULT_REQUIRED = ['package.json'];

export function requiredSourceFiles(name) {
  if (name === 'chat') {
    return CHAT_REQUIRED;
  }
  return DEFAULT_REQUIRED;
}

export function isHiddenSourcePath(path) {
  return path.split('/').some(
    (part) => part === HIDDEN_DS_STORE || part.startsWith(HIDDEN_APPLE_DOUBLE),
  );
}

export function isArchivePartName(name) {
  return name.startsWith(SOURCE_ARCHIVE_PART_PREFIX);
}

export function assertArchiveContentType(type) {
  const lower = String(type ?? '').toLowerCase();
  if (lower.includes('text/html') || lower.includes('text/xml')) {
    throw new Error('archive returned HTML, not source');
  }
}

export function isGzipArchiveType(type) {
  const lower = String(type ?? '').toLowerCase();
  return lower.includes('gzip') || lower.includes('tar');
}

export async function listSourceFiles(root) {
  const files = [];
  async function walk(dir) {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = join(dir, entry.name);
      const rel = relative(root, full).replaceAll('\\', '/');
      if (entry.isDirectory()) {
        if (entry.name === '.git' || entry.name === 'node_modules') {
          continue;
        }
        await walk(full);
        continue;
      }
      files.push(rel);
    }
  }
  await walk(root);
  return files.sort();
}

export async function stripHiddenSourceFiles(root) {
  const files = await listSourceFiles(root);
  let removed = 0;
  for (const path of files) {
    if (!isHiddenSourcePath(path)) {
      continue;
    }
    await rm(join(root, path), { force: true });
    removed += 1;
  }
  return removed;
}

export async function assembleArchiveParts(root) {
  const files = await listSourceFiles(root);
  const parts = files
    .filter((path) => isArchivePartName(path.split('/').pop() ?? ''))
    .sort();
  if (parts.length === 0) {
    return false;
  }
  const archive = join(root, SOURCE_ARCHIVE_NAME);
  const output = createWriteStream(archive);
  for (const path of parts) {
    await pipeline(Readable.from(await readFile(join(root, path))), output, { end: false });
  }
  output.end();
  await new Promise((resolve, reject) => {
    output.on('finish', resolve);
    output.on('error', reject);
  });
  await run('tar', ['-xzf', archive, '-C', root]);
  for (const path of parts) {
    await rm(join(root, path), { force: true });
  }
  await rm(archive, { force: true });
  return true;
}

export async function installChatRuntimeConfig(root, name) {
  if (name !== 'chat') {
    return false;
  }
  const source = join(root, CHAT_CONFIG_FILE);
  const dest = join(root, CHAT_RUNTIME_CONFIG);
  try {
    await stat(source);
  } catch {
    return false;
  }
  try {
    await stat(dest);
    return false;
  } catch {
    await writeFile(dest, await readFile(source));
    return true;
  }
}

export async function verifyFetchedSource(root, name) {
  const missing = [];
  for (const path of requiredSourceFiles(name)) {
    try {
      await stat(join(root, path));
    } catch {
      missing.push(path);
    }
  }
  if (missing.length > 0) {
    throw new Error(`missing source files for ${name}: ${missing.join(', ')}`);
  }
}

export async function writeSourceStamp(root, info) {
  await writeFile(join(root, SOURCE_STAMP_NAME), `${JSON.stringify(info, null, 2)}\n`);
}

export async function flattenArchiveRoot(root) {
  if ((await listSourceFiles(root)).includes('package.json')) {
    return false;
  }
  const entries = await readdir(root, { withFileTypes: true });
  const visible = entries.filter((entry) => !entry.name.startsWith('.'));
  if (visible.length !== 1 || !visible[0].isDirectory()) {
    return false;
  }
  const nested = join(root, visible[0].name);
  for (const entry of await readdir(nested, { withFileTypes: true })) {
    const from = join(nested, entry.name);
    const to = join(root, entry.name);
    await run('mv', [from, to]);
  }
  await rm(nested, { recursive: true, force: true });
  return true;
}

export async function materializeFetchedSource(root, name) {
  const flattened = await flattenArchiveRoot(root);
  const files = await listSourceFiles(root);
  const assembled = files.includes('package.json') ? false : await assembleArchiveParts(root);
  const hidden = await stripHiddenSourceFiles(root);
  const installedConfig = await installChatRuntimeConfig(root, name);
  await verifyFetchedSource(root, name);
  const stamp = {
    name,
    flattened,
    assembled,
    hidden,
    installedConfig,
    files: (await listSourceFiles(root)).length,
  };
  await writeSourceStamp(root, stamp);
  return stamp;
}
