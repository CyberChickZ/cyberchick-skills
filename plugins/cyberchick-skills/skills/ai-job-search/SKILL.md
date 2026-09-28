---
name: ai-job-search
description: 全自动求职流水线——每天从 80+ 家公司的 ATS 接口拉新岗并预筛 JD、按方向选简历、派 sonnet 子代理填表投递、清邮箱更新状态、刷新进度看板。用户说“投简历 / 找岗 / 继续申请 / jobright / 看看邮件 / 更新进度”时用。
---

# ai-job-search

个人资料和设定都在**本机数据目录**，不在这个插件里：

```
DATA = ~/.claude/cyberchick-skills/ai-job-search/   （设置了 CLAUDE_CONFIG_DIR 就在它下面；AI_JOB_SEARCH_DATA 可覆盖）
SCRIPTS = ${CLAUDE_PLUGIN_ROOT}/skills/ai-job-search/scripts
```

第一次用：`DATA/profile.md` 不存在 → 跑 `python3 SCRIPTS/init_data.py` 生成模板，让用户填好 `profile.md`、`local.md`、`config.json` 再继续。

授权范围、看板链接、简历怎么选、方向优先级，**以 `DATA/local.md` 为准**。只有硬停项（见 `DATA/profile.md` 末尾）和外发邮件一定要停下来。

## 文件地图（先读对应的，别凭记忆）

| 文件 | 管什么 | 什么时候读 |
|---|---|---|
| `DATA/local.md` | 个人设定：授权、看板链接、简历选择、方向优先级 | **每次开始时** |
| `DATA/profile.md` | 答案库：联系方式、地址、学历、签证答法、常见题、pitch、硬停 | **每次派填表子代理前** |
| `DATA/quotas.md` | 各公司投递上限 / 冷却 / 稀缺名额 | 选岗时 |
| `DATA/ats_playbook.md` | 各 ATS 填表技巧和坑（Greenhouse/Ashby/Workday/iCIMS/Apple…） | 子代理开工前必读 |
| `DATA/watchlist.json` | 目标公司 + 已验证的 ATS slug | 加公司时 |
| `DATA/config.json` | 路径（jobdir、简历仓库、简历输出名、简历变体）+ **`filters` 筛岗偏好**：跳过的公司、直接排除的 flag、毕业年份、地点、Amazon 搜索词、方向排序 | 路径不对、筛岗结果不对时 |
| `SCRIPTS/source_jobs.py` | 拉岗（watchlist 里的 Greenhouse/Ashby/Lever + **Amazon search.json**）+ 预筛 JD + 去重 → `<jobdir>/queue_YYYYMMDD.md/.json` | 每天第一步 |
| `SCRIPTS/build_resume.sh` | 编译简历 → config.json 的 `resume_out`，查页数/丢字/编译错误 | 改完 tex 后 |
| `SCRIPTS/render_site.py` + `site_template.html` | CSV → 看板 HTML | 每批投完 |

数据：
- **`<jobdir>/applications.csv` = 唯一事实来源**。列：`id,applied_date,company,role,location,track,ats,link,status,resume,notes,last_update`；status ∈ submitted / rejected / interview / offer / skipped / blocked / queued / withdrawn；track ∈ SDE / FDE / Robotics / MLE / Research / Other。
- 看板：`render_site.py` 生成 `<jobdir>/site/index.html`，用 Artifact 工具 publish；链接见 `DATA/local.md`，带 `url` 参数更新同一个链接。

## 每日流程

1. **邮箱**（Gmail MCP，`search_threads(query="in:inbox newer_than:2d")`）
   - 拒信 / 面试 / OA / take-home → 改 CSV 对应行的 status + last_update + notes，**在回复里高亮**，需要用户本人行动的放最前
   - 投递确认 → 归档（`unlabel_thread` 去掉 INBOX、UNREAD），只报数量
   - 营销 → `trash_thread`
   - 银行 / 学校 / 签证 / 个人 → 不动，提一句
2. **找岗**：`python3 SCRIPTS/source_jobs.py --days 3`（首次或隔久了用 `--days 14`）。输出三档：✅ 可直投 / ⚠️ 写了 3+ 年要看 JD / ⛔ 已排除。再补 **JobRight**（两边互补，实测重合很少）：在已登录的 `jobright.ai/jobs/recommend` 页面里用 javascript_tool 调它的内部接口 `fetch('/swan/recommend/list/jobs?refresh=false&sortCondition=0&position=<0,20,40…>&count=20&syncRerank=false')` 翻页拿全量（页面是虚拟列表，别滚动抓 DOM）。每条的 `jobResult` 有 jobTitle / jobSeniority / employmentType / isCitizenOnly / isClearanceRequired / originalUrl；`companyResult.companyName`。只留 jobSeniority 含 Intern/New Grad/Entry 的（它 60% 是 Mid Level）。**它的 publishTime 是重新抓取时间，不是真实发布日期；H1B 标记是公司级估计，全都是 true，没区分度。** originalUrl 里出现新的 greenhouse/ashby/lever slug → `--probe` 验证后加进 `DATA/watchlist.json`。JobRight 付费 autofill 不用。结果输出不能太长（javascript_tool 返回约 1KB 就截断）→ 在页面里算好再分批取。
   用户丢过来的链接照常处理。
