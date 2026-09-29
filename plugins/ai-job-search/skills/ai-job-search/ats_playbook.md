# ATS 填表手册

> 工具名按 Claude Code 的浏览器扩展（Claude in Chrome）写，例如 `read_page`、`form_input`、`javascript_tool`；其他宿主换成对应的浏览器工具。
> **更新规则**：新经验并入对应章节，能改写或替换旧条目就不要新增；不新建章节；每条写「做法 — 原因（公司 月-日）」；改完跑 `python3 SCRIPTS/lint_data.py`，不通过就合并精简。作答口径写进 profile.md，不写在这里。

## 1. 通用流程

- **加载工具一次**（含 `browser_batch`）；只用一个 tab，同一时刻只有一个代理在操作浏览器。`javascript_tool` 要传 `action: "javascript_exec"`；输出里带 query 的 URL 会被替换成 `[BLOCKED: …]`，别打印带参数的链接。
- **先探通道**：`javascript_tool` 跑 `JSON.stringify({nInput:document.querySelectorAll('input').length,nIframe:document.querySelectorAll('iframe').length})`。`nInput>0` = 同源，用 JS 批量填（快 10 倍）；`nInput==0 && nIframe>0` = 跨域 iframe，JS 和 `read_page` 都进不去，只能按截图坐标点；不要把 iframe 的 src 单独打开（会话绑在原 tab 上）。
- **扫一次、规划、批量填**：`read_page filter:"all"` 一次拿全表的 ref、标签、必填和选项 → 一次性规划每个字段的值 → `browser_batch` 批量执行 → 截图一次核对 → 提交 → 截图确认成功页。每份申请目标 3–5 次工具调用，不要「做一步截一张图」。
- **页面重排后 ref 和坐标全部失效**（错误 banner 消失、上传完成都会位移）：重排后重新 `find`，用 ref 点；不要在一个 batch 里连点多个不同字段组。
- **看到确认页才算提交成功**；提交后跳到 404 不等于失败，去候选人 dashboard 核实（iCIMS GitHub 08-18）。
- **出错不要 `location.reload()`**：会丢会话、可能被迫重新登录（Workday 08-18）；重试失败的那一步。
- **单个岗位卡 3 次就标 blocked 换下一个**；公司主动拒收（「近期已投过本公司」）不是填表失败，记进 quotas.md（Sierra、Cognition）。
- **截图报「Permission denied for this action on this domain」**：是扩展没有该域名权限，不是网站拦截；请 用户 在扩展里授权该域名，或请他截图，按 `扩展截图宽 / 用户截图宽` 比例换算坐标（先点一次验证再批量）。

## 2. 表单技巧

