import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { archiveUrl, sourceRevision } from './source-revision.mjs';

const SHA = '8358cb61109041c00fbb9e9a48f5d30cc72a6e32';

test('accepts only a full commit SHA', () => {
  assert.equal(sourceRevision(SHA), SHA);
  assert.throws(() => sourceRevision('main'), /full 40-character/);
  assert.throws(() => sourceRevision(''), /full 40-character/);
  assert.throws(() => sourceRevision('8358cb611090'), /full 40-character/);
});

test('archive URL is the Gitea archive of that commit', () => {
  assert.equal(
    archiveUrl('https://nordman-grund.onrender.com/', 'nordman', 'chat', SHA),
    `https://nordman-grund.onrender.com/api/v1/repos/nordman/chat/archive/${SHA}.tar.gz`,
  );
});

test('the image fetch step is cached on the revision', () => {
  const dockerfile = readFileSync(new URL('./Dockerfile', import.meta.url), 'utf8');
  assert.match(dockerfile, /ARG GRUND_SOURCE_REVISION/);
  assert.match(
    dockerfile,
    /RUN echo "grund-source-revision \$\{GRUND_SOURCE_REVISION\}" \\\n && node \/runtime\/fetch-source\.mjs --out \/app/,
  );
  const fetchSource = readFileSync(new URL('./fetch-source.mjs', import.meta.url), 'utf8');
  assert.match(fetchSource, /sourceRevision\(process\.env\.GRUND_SOURCE_REVISION\)/);
  assert.doesNotMatch(fetchSource, /GRUND_SOURCE_REF/);
});
