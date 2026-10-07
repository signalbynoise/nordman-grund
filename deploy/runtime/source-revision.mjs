const REVISION_PATTERN = /^[0-9a-f]{40}$/;

export function sourceRevision(value) {
  const revision = String(value ?? '').trim();
  if (!REVISION_PATTERN.test(revision)) {
    throw new Error('GRUND_SOURCE_REVISION must be the full 40-character commit SHA');
  }
  return revision;
}

export function archiveUrl(origin, owner, name, revision) {
  const base = String(origin).replace(/\/$/, '');
  return `${base}/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/archive/${revision}.tar.gz`;
}
