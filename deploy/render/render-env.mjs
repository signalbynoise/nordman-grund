#!/usr/bin/env node

function required(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`missing ${name}`);
  }
  return value;
}

function parseDatabaseUrl(raw) {
  const url = new URL(raw);
  if (url.protocol !== 'postgres:' && url.protocol !== 'postgresql:') {
    throw new Error(`unsupported database protocol: ${url.protocol}`);
  }
  const host = url.hostname;
  const port = url.port || '5432';
  const user = decodeURIComponent(url.username);
  const password = decodeURIComponent(url.password);
  const name = url.pathname.replace(/^\//, '');
  return { host, port, user, password, name };
}

const rootUrl = (process.env.GRUND_PUBLIC_ORIGIN ?? process.env.GITEA_ROOT_URL ?? '').replace(/\/$/, '');
const port = process.env.PORT ?? '10000';
const db = parseDatabaseUrl(required('DATABASE_URL'));

const lines = [
  `GITEA__server__DOMAIN=${new URL(`${rootUrl}/`).hostname}`,
  `GITEA__server__ROOT_URL=${rootUrl}/`,
  `GITEA__server__HTTP_ADDR=0.0.0.0`,
  `GITEA__server__HTTP_PORT=${port}`,
  `GITEA__server__APP_DATA_PATH=/repos/gitea`,
  `GITEA__repository__ROOT=/repos/git/repositories`,
  `GITEA__lfs__PATH=/repos/git/lfs`,
  `GITEA__database__DB_TYPE=postgres`,
  `GITEA__database__HOST=${db.host}:${db.port}`,
  `GITEA__database__NAME=${db.name}`,
  `GITEA__database__USER=${db.user}`,
  `GITEA__database__PASSWD=${db.password}`,
  `GITEA__database__SSL_MODE=${process.env.GITEA__database__SSL_MODE ?? 'require'}`,
  `GITEA__security__INSTALL_LOCK=${process.env.GITEA__security__INSTALL_LOCK ?? 'true'}`,
  `GITEA__service__DISABLE_REGISTRATION=${process.env.GITEA__service__DISABLE_REGISTRATION ?? 'false'}`,
  `GITEA__mailer__ENABLED=${process.env.GITEA__mailer__ENABLED ?? 'false'}`,
];

if (process.env.APP_NAME) {
  lines.push(`GITEA__other__APP_NAME=${process.env.APP_NAME}`);
}

process.stdout.write(`${lines.join('\n')}\n`);
