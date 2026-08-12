const express = require('express');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const multer = require('multer');
const simpleGit = require('simple-git');
const { exec } = require('child_process');
const util = require('util');

const execAsync = util.promisify(exec);
const app = express();
const PORT = 3001;

// 仓库根目录（IMG-LIBRARY）
const repoRoot = path.join(__dirname, '..');
// openEDU 目录
const openeduDir = path.join(repoRoot, 'openEDU');
// Git 实例
const git = simpleGit(repoRoot);

// 中间件
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// 课程目录映射
const COURSE_DIRS = {
  'course-1': path.join(openeduDir, 'course-1'),
  'course-2': path.join(openeduDir, 'course-2'),
  'course-3': path.join(openeduDir, 'course-3'),
};

// Multer 配置：上传到对应课程目录
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const course = req.body.course || 'course-2';
    const subfolder = req.body.subfolder || '';
    let uploadDir = COURSE_DIRS[course];
    if (subfolder) uploadDir = path.join(uploadDir, subfolder);
    fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    cb(null, file.originalname);
  }
});
const upload = multer({ storage });

// ---- API 路由 ----

// 1. 列出课程下的 JSON 文件
app.get('/api/files', (req, res) => {
  const course = req.query.dir || 'course-2';
  const dir = COURSE_DIRS[course];
  if (!dir) return res.status(400).json({ error: 'Invalid course' });

  try {
    const files = fs.readdirSync(dir)
      .filter(f => f.endsWith('.json'))
      .map(f => ({
        name: f,
        path: `openEDU/${course}/${f}`,
        mtime: fs.statSync(path.join(dir, f)).mtime
      }));
    res.json(files);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// 2. 读取文件内容
app.get('/api/read', (req, res) => {
  const relativePath = req.query.path;
  if (!relativePath || relativePath.includes('..')) return res.status(403).send('Forbidden');

  const filePath = path.join(repoRoot, relativePath);
  if (!fs.existsSync(filePath)) return res.status(404).send('File not found');

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    res.send(content);
  } catch (e) {
    res.status(500).send(e.message);
  }
});

// 3. 保存文件并自动提交推送
app.post('/api/save', async (req, res) => {
  const { path: relativePath, content } = req.body;
  if (!relativePath || content === undefined) return res.status(400).send('Missing data');
  if (relativePath.includes('..')) return res.status(403).send('Forbidden');

  const filePath = path.join(repoRoot, relativePath);
  try {
    fs.writeFileSync(filePath, content, 'utf8');

    await git.add(relativePath);
    const status = await git.status();
    if (status.staged.length === 0) {
      return res.json({ message: 'No changes detected.' });
    }
    await git.commit(`Admin: Update ${relativePath}`);
    await git.push('origin', 'main');
    res.json({ message: `Saved and pushed: ${relativePath}` });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// 4. 上传文件（音频/图片）
app.post('/api/upload', upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).send('No file uploaded');

  const course = req.body.course || 'course-2';
  const subfolder = req.body.subfolder || '';
  const relativePath = `openEDU/${course}/${subfolder ? subfolder + '/' : ''}${req.file.originalname}`;

  try {
    await git.add(relativePath);
    await git.commit(`Admin: Upload ${relativePath}`);
    await git.push('origin', 'main');
    res.json({ message: `Uploaded and pushed: ${relativePath}` });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// 5. 清理 CDN 缓存（只清理当前选中的课程）
app.post('/api/purge', async (req, res) => {
  const { course } = req.body; // 如 "course-2"
  let arg = 'all';
  if (course && course.startsWith('course-')) {
    const courseNum = course.split('-')[1];
    arg = `--course ${courseNum}`;
  }

  try {
    // 工作目录设为 openEDU，因为脚本在那里
    const { stdout, stderr } = await execAsync(
      `node openEDU-purge.js ${arg}`,
      { cwd: openeduDir }
    );
    if (stderr) console.error(stderr);
    res.json({ message: `Purge completed for ${course || 'all courses'}`, output: stdout });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// 6. 获取 Git 提交历史（最近3条）
app.get('/api/history', async (req, res) => {
  try {
    const log = await git.log({ maxCount: 3 });
    res.json(log.all.map(c => ({ date: c.date, message: c.message, hash: c.hash })));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// 启动
app.listen(PORT, () => {
  console.log(`Admin panel running at http://localhost:${PORT}`);
  console.log(`Make sure you have GitHub credentials configured for push.`);
});