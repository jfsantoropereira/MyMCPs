// Regression tests for validatePath symlink/containment checks.
// Run: node --test test/path-validation.test.mjs (node >= 22.18 / 23.6 strips types from the .ts import)
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { validatePath } from '../path-validation.ts';

let root, allowed, outside, sibling, allowedDirs;

const isInside = (p) => p === allowed || p.startsWith(allowed + path.sep);

before(async () => {
  root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'pv-')));
  allowed = path.join(root, 'allowed');
  outside = path.join(root, 'outside');
  sibling = `${allowed}-private`;
  await fs.mkdir(path.join(allowed, 'sub'), { recursive: true });
  await fs.mkdir(path.join(outside, 'dir'), { recursive: true });
  await fs.mkdir(sibling);
  await fs.writeFile(path.join(outside, 'secret.txt'), 'outside\n');
  await fs.writeFile(path.join(outside, 'dir', 'inner.txt'), 'outside\n');
  await fs.writeFile(path.join(sibling, 's.txt'), 'sibling\n');
  await fs.writeFile(path.join(allowed, 'ok.txt'), 'inside\n');
  await fs.symlink(path.join(outside, 'secret.txt'), path.join(allowed, 'l_file'));
  await fs.symlink(path.join(outside, 'dir'), path.join(allowed, 'l_dir'));
  await fs.symlink(path.join(outside, 'missing.txt'), path.join(allowed, 'l_dangling'));
  await fs.symlink(path.join(allowed, 'ok.txt'), path.join(allowed, 'l_inside'));
  allowedDirs = [allowed];
});

after(async () => {
  if (root) await fs.rm(root, { recursive: true, force: true });
});

test('rejects symlink to a file outside the allowed directory', async () => {
  await assert.rejects(validatePath(path.join(allowed, 'l_file'), allowedDirs), /Access denied/);
});

test('rejects symlink to a directory outside the allowed directory', async () => {
  await assert.rejects(validatePath(path.join(allowed, 'l_dir'), allowedDirs), /Access denied/);
  await assert.rejects(validatePath(path.join(allowed, 'l_dir', 'inner.txt'), allowedDirs));
});

test('rejects dangling symlink pointing outside (no outside file created)', async () => {
  await assert.rejects(validatePath(path.join(allowed, 'l_dangling'), allowedDirs), /Access denied/);
  await assert.rejects(fs.access(path.join(outside, 'missing.txt')));
});

test('rejects sibling directory sharing the allowed prefix', async () => {
  await assert.rejects(validatePath(path.join(sibling, 's.txt'), allowedDirs), /Access denied/);
  await assert.rejects(validatePath(path.join(sibling, 'new.txt'), allowedDirs), /Access denied/);
});

test('rejects .. traversal out of the allowed directory', async () => {
  await assert.rejects(validatePath(path.join(allowed, '..', 'outside', 'secret.txt'), allowedDirs), /Access denied/);
  await assert.rejects(validatePath(`${allowed}/../outside/new.txt`, allowedDirs), /Access denied/);
});

test('allows a regular file inside', async () => {
  const p = await validatePath(path.join(allowed, 'ok.txt'), allowedDirs);
  assert.equal(p, path.join(allowed, 'ok.txt'));
});

test('allows a symlink that points inside and returns its real path', async () => {
  const p = await validatePath(path.join(allowed, 'l_inside'), allowedDirs);
  assert.equal(p, path.join(allowed, 'ok.txt'));
});

test('allows a new file in an existing inside subdirectory', async () => {
  const p = await validatePath(path.join(allowed, 'sub', 'new.txt'), allowedDirs);
  assert.ok(isInside(p), p);
  assert.equal(p, path.join(allowed, 'sub', 'new.txt'));
});

test('allows in-scope names that begin with dots', async () => {
  const p = await validatePath(path.join(allowed, '..foo'), allowedDirs);
  assert.equal(p, path.join(allowed, '..foo'));
});
