// 一次性脚本：把 readme.MD 里过时的「手工清缓存」流程换成自动化后的流程。
const fs = require('node:fs');

const file = 'openEDU/readme.MD';
const src = fs.readFileSync(file, 'utf8');
const eol = src.includes('\r\n') ? '\r\n' : '\n';
const lines = src.split(/\r?\n/);

// 原第 35-45 行（脚标 34-44）：那段还写着 openEDU-purge.js / openEDU-check.js
// 这两个脚本磁盘上已经不存在了，改用新的自动化流程。
const oldBlock = lines.slice(34, 45).join(eol);
console.log('--- 将被替换的内容 ---');
console.log(oldBlock);

const newBlock = [
  '你现在的流程（2026-10-26 起，缓存这一步已经自动化了）：',
  '',
  '1. 更新数据 → 本地改 openEDU/ 下的 JSON / 图片',
  '2. 推送     → git push 到 GitHub main 分支',
  '3. 自动清理 → .github/workflows/purge-cdn.yml 触发，',
  '              对这次改动过的每个路径各调一次 jsDelivr purge',
  '4. 验证（可选）→ node scripts/purge-cdn.mjs --list=changed.txt --verify',
  '               或直接把 CDN 地址贴浏览器里看内容',
  '',
  '新增的文件本来就没有缓存（push 完立刻可见），只有改过的文件需要清 ——',
  '所以 workflow 只对本次 diff 里真正变动的路径发请求，不做全量扫。',
  '手工补一次：GitHub → Actions → Purge CDN cache → Run workflow。',
  '',
  '这套组合拳可以确保 CDN 始终提供最新数据，不再被缓存困扰。',
].join(eol);

const out = [...lines.slice(0, 34), ...newBlock.split(eol), ...lines.slice(45)].join(eol);
fs.writeFileSync(file, out, 'utf8');
console.log('\n--- 写好了 ---');
console.log(fs.readFileSync(file, 'utf8').split(/\r?\n/).slice(33, 50).join('\n'));
