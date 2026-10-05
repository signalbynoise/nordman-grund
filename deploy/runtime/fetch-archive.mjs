export const ARCHIVE_RETRY = {
  attempts: 5,
  delayMs: 2_000,
  statuses: [429, 502, 503],
};

export function isTransientArchiveStatus(status) {
  return ARCHIVE_RETRY.statuses.includes(Number(status));
}

export async function waitArchiveRetry(attempt, sleep = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
})) {
  await sleep(ARCHIVE_RETRY.delayMs * attempt);
}

export function giteaAuthHeader(token) {
  if (token.startsWith('Bearer ') || token.startsWith('token ')) {
    return token;
  }
  return `token ${token}`;
}

export async function fetchSourceArchive(
  url,
  token,
  deps = { fetch, sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)) },
) {
  let lastStatus = 0;
  for (let attempt = 1; attempt <= ARCHIVE_RETRY.attempts; attempt += 1) {
    const response = await deps.fetch(url, {
      headers: { authorization: giteaAuthHeader(token) },
    });
    if (response.ok) {
      return response;
    }
    lastStatus = response.status;
    if (
      !isTransientArchiveStatus(response.status) ||
      attempt === ARCHIVE_RETRY.attempts
    ) {
      throw new Error(`archive ${response.status}`);
    }
    console.error(
      `[warn] [runtime:fetch] archive ${response.status}, retry ${attempt}`,
    );
    await waitArchiveRetry(attempt, deps.sleep);
  }
  throw new Error(`archive ${lastStatus}`);
}
