#!/usr/bin/env node

const origin = (process.env.GRUND_URL ?? process.env.GRUND_PUBLIC_ORIGIN ?? '').replace(/\/$/, '');
const token = process.env.GITEA_ADMIN_TOKEN ?? process.env.GRUND_ADMIN_TOKEN;
const owner = process.env.GRUND_OWNER ?? 'nordman';

const hooks = [
  { repo: 'web', url: process.env.RENDER_DEPLOY_HOOK_WEB },
  { repo: 'chat', url: process.env.RENDER_DEPLOY_HOOK_CHAT },
].filter((item) => item.url);

if (!origin || !token) {
  console.error('Set GRUND_URL and GITEA_ADMIN_TOKEN (or GRUND_ADMIN_TOKEN).');
  process.exit(1);
}

if (hooks.length === 0) {
  console.error('Set RENDER_DEPLOY_HOOK_WEB and/or RENDER_DEPLOY_HOOK_CHAT.');
  process.exit(1);
}

async function upsertWebhook(repo, hookUrl) {
  const listUrl = `${origin}/api/v1/repos/${owner}/${repo}/hooks`;
  const headers = {
    authorization: `token ${token}`,
    'content-type': 'application/json',
  };
  const list = await fetch(listUrl, { headers });
  if (!list.ok) {
    throw new Error(`list hooks ${repo}: ${list.status}`);
  }
  const existing = await list.json();
  const match = existing.find((hook) => hook.config?.url === hookUrl);
  const body = {
    type: 'gitea',
    active: true,
    events: ['push'],
    config: {
      url: hookUrl,
      content_type: 'json',
    },
  };
  if (match) {
    const response = await fetch(`${listUrl}/${match.id}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`update hook ${repo}: ${response.status}`);
    }
    console.error(`[info] [deploy:webhook] updated ${owner}/${repo}`);
    return;
  }
  const response = await fetch(listUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`create hook ${repo}: ${response.status}`);
  }
  console.error(`[info] [deploy:webhook] created ${owner}/${repo}`);
}

for (const hook of hooks) {
  await upsertWebhook(hook.repo, hook.url);
}
