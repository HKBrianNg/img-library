// 给课程配图生成缩略图。
//
// 为什么需要：原图普遍 1024px 宽（最大的 3061px），而前端卡片只显示 148px 高。
// 一个章节几百张原图 = 十几 MB，加载慢还经常超时。缩到长边 480px 后体积只有原来的三成左右。
//
// 注意：仓库里 1130 个 .jpg 里有 1062 个实际内容是 WebP、67 个是真 JPEG、1 个是 PNG
// （扩展名不可信），所以用 sharp 按内容解码，不要改用只认扩展名的工具。
// 输出统一用 WebP 编码，扩展名沿用 .jpg —— 跟现有原图一致，前端路径不用改。
//
// 用法（在仓库根目录）：
//   node scripts/gen-thumbs.mjs                          # 默认 EnglishWord / 480 / 80
//   node scripts/gen-thumbs.mjs EnglishWord 480 80
//
// 幂等：目标已存在且不比源旧就跳过，重跑只处理新增或改过的图。

import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const args = process.argv.slice(2);
const force = args.includes('--force') || args.includes('-f');
// 缩略图不是「变小变糊」：原图动辄 3000px，浏览器运行时降采样用的是快速算法，
// 糊成一团；这里用 sharp 的 Lanczos 重采样，显示反而更清楚。
//
// 额外锐化默认关：试过 sigma 0.6，高频细节一多 WebP 就压不动 —— 972/1130 张
// 缩完反而比原图大、被退回原图，等于白跑，总量还从 9.12MB 涨到 9.66MB。
// 想开就加 --sharpen。
const doSharpen = args.includes('--sharpen');
const positional = args.filter((a) => !a.startsWith('-'));
const course = positional[0] || 'EnglishWord';
// 400px 是卡片实际需要的两倍（卡片约 200px 宽，2x 屏刚好不糊）；
// 再往下降到 320px 能多省 1.4MB，但高分屏上配图开始发虚。
const longEdge = Number(positional[1] || 400);
const quality = Number(positional[2] || 72);

const srcDir = path.join(process.cwd(), 'openEDU', course, 'content');
if (!fs.existsSync(srcDir)) {
  console.error(`找不到目录: ${srcDir}`);
  process.exit(1);
}
const dstDir = path.join(srcDir, 'thumb');
fs.mkdirSync(dstDir, { recursive: true });

const files = fs.readdirSync(srcDir).filter((f) => f.toLowerCase().endsWith('.jpg'));
const srcTotal = files.reduce((a, f) => a + fs.statSync(path.join(srcDir, f)).size, 0);

console.log(`课程  : ${course}`);
console.log(`原图  : ${files.length} 张，${(srcTotal / 1024 / 1024).toFixed(2)} MB`);
console.log(
  `输出  : ${path.relative(process.cwd(), dstDir)}（长边 ${longEdge}px，WebP 质量 ${quality}，锐化 ${doSharpen ? '开' : '关'}）`
);
console.log('');

let generated = 0;
let copied = 0; // 缩略后反而更大，直接沿用原图的
let skipped = 0;
const failed = [];

// 分批并发，sharp 自己会开线程池，这里只是别一次塞太多文件句柄
const CONCURRENCY = 8;
for (let i = 0; i < files.length; i += CONCURRENCY) {
  const batch = files.slice(i, i + CONCURRENCY);
  await Promise.all(
    batch.map(async (f) => {
      const src = path.join(srcDir, f);
      const out = path.join(dstDir, f);

      // 已生成过、且原图没再改过 —— 跳过（--force 时全部重来）
      if (!force && fs.existsSync(out)) {
        const a = fs.statSync(out).mtimeMs;
        const b = fs.statSync(src).mtimeMs;
        if (a >= b) {
          skipped++;
          return;
        }
      }

      try {
        const srcSize = fs.statSync(src).size;
        const pipeline = sharp(src)
          .rotate() // 按 EXIF 摆正，否则竖拍的图会躺下
          .resize({ width: longEdge, height: longEdge, fit: 'inside', withoutEnlargement: true })
        if (doSharpen) {
          pipeline.sharpen({ sigma: 0.6 }) // 轻微即可，重了会出现白边
        }
        await pipeline.webp({ quality }).toFile(out);
        generated++;

        // 仓库里大部分图已经是 200~400px 的小 WebP（平均 8KB），重新编码反而更大。
        // 这种直接沿用原图 —— 顺带保证 thumb/ 里每个名字都有文件，
        // 前端不用先 404 一次再回退（那会让请求数翻倍）。
        if (fs.statSync(out).size >= srcSize) {
          fs.copyFileSync(src, out);
          copied++;
          generated--;
        }
      } catch (e) {
        failed.push(`${f} —— ${e.message}`);
      }
    })
  );
  if ((i / CONCURRENCY) % 20 === 0) {
    console.log(`  已处理 ${Math.min(i + CONCURRENCY, files.length)} / ${files.length} ...`);
  }
}

const dstTotal = fs
  .readdirSync(dstDir)
  .reduce((a, f) => a + fs.statSync(path.join(dstDir, f)).size, 0);

console.log('');
console.log('=== 完成 ===');
console.log(
  `  真缩略: ${generated}   沿用原图(缩了反而更大): ${copied}   跳过(已存在): ${skipped}   失败: ${failed.length}`
);
if (failed.length) {
  console.log('  失败明细（前 10 条）:');
  failed.slice(0, 10).forEach((x) => console.log(`    ${x}`));
}
console.log(`  缩略图总大小: ${(dstTotal / 1024 / 1024).toFixed(2)} MB`);
console.log(`  占原图比例  : ${((100 * dstTotal) / srcTotal).toFixed(1)}%`);
