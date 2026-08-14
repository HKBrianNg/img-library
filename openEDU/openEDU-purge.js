// openEDU-purge.js
const https = require('https');

const GITHUB_USER = 'HKBrianNg';
const REPO = 'img-library';
const BRANCH = 'main';

const COURSE_FILES = {
  '1': [
    'course-1/atthedoor.json',
    'course-1/balcony.json',
    'course-1/bedroom.json',
    'course-1/diningroom.json',
    'course-1/kiddiespeak.json',
    'course-1/kitchen.json',
    'course-1/livingroom.json',
    'course-1/playarea.json',
    'course-1/readingcorner.json',
    'course-1/course-1.json',
  ],
  '2': [
    'course-2/ch1-english-children-songs.json',
    'course-2/ch2-chinese-children-songs.json',
    'course-2/ch3-english-pop-music.json',
    'course-2/ch4-chinese-pop-music.json',
    'course-2/course-2.json',
  ],
  '3': [
    'course-3/ch1-human-body.json',
    'course-3/course-3.json'
  ]
};

const args = process.argv.slice(2);
let filesToPurge = [];

function printHelp() {
  console.log(`
📖 用法：
  node openEDU-purge.js all                      清理所有课程
  node openEDU-purge.js --course <编号>          清理指定课程（如 --course 1）
  node openEDU-purge.js                          显示本帮助信息

📂 当前支持的课程编号：
${Object.keys(COURSE_FILES).map(id => `  course-${id}`).join('\n')}
  `);
}

if (args.length === 0) {
  printHelp();
  process.exit(0);
}

if (args[0] === 'all') {
  for (const courseId of Object.keys(COURSE_FILES)) {
    filesToPurge = filesToPurge.concat(COURSE_FILES[courseId]);
  }
  console.log(`🔍 清理所有课程，共 ${filesToPurge.length} 个文件`);
} else if (args[0] === '--course' && args[1]) {
  const courseId = args[1];
  if (COURSE_FILES[courseId]) {
    filesToPurge = COURSE_FILES[courseId];
    console.log(`🔍 选定课程 course-${courseId}，共 ${filesToPurge.length} 个文件`);
  } else {
    console.error(`❌ 未找到课程 course-${courseId}。`);
    printHelp();
    process.exit(1);
  }
} else {
  printHelp();
  process.exit(1);
}

function purgeFile(filePath) {
  return new Promise((resolve, reject) => {
    const fullPath = `openEDU/${filePath}`;
    const url = `https://purge.jsdelivr.net/gh/${GITHUB_USER}/${REPO}@${BRANCH}/${fullPath}`;
    
    https.get(url, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        console.log(`\n✅ [${res.statusCode}] ${fullPath}`);
        console.log('📄 原始响应:');
        console.log(body);
        resolve({ file: fullPath, status: res.statusCode, raw: body });
      });
    }).on('error', (err) => {
      console.error(`❌ [ERROR] ${fullPath} - ${err.message}`);
      reject(err);
    });
  });
}

(async () => {
  if (filesToPurge.length === 0) {
    console.log('⚠️ 没有需要清理的文件。');
    process.exit(0);
  }

  console.log(`🚀 开始清理 CDN 缓存...\n`);

  const results = await Promise.allSettled(filesToPurge.map(purgeFile));

  console.log('\n📊 清理结果汇总：');
  const successCount = results.filter(r => r.status === 'fulfilled').length;
  const failCount = results.filter(r => r.status === 'rejected').length;
  
  console.log(`✅ 成功: ${successCount}  |  ❌ 失败: ${failCount}`);
  console.log('🎉 清理完成！');
})();