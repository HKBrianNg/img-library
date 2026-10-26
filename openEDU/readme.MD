your-project/
├── openEDU/
│   ├── course-1/
│   │   └── ch1-xxx.json
│   ├── course-2/
│   │   └── ch2-xxx.json
│   └── course-3/
│       └── ch3-english-pop-music.json
└── openEDU-purge.js 

# 显示帮助（无参数）
node openEDU-purge.js

# 清理所有课程
node openEDU-purge.js all

# 清理指定课程
node openEDU-purge.js --course 1
node openEDU-purge.js --course 2


# 查询 course-2 的所有数据
node openEDU-check.js --course 2

# 查询 course-1 的所有数据
node openEDU-check.js --course 1

# 查询所有课程
node openEDU-check.js all

# 显示帮助
node openEDU-check.js


你现在的流程（2026-10-26 起，缓存这一步已经自动化了）：

1. 更新数据 → 本地改 openEDU/ 下的 JSON / 图片
2. 推送     → git push 到 GitHub main 分支
3. 自动清理 → .github/workflows/purge-cdn.yml 触发，
              对这次改动过的每个路径各调一次 jsDelivr purge
4. 验证（可选）→ node scripts/purge-cdn.mjs --list=changed.txt --verify
               或直接把 CDN 地址贴浏览器里看内容

新增的文件本来就没有缓存（push 完立刻可见），只有改过的文件需要清 ——
所以 workflow 只对本次 diff 里真正变动的路径发请求，不做全量扫。
手工补一次：GitHub → Actions → Purge CDN cache → Run workflow。

这套组合拳可以确保 CDN 始终提供最新数据，不再被缓存困扰。

好的，现在确认了脚本在 openEDU 目录内，管理后台的路径也调整正确，整个体系就通顺了。

当前状态总结：

数据：openEDU/course-1/、course-2/ 等

CLI 工具：openEDU/openEDU-purge.js、openEDU/openEDU-check.js

管理后台：admin/server.js → 通过 cwd: path.join(__dirname, '..', 'openEDU') 调用脚本

前端代码：client/src/CoursesData.ts → 从 CDN 加载数据

现在你可以在管理后台中：

编辑 JSON → 保存并自动推送到 GitHub

上传音频/图片 → 保存并自动推送到 GitHub

点击 Purge CDN → 清理当前课程的 CDN 缓存


┌─────────────────────────────────────────────────────────────┐
│  [数据编辑]  [添加歌曲]  ← 顶部标签切换                      │
├─────────────────────────────────────────────────────────────┤
│  当前为“添加歌曲”模式                                        │
│                                                             │
│  Step 1: 上传音频文件                                        │
│  [选择文件] [上传]  ✓ 已完成                                │
│                                                             │
│  Step 2: 上传歌词文件                                        │
│  [选择文件] [上传]  □ 待处理                                │
│                                                             │
│  Step 3: 填写歌曲信息并注册到章节                            │
│  歌曲ID: [___]  标题: [___]  章节: [下拉选择]               │
│  [注册到JSON]                                              │
│                                                             │
│  Step 4: 保存并推送到GitHub                                  │
│  [Save & Push]                                             │
│                                                             │
│  Step 5: 清理CDN缓存                                         │
│  [Purge CDN]                                               │
│                                                             │
│  Step 6: 预览                                               │
│  [输入前端URL] [打开预览]                                   │
└─────────────────────────────────────────────────────────────┘