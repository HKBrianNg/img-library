// openEDU-check.js
// 用途：查询 CDN 上课程数据（包括元数据和所有 lesson 文件）
// 用法：
//   node openEDU-check.js --course 2       查询 course-2
//   node openEDU-check.js --course 1       查询 course-1
//   node openEDU-check.js all              查询所有课程
//   node openEDU-check.js                  显示帮助

const https = require('https');
const { execSync } = require('child_process');

// ---------- 配置区域 ----------
// 自动检测默认分支
let DEFAULT_BRANCH = 'main';
try {
  DEFAULT_BRANCH = execSync('git rev-parse --abbrev-ref HEAD').toString().trim();
} catch (e) {
  // 如果不在 git 仓库中，则使用 'main'
}

const CONFIG = {
  GITHUB_USER: 'HKBrianNg',
  REPO: 'img-library',
  BRANCH: DEFAULT_BRANCH,
  BASE_PATH: 'openEDU'
};

// 课程文件映射（课程ID -> 文件路径列表）
// 注意：这里的文件路径是相对于 openEDU/ 的，且包含所有需要查询的 JSON 文件
const COURSE_FILES = {
  '1': [
    'course-1/course-1.json',
    'course-1/atthedoor.json',
    'course-1/balcony.json',
    'course-1/bedroom.json',
    'course-1/diningroom.json',
    'course-1/kiddiespeak.json',
    'course-1/kitchen.json',
    'course-1/livingroom.json',
    'course-1/playarea.json',
    'course-1/readingcorner.json',
  ],
  '2': [
    'course-2/course-2.json',
    'course-2/ch1-english-children-songs.json',
    'course-2/ch2-chinese-children-songs.json',
    'course-2/ch3-english-pop-music.json',
    'course-2/ch4-chinese-pop-music.json',
  ],
};
// -----------------------------

// 解析命令行参数
const args = process.argv.slice(2);
let targetCourses = [];

function printHelp() {
  console.log(`
📖 用法：
  node openEDU-check.js all                      查询所有课程（含所有文件）
  node openEDU-check.js --course <编号>          查询指定课程
  node openEDU-check.js                          显示本帮助信息

📂 当前支持的课程编号：
${Object.keys(COURSE_FILES).map(id => `  course-${id}`).join('\n')}

💡 提示：脚本会自动检测当前 Git 分支（${CONFIG.BRANCH}），无需手动修改。
  `);
}

if (args.length === 0) {
  printHelp();
  process.exit(0);
}

if (args[0] === 'all') {
  targetCourses = Object.keys(COURSE_FILES);
  console.log(`🔍 查询所有课程，共 ${targetCourses.length} 门课程\n`);
} else if (args[0] === '--course' && args[1]) {
  const courseId = args[1];
  if (COURSE_FILES[courseId]) {
    targetCourses = [courseId];
    console.log(`🔍 查询课程 course-${courseId}\n`);
  } else {
    console.error(`❌ 未找到课程 course-${courseId}。`);
    printHelp();
    process.exit(1);
  }
} else {
  printHelp();
  process.exit(1);
}

/**
 * 从 CDN 获取 JSON 内容并返回解析后的数据
 */
function fetchJson(fullPath) {
  return new Promise((resolve) => {
    const url = `https://cdn.jsdelivr.net/gh/${CONFIG.GITHUB_USER}/${CONFIG.REPO}@${CONFIG.BRANCH}/${fullPath}`;
    https.get(url, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        const result = { fullPath, url, statusCode: res.statusCode, body };
        if (res.statusCode === 200) {
          try {
            result.data = JSON.parse(body);
          } catch {
            result.data = null;
          }
        }
        resolve(result);
      });
    }).on('error', (err) => {
      console.error(`❌ [ERROR] ${fullPath} - ${err.message}`);
      resolve({ fullPath, statusCode: 0, data: null, body: '' });
    });
  });
}

/**
 * 输出单个文件的摘要信息
 */
function printFileSummary(filePath, result, isMeta = false) {
  console.log(`\n📁 ${filePath}`);
  console.log(`   🌐 ${result.url}`);
  if (result.statusCode !== 200) {
    console.log(`   ❌ HTTP ${result.statusCode}`);
    return;
  }
  console.log(`   ✅ HTTP ${result.statusCode}`);

  const data = result.data;
  if (!data) {
    console.log(`   ⚠️  内容非 JSON 格式`);
    return;
  }

  // 如果是课程元数据（包含 chapters）
  if (data.chapters) {
    console.log(`   📚 课程元数据`);
    console.log(`   🆔 ID: ${data.id}`);
    console.log(`   📝 标题(zh): ${data.title?.zh || '(无)'}`);
    console.log(`   📝 标题(en): ${data.title?.en || '(无)'}`);
    console.log(`   🏷️  分类: ${data.category?.en || '(无)'}`);
    console.log(`   📂 章节数: ${data.chapters.length}`);
    data.chapters.forEach((ch, idx) => {
      console.log(`      ${idx + 1}. [${ch.id}] ${ch.title?.en || ch.title?.zh || ch.id}`);
      if (ch.lessonsFile) {
        console.log(`         └─ lessonsFile: ${ch.lessonsFile}`);
      }
    });
  } else if (Array.isArray(data)) {
    // 如果是 lesson 文件（数组）
    console.log(`   📑 Lesson 文件，共 ${data.length} 个课时`);
    data.slice(0, 3).forEach((lesson, idx) => {
      console.log(`      ${idx + 1}. [${lesson.id}] ${lesson.title || '(无标题)'}`);
      console.log(`         ├─ type: ${lesson.type}`);
      console.log(`         ├─ lessonUrl: ${lesson.lessonUrl || '(无)'}`);
      if (lesson.content) {
        const preview = lesson.content.length > 60 ? lesson.content.substring(0, 60) + '...' : lesson.content;
        console.log(`         └─ content: ${preview}`);
      }
    });
    if (data.length > 10) {
      console.log(`         ... 还有 ${data.length - 10} 个课时`);
    }
  } else {
    // 其他 JSON 对象（如 course-1 中的单个场景文件）
    console.log(`   📄 文件内容（部分字段）:`);
    const keys = Object.keys(data).slice(0, 5);
    keys.forEach(k => {
      const val = typeof data[k] === 'object' ? JSON.stringify(data[k]).substring(0, 40) : data[k];
      console.log(`      ${k}: ${val}`);
    });
  }
}

/**
 * 查询单个课程的所有文件
 */
async function checkCourse(courseId) {
  const files = COURSE_FILES[courseId];
  console.log(`\n${'='.repeat(60)}`);
  console.log(`📚 课程 course-${courseId} (共 ${files.length} 个文件)`);
  console.log(`${'='.repeat(60)}`);

  for (const file of files) {
    const fullPath = `${CONFIG.BASE_PATH}/${file}`;
    const result = await fetchJson(fullPath);
    const isMeta = file.endsWith('course-1.json') || file.endsWith('course-2.json');
    printFileSummary(file, result, isMeta);
  }
}

(async () => {
  for (const courseId of targetCourses) {
    await checkCourse(courseId);
  }
  console.log(`\n${'='.repeat(60)}`);
  console.log('🎉 查询完成！');
})();