### 2.1 文本输入
- **React 受控组件用 JS 赋 `value` 不生效**（DOM 有值，提交报 required）：`el.focus(); el.setSelectionRange(0, el.value.length); document.execCommand('insertText', false, txt)`，或 `triple_click` 后真键盘 `type`。
- **`type=email` / `tel` / `number` 不支持 `setSelectionRange`**，退回 `selectAll` 会选中整页、字才丢；这类字段一律真键盘输入（Ashby 08-18）。
- **已有值的字段先跳过**（`if(el.value) return;`），免得覆盖自动填好的内容。
- **同一字段 JS 填两次都报错**就停止重试 JS，改用 `find` → `triple_click` → `type`。
- **单页表单的文本框里不要按回车**：iCIMS 会整表提交、清空字段；回车只用来确认下拉选项。
- **字符白名单**：Workday Role Description 拒收 `< > [ ] " { } \`；SmartRecruiters 拒收 `>`（改用 `→`）；部分字段 200 字上限、提交前不提示。

### 2.2 下拉、单选、日期
- **三类下拉三种做法**：原生 `<select>`（iCIMS）→ 点开后输入首字母再回车；带搜索的 listbox（Workday、iCIMS 国家州）→ 点开、输入全名、点那一行，不按回车；react-select / combobox（Greenhouse、Ashby）→ 点开、输入、回车。选完截图确认显示的是值而不是 placeholder。
- **`form_input` 对 react-select 无效**：必须 `left_click` → `type` → `key Return`，截图看到带 × 的值才算。
- **单选按题目文字匹配，不按序号**：工作授权、公民身份、export-control 这类题必须照实答。
- **看不到选项的原生 select**（iCIMS EEO，选项由系统渲染、截图拍不到）：`key Down` → 截图 → 重复，逐个枚举；身份类字段不要靠方向键猜。
- **日期选择器不是文本框**：输入 `MM/DD/YYYY` 后必须点弹出日历里的那一天才算（Ashby 08-18）；Workday 分段日期 `triple_click` 月份格一次输入 `MMYYYY`。
- **毕业日期下拉里没有真实月份**：见 profile.md「其它常见题」的作答口径。

### 2.3 文件上传
- **一律用 `file_upload` 传给 `<input type=file>` 的 ref，不要点「Choose file」**（会弹出无法操控的系统对话框）。
- **input 被隐藏、不在 a11y 树里**：先用 JS 确认它存在，再临时显形：`el.style.cssText='position:fixed;top:120px;left:120px;width:280px;height:44px;opacity:1;z-index:2147483647'; el.setAttribute('aria-label','FILEINPUT')` → `read_page` 拿到 ref → `file_upload` → 还原样式（TRI、Lever）。
- **input 在 shadow DOM 里**（SmartRecruiters `<spl-dropzone>`）：见 4.SmartRecruiters。
- **页面用 `showOpenFilePicker`、DOM 里没有 file input**（Google Careers）：先建一个隐藏 input 并 `file_upload` 进去，再把 `window.showOpenFilePicker` 替换成返回该文件句柄的函数，然后触发网站的上传；注入不及时就请 用户 点那一下。
- **`file_upload` 会吞掉紧接着的下一次点击**：上传单独一个 batch，之后重新 `find`。
- **上传简历常会触发重渲染、清空已填字段**：先上传，再填其他字段，最后截图核对（Ashby 多家复现）。

### 2.4 校验和报错
- **不截图读错误**：`JSON.stringify([...new Set([...document.querySelectorAll('*')].filter(e=>e.children.length===0&&/^Error|required|illegal/i.test(e.textContent||'')).map(e=>e.textContent.trim().slice(0,80)))])`；再检查步骤指示确认真的翻页了。
- **点提交后停在原地、没有可见报错** = 视口外还有漏填的必填项：滚回顶部逐段查红色提示（Greenhouse Location、Ashby 大表单）。
- Greenhouse 的错误在 `[aria-invalid="true"]` / `.error` 里，不一定有顶部 banner；同公司不同岗位的必填项可能不同。

### 2.5 简历自动解析和旧资料
- **自动解析的结果必须逐项审计**：Workday 08-18 生成了 11 个空的工作经历块、把项目名塞进公司栏、把公司名塞进职位栏、毕业年填成入学年。多余的块从最后一个开始删、每删一次重新查询。
- **重点核对地址和毕业年份**：门户会带出旧 profile 的旧地址和旧简历（Workday、Amazon、ZipRecruiter）；提交前在 Review 页改成当前的。

## 3. 账号、登录、验证码

- **先看是否已登录**：导航栏有 My Jobs / Profile / Sign out 就是已登录，不要按旧记录直接走注册（ZipRecruiter 09-28）。
- **登录顺序**：已有账号 / Chrome 保存的 passkey 或密码 → 「Sign in with Google」。
- **点 Google SSO 前看授权页**：写「You're signing back in to X」= 已有账号，可以继续；出现账号选择器或 URL 带 `prompt=consent` = 首次授权，会新建一个空账号、藏掉真实申请记录，退回来改用原账号登录（Amazon）。
- **注册账号、设密码**：按 local.md 的授权处理，密码记进 applications.csv 对应行的 notes；做不成的记进 needs_signup.md，接着投下一个。
- **邮箱验证码 / 验证链接**：自己用 Gmail 连接器取（按公司名 + `newer_than:1d` 搜），只用本次自己触发的那封，不点邮件里其他链接。
- **reCAPTCHA / hCaptcha**：除验证码外全部填完，tab 留着交给 用户（McKinsey、Susquehanna）。
- **身份验证要上传证件 + 摄像头自拍**：其余填完，tab 停在该步交给 用户（Amazon 09-28）。
- **长时间挂着的注册页会过期**（「Your session has expired」）：复用前先检查，过期就重新进入（McKinsey 09-28）。

## 4. 各 ATS 系统

### Greenhouse
- **公司官网内嵌的跨域 iframe 读不到字段**：直接打开 `https://job-boards.greenhouse.io/embed/job_app?for=<board>&token=<jobid>`，同源可填；先试 embed，embed 也 404 / 空白才判 blocked（Stripe 09-28、Samsara、Together、Scale）。
- **同公司不同岗位的字段顺序不一样**：先枚举再按标签匹配（`label[for]` 或向上找 label），绝不按序号填（Anthropic）。
- **Country / Location / Degree / Yes-No 都是 combobox**：`left_click` → `type` → 等下拉 → 点那一行 → 截图；不要 JS 赋值（Klaviyo 09-23）。被 JS 写坏的 combobox：点开、`cmd+a`、Delete，再从列表选。
- **Location (City) 用 JS 插入会丢**：清空后真键盘输入，并点选下拉里的建议项（Snorkel AI 09-28）。
- **Education 用 HTML5 datalist**（c3.ai embed）：真键盘输入触发建议列表后按 Tab 离开才算「从建议中选择」；Degree 用它的原词，如「Master's Degree」（C3 AI 09-27）。