3. **选一批 4–5 个**：按 `DATA/local.md` 的方向优先级；查 `DATA/quotas.md`；稀缺名额只列给用户选。
4. **派填表子代理**（`model: "sonnet"`，一次只一个，浏览器串行）——用下面的模板，**引用文件，不要把规则抄进 prompt**。
5. 子代理回来 → 核对它写进 CSV 的行 → `render_site.py` → 重新 publish 看板。
6. **汇报**：表格（公司/岗位/状态/卡点）+「要你做的」+ 看板链接。

### 子代理 prompt 模板
```
你是填表子代理。开工前读：
- DATA/profile.md（答案库+硬停，照实答）
- DATA/ats_playbook.md（按 ATS 找对应小节）
（DATA 换成实际路径）
队列：<4–5 行：公司 | 岗位 | 链接 | 用哪版简历>
规则：先读 JD，写明不给 sponsorship / 要公民或 clearance / 要 PhD → 跳过记原因。单岗卡 3 次就标 blocked 换下一个。只有看到确认页才算 submitted。每投完一个立刻追加/更新 <jobdir>/applications.csv（csv 模块写，别手拼逗号）。遇到硬停项 → tabs_create_mcp 开独立 tab 停在那步不关，汇报里写 tab 标题。
学到新坑 → 修好后把解法追加进 DATA/ats_playbook.md 对应小节（带日期+公司）。
汇报：每岗一行 公司 | 岗位 | 状态 | 原因。
```

## 简历

- 选哪版：按 `DATA/local.md` 的「简历怎么选」表。变体名对应 `DATA/config.json` 的 `resume_variants`（`"变体": "tex 文件名（不含 .tex）:输出后缀"`）。
- 编译：`SCRIPTS/build_resume.sh <变体>`；为某个岗定制：复制最接近的 tex 为 `YYMMDD_<company>.tex` → 改 → `build_resume.sh YYMMDD_<company>.tex <Suffix>`。
- `build_resume.sh` 开了 halt-on-error：有编译错误就不出 PDF。**别绕过**——以前有过简历带着一行乱码被投了十几次，就是因为错误被吞了。
- 中文进 LaTeX 会静默丢字（脚本会报 Missing character）；中文名用拼音。
- Skills 栏 ≤3 行、每行 ≤8 项，只留敢被追问三层的。
- 简历仓库是 git 仓库的话，改完 tex 就 commit。

## 硬规则
- **诚实**：签证照 profile.md 答；不编经历、学历、技能；自由文本只用简历里有的事实和数字。
- **确认页才算投了**。404 不等于失败（去候选人 dashboard 核实）。
- **外发邮件**：先给用户一行大纲（给谁 / 说啥 / 要啥）→ 他点头 → 再发正式版。
- **需要用户本人操作的页面**（SSO 账号选择、Apple ID、验证码、短信）：开独立 tab 停住，不在同一 tab 继续跳走。
- **子代理用 sonnet**；浏览器同一时刻只有一个代理。
- 一批 4–5 个。批次太大子代理会在“评估规模”上耗光预算、一个都不投。

## 自我维护
所有会变的东西都写进 `DATA/`，不要改插件目录里的文件（插件更新会覆盖）：
- 用户给了新事实（地址、学历更正、某题怎么答）→ **当轮**改 `DATA/profile.md`。
- 撞到新配额 / 冷却 → **当轮**改 `DATA/quotas.md`，并把公司加进 `DATA/config.json` 的 `filters.skip`（写原因和到期日），到期后删掉。
- 筛岗偏好变了（地点、排除条件、毕业年份…）→ 改 `DATA/config.json` 的 `filters`，不要改脚本。
- 修好一个填表坑 → **当轮**写进 `DATA/ats_playbook.md`。
- 加目标公司 → `source_jobs.py --probe <ats>:<slug>` 验证通过再进 `DATA/watchlist.json`（Ashby 要 UA 头、不能并发，脚本已处理）。
- 子代理 prompt 里出现了第二次抄同一条规则 → 那条规则该进文件了。
- 想把通用的 ATS 经验分享出去：去掉个人信息后，同步到插件仓库里的 `ats_playbook.md`。
