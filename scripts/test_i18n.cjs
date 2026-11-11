'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function load(page, search = '?lang=zh', saved = null) {
  const context = { window: {}, URL, location: {href: `https://example.test/${search}`},
    localStorage: {getItem: () => saved}, document: {readyState:'loading',addEventListener(){}}, console };
  vm.createContext(context);
  for (const file of ['i18n-common.js', `i18n-${page}.js`, 'i18n.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'dist/assets', file), 'utf8'), context);
  }
  return context.window.ShowcaseI18n;
}
const home = load('home'), archive = load('archive');
assert.equal(home.language, 'zh');
assert.equal(load('home', '?lang=en', 'zh').language, 'en');
assert.equal(load('home', '', 'zh').language, 'en');
assert.equal(load('archive', '', 'zh').language, 'en');
assert.equal(load('archive', '', null).language, 'en');
assert.equal(home.translate('Introduction'), '项目介绍');
assert.equal(home.translate('6 of 10'), '6 / 10');
assert.equal(home.translate('DreamX-RoboConductor'), 'DreamX-RoboConductor');
assert.equal(home.translate('  Introduction\n', 'en'), '  Introduction\n');
assert.match(home.translate('TASK 01 · 4 / 5 SUCCESS'), /任务.*01.*4.*5.*成功/);
assert.match(home.translate('Scene 05 · Failure'), /场景.*05.*失败/);
assert.match(archive.translate('50 tasks · 500 episodes · 411 / 500 Success'), /50.*500.*411.*500.*成功/);
assert.equal(home.translate('Experiments'), archive.translate('Experiments'));
assert.equal(archive.translate('Success rate'), '成功率');
assert.equal(archive.translate('Episodes'), '试验');
const data = JSON.parse(fs.readFileSync(path.join(root, 'dist/data/page-data.json'), 'utf8'));
for (const task of data.simulation.tasks) {
  assert.equal(home.translate(task.name), task.name);
  const title = task.id.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  assert.equal(archive.translate(title), title);
}
for (const task of data.real.tasks) assert.equal(home.translate(task.title), task.title);
for (const item of data.simulation.featured) assert.equal(home.translate(item.title), item.title);
assert.equal(home.translate('Adjust Bottle · Success'), 'Adjust Bottle · 成功');
console.log('PASS English default, explicit language selection, English task names, translated UI, and source preservation');