### Ashby
- **表单是 React 受控**：用下面的 helper 按标签填长文本，短字段和 email 用真键盘。
  ```js
  const put=(el,t)=>{el.focus();try{el.setSelectionRange(0,(el.value||'').length)}catch(e){};document.execCommand('insertText',false,t)};
  const poke=x=>{x.focus();const l=(x.value||'').length;x.setSelectionRange(l,l);document.execCommand('insertText',false,'.');document.execCommand('delete');x.dispatchEvent(new Event('change',{bubbles:true}));x.blur()};
  ```
- **顺序**：先上传简历 → 再填文本 → 提交前对所有 JS 填过的字段跑一遍 `poke`，否则会报「Missing entry for required field」（Zyphra、Kovari、Luma）。
- **Name / Email 的第一次键盘输入常常没进去**：输入后读回 `value`，最多试两次。
- **radio / checkbox 用 JS 点无效**：用 `left_click` 点选项的文字（不是圆圈）；被 JS 写乱的先点另一个选项再点正确的；每点一次重新定位（Notion 08-19）。
- **Location、School 是 combobox**：输入后等约 2 秒，点下拉里的第一项；Yes/No 是按钮对，点文字。
- **月 / 年的原生 `<select>`** 反而可以直接 `s.value=...` 加 `change` 事件。
- **「Still Student?」不要勾**：会清空并禁用 End Date。
- 有一个和第一个文本框同名的隐藏 textarea：按标签 + 元素类型双重匹配，否则名字会被追加进 GitHub URL 栏。

### Lever
- 表单简单；简历上传后不会自动填 name / email / location，要手动填。
- Location 是自由文本 + 自动补全：清空后输入城市名，从下拉里选（Palantir 09-27）。

### Workday
- **「Use My Last Application」预填后逐块审计**：空的工作经历块、项目名进公司栏、旧地址（NVIDIA 09-27）。
- **改完 My Information 要把后面每一步都 Save and Continue 一遍**才会在 Review 页生效；面包屑上的步骤名点了不跳转，用每页的 Back 逐级回退。
- **Voluntary Disclosures 的下拉**：点开 → 按首字母（d）→ 回车，比滚动列表快。
- 分段日期、字符白名单、listbox 做法见 2.1、2.2。

### iCIMS
- 常在跨域 iframe 里：只能按截图坐标点（见 1. 先探通道）。
- 候选人 dashboard 在 `/jobs/dashboard`（`/dashboard` 会 404）。
- 部分门户要建账号 + hCaptcha（见 3.）。

### SmartRecruiters
- **简历 input 在 `<spl-dropzone>` 的 shadowRoot 里**：`const inp=dz.shadowRoot.querySelector('input[type=file]'); document.body.appendChild(inp)` → 显形、`file_upload` → 放回 shadowRoot。监听器绑在元素上，搬动后照样生效；派发 `change` 时加 `composed:true`（Neurable 08-18）。
- 自动解析结果同样要审计（见 2.5）。

### 其他
- **Recruitee**（1X）：可能要求填 cover letter 文本，用 pitch。
- **ZipRecruiter Quick Apply**：多步弹窗（问答 → EEO → Review）；Review 页会带出旧简历和旧地址，点 Edit 换掉；提交后到 `/candidate/my-jobs` 的 Applied 页看到「Applied Today」才算（09-28）。

## 5. 公司特例

- **Amazon**：自有账号系统，右上角 My career 有 Sign out 即已登录；每个岗位都要重新勾工作授权、赞助、政府雇员几题；简历会沿用上一次上传的文件，去 Resume 步骤核对，不对就 Replace；Apply now 偶尔要点两次；ADC / TS-SCI 岗要美国公民身份，直接跳过记原因（09-27）。
- **Amazon 10 个 active 申请上限**：超限时 Apply 会跳到 `result=application_limit_reach`。腾位只撤两类：(a) 页面显示已停收、投递超过 30 天的旧申请；(b) CSV 已标 rejected 但网站仍显示 active 的（09-28）。
- **Apple**：要 Apple ID 登录，之后 4 步（Info → Resume → Questions → Review）；简历解析可能把实习单位塞进 Education，删掉；Profile 里可能是旧简历，提交前换掉。
- **Ford**：无密码注册，邮箱验证码两轮，第一轮常过期。
- **HPE / Cisco**：上传简历后页面卡死，是 ATS 故障（09-24 两次），隔几天再试。
- **McKinsey**：注册页字段都能填，最后有 reCAPTCHA，见 3.。
- **Palantir（Lever）**：末尾有「Delta vs. Dev」、行为题、「three numbers that describe you」等，要真实撰写；EEO 的 Disability Self-ID 下方还有签名和日期两个文本框，容易漏。
- **Ramp（Ashby）**：Builder's quiz 是外部网站，要真实作答，把结果（如「Money Architect」）填回申请表，不能编。
- **Robinhood（Greenhouse）**：利益冲突 / 政府官员题都是 Yes/No 加条件追问，答 No 不用展开。
- **Stripe / Pinterest**：站内 Apply 不通，用 Greenhouse embed URL（见 4. Greenhouse）。
