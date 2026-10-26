#!/usr/bin/env node
/**
 * 把改动过的路径在 jsDelivr 上的缓存清掉。
 *
 * 背景：前台的数据/图片全走
 *   https://cdn.jsdelivr.net/gh/<REPO>@<BRANCH>/openEDU/...
 * jsDelivr 对**分支**（@main）的缓存是 12 小时（响应头 s-maxage=43200）。
 * 所以：
 *   - 新增文件：CDN 没缓存过，push 后立刻就有，不用管；
 *   - 改过的文件：不加处理的话最长要等 12 小时才生效。
 * 这里是给后者补一刀 —— 对着 https://purge.jsdelivr.net 挨个 GET 一次。
 *
 * 两个踩过的坑：
 *   1. purge 端点是 GET，不是 POST（POST 会 405）；
 *   2. 加 ?v=xxx 版本号没用 —— jsDelivr 按路径缓存，忽略 query string。
 *
 * 用法：
 *   node scripts/purge-cdn.mjs --list=changed.txt      # 文件里每行一个相对路径
 *   node scripts/purge-cdn.mjs openEDU/a.json openEDU/b.jpg   # 直接给路径
 *   node scripts/purge-cdn.mjs --list=changed.txt --dry-run   # 只打印将要做什么
 *   node scripts/purge-cdn.mjs --list=changed.txt --verify    # 清完再复查 Age
 *
 * 路径列表必须用 --list= 给：早先版本靠「参数是不是个文件」来判断，
 * 结果单个 openEDU/...json 参数会被当成列表文件读进去（拿 JSON 正文当路径）。
 */

import fs from 'node:fs';

const REPO = process.env.JSDELIVR_REPO || 'HKBrianNg/img-library';
const BRANCH = process.env.JSDELIVR_BRANCH || 'main';
const ROOT = 'openEDU/';
const PURGE_BASE = 'https://purge.jsdelivr.net';
const CDN_BASE = `https://cdn.jsdelivr.net/gh/${REPO}@${BRANCH}`;

// 一次 purge 一个文件，太多请求既慢又容易撞限流。
// 正常一次推几十个文件；超过这个数大概率是误操作（比如把整个目录重命名了），
// 宁可报警让人来处理，也别闷头打几百个请求。
const MAX_FILES = 200;
const PAUSE_MS = 120; // 请求之间留点间隔，别把限流招来

const argv = process.argv.slice(2);
const dryRun = argv.includes('--dry-run');
const verify = argv.includes('--verify');
const pathArgs = argv.filter((a) => !a.startsWith('--'));
const listFile = (argv.find((a) => a.startsWith('--list=')) || '').slice('--list='.length);

/** 路径列表：--list= 给文件，否则就是命令行上的路径 */
function readPaths() {
  if (listFile) {
    return fs
      .readFileSync(listFile, 'utf8')
      .replace(/^﻿/, '') // Windows 记事本/PowerShell 写出来的 UTF-8 BOM
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
  }
  return pathArgs;
}

const all = readPaths();
// 只认 openEDU/ 下的；Windows 传来的反斜杠也算进来
const paths = [...new Set(all.map((p) => p.replace(/\\/g, '/').replace(/^\.\//, '')))].filter(
  (p) => p.startsWith(ROOT) && !p.endsWith('/')
);
const ignored = all.length - paths.length;

// encodeURI 保留 / ，只把中文等字符转义 —— 正是 CDN 上那个文件的路径
const relUrl = (rel) => encodeURI(rel);
const cdnUrl = (rel) => `${CDN_BASE}/${relUrl(rel)}`;
const purgeUrl = (rel) => `${PURGE_BASE}/gh/${REPO}@${BRANCH}/${relUrl(rel)}`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function purgeOne(rel) {
  const url = purgeUrl(rel);
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const res = await fetch(url, { redirect: 'follow' });
      // jsDelivr 用法 STATUS finished / pending，两者都算成功
      if (res.ok) {
        const body = await res.text().catch(() => '');
        const status = /"status"\s*:\s*"([^"]+)"/.exec(body);
        return { rel, ok: true, status: status ? status[1] : `HTTP ${res.status}` };
      }
      if (res.status === 429) {
        await sleep(1500 * attempt);
        continue;
      }
      return { rel, ok: false, status: `HTTP ${res.status}` };
    } catch (err) {
      if (attempt === 3) return { rel, ok: false, status: err.message.slice(0, 60) };
      await sleep(1000 * attempt);
    }
  }
  return { rel, ok: false, status: '重试后仍然失败' };
}

async function checkOne(rel) {
  try {
    const res = await fetch(cdnUrl(rel), { method: 'HEAD' });
    return `${res.status}  Age=${res.headers.get('age') ?? '-'}`;
  } catch (err) {
    return `ERR ${err.message.slice(0, 40)}`;
  }
}

async function main() {
  console.log(`仓库: ${REPO}@${BRANCH}`);
  console.log(`待清理: ${paths.length} 个路径${ignored ? `（另有 ${ignored} 个不在 ${ROOT} 下，跳过）` : ''}`);
  if (dryRun) {
    paths.slice(0, 20).forEach((p) => console.log(`  GET ${purgeUrl(p)}`));
    if (paths.length > 20) console.log(`  … 还有 ${paths.length - 20} 个`);
    console.log('\n--dry-run：什么都没真的发送');
    return;
  }
  if (paths.length === 0) {
    console.log('没有需要清理的路径，结束');
    return;
  }
  if (paths.length > MAX_FILES) {
    console.log(
      `\n⚠ 一次 ${paths.length} 个，超过 ${MAX_FILES} 个上限了 —— 多半是误操作。\n` +
        `  确认没问题的话把 MAX_FILES 调大再跑。这次不发送任何请求。`
    );
    process.exitCode = 1;
    return;
  }

  const results = [];
  for (let i = 0; i < paths.length; i += 1) {
    const r = await purgeOne(paths[i]);
    results.push(r);
    console.log(`  [${i + 1}/${paths.length}] ${r.ok ? '✓' : '✗'} ${r.rel}  ${r.status}`);
    if (i < paths.length - 1) await sleep(PAUSE_MS);
  }

  const failed = results.filter((r) => !r.ok);
  console.log(`\n清了 ${results.length - failed.length}/${results.length} 个路径`);

  if (verify) {
    console.log('\n复查（Age 应当很小 / 不存在）：');
    for (const r of results.slice(0, 10)) {
      console.log(`  ${r.rel} -> ${await checkOne(r.rel)}`);
    }
  }

  // GitHub Actions 会把写进这个文件的内容显示在 run 页面上
  const summaryFile = process.env.GITHUB_STEP_SUMMARY;
  if (summaryFile) {
    const lines = [
      `## CDN 缓存清理`,
      '',
      `仓库 \`${REPO}@${BRANCH}\` · 共 **${results.length}** 个路径`,
      '',
      failed.length
        ? `⚠ ${failed.length} 个没清成功：\n${failed.map((f) => `- \`${f.rel}\` → ${f.status}`).join('\n')}`
        : '✅ 全部成功，线上应该几分钟内就更新了。',
    ];
    fs.appendFileSync(summaryFile, `${lines.join('\n')}\n`);
  }

  // 故意不用非零退出：清缓存失败不该让 CI 变红，写进 summary 里看得见就够了
  if (failed.length) console.log(`\n⚠ ${failed.length} 个没成功（不影响 CI）：`);
  failed.forEach((f) => console.log(`  ${f.rel} -> ${f.status}`));
}

main();
