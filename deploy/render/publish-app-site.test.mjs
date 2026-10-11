import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { flattenArchiveRoot, readRevisionMeta } from './publish-app-site.mjs';

test('reads the revision meta from published HTML', () => {
  const html = '<html><head><meta name="nordman-revision" content="3a4e99e6" /></head></html>';
  assert.equal(readRevisionMeta(html), '3a4e99e6');
  assert.equal(readRevisionMeta('<html></html>'), '');
});

test('flattens the single archive prefix so index.html is at the site root', async () => {
  const root = await mkdtemp(join(tmpdir(), 'nordman-site-'));
  try {
    await mkdir(join(root, 'clipshare'));
    await writeFile(join(root, 'clipshare', 'index.html'), '<meta name="nordman-revision" content="3a4e99e6" />');
    await writeFile(join(root, 'clipshare', 'boot.js'), 'console.log(1)\n');
    assert.equal(await flattenArchiveRoot(root), true);
    const html = await readFile(join(root, 'index.html'), 'utf8');
    assert.match(html, /nordman-revision/);
    assert.equal(await readFile(join(root, 'boot.js'), 'utf8'), 'console.log(1)\n');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
