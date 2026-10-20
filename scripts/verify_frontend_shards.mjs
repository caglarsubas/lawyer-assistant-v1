/** Fail closed if Vitest's two CI shards do not cover every discovered file once. */
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { relative, resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { BaseSequencer } from '../frontend/node_modules/vitest/dist/node.js';
import assert from 'node:assert/strict';
const root = resolve(fileURLToPath(new URL('../frontend/', import.meta.url)));
function files() {
  const rows = JSON.parse(execFileSync(process.execPath, ['node_modules/vitest/vitest.mjs', 'list',
    '--filesOnly', '--json'], { cwd: root, encoding: 'utf8' }));
  const paths = rows.map(row => relative(root, row.file)).sort();
  assert(paths.length > 0, 'Empty frontend discovery');
  assert.equal(new Set(paths).size, paths.length, 'Duplicate discovered frontend files');
  return paths;
}
const all = files();
async function shard(index) {
  const sequencer = new BaseSequencer({ config: { root, shard: { index, count: 2 } } });
  return (await sequencer.shard(all.map(file => ({ moduleId: resolve(root, file) }))))
    .map(spec => relative(root, spec.moduleId)).sort();
}
const first = await shard(1), second = await shard(2);
assert.deepEqual([...first, ...second].sort(), all, 'Shards must cover every file exactly once');
const args = process.argv.slice(2);
if (args.length) {
  assert.equal(args.length, 2, 'Expected result JSON path and shard number');
  assert(['1', '2'].includes(args[1]), 'Invalid shard');
  const result = JSON.parse(readFileSync(args[0], 'utf8'));
  assert.equal(result.success, true, 'Shard tests failed');
  assert(result.numTotalTests > 0 && result.numTotalTests === result.numPassedTests, 'Every case must pass');
  const actual = result.testResults.map(row => relative(root, row.name)).sort();
  assert.deepEqual(actual, args[1] === '1' ? first : second, 'Executed shard must equal discovered shard');
  console.log(JSON.stringify({ shard: Number(args[1]), passed_cases: result.numPassedTests, executed_files: actual.length }));
}
console.log(JSON.stringify({ files: all.length, shards: [first.length, second.length], disjoint: true }));
