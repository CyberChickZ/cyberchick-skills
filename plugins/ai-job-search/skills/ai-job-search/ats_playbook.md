# ATS 填表手册（browser playbook）

> 工具名按 Claude Code 的浏览器扩展（Claude in Chrome）写，例如 `read_page`、`form_input`、`javascript_tool`。在 Codex 等其他宿主上，换成对应的浏览器自动化工具，填表思路不变。

填表子代理**开工前必读**。每条都是真实踩坑换来的；遇到新坑 → 修好后把解法追加到对应 ATS 小节（写日期 + 公司），别只留在对话里。

## 09 月新增（2026-09-20 ~ 09-25）

- **邮箱验证码（用户授权后可以直接用他的邮箱，见 local.md）**：Greenhouse 提交后要 8 位 security code、Ford/Workday 注册验证码等 → 用 Gmail MCP `search_threads(query="<公司名> newer_than:1d")`，snippet 里就有码，填进去再点提交。只取**本次自己触发的**验证邮件，别点邮件里的其它链接。（Neuralink 09-27）

- **Greenhouse 跨域 iframe**：公司官网内嵌的 Greenhouse 表单读不到字段 → 直接开 `https://job-boards.greenhouse.io/embed/job_app?for=<board>&token=<jobid>`，同源可填。（Samsara/Together/Scale 验证）
- **Greenhouse Country/Location 的 react-select：绝不用 JS 赋值。** DOM 看着填了，提交必报 "Select a country"/"Please enter your location"。只能 `left_click` → `type` → 等下拉 → `Return`/点那一行 → 截图确认。（Klaviyo 09-23 为此耗掉整轮）
- **`file_upload` 会吞掉紧接着的下一次 click**：上传单独一个 batch，之后重新 `find` 取 ref。
- **页面重排后坐标全部失效**：错误 banner 消失、上传完成都会让布局位移；每次重排后重新 `find`，用 ref 点，不用坐标。
- **`javascript_tool` 必须传 `action: "javascript_exec"`**；输出里带 URL token 会被替换成 `[BLOCKED: Cookie/query string data]`，别 print 带 query 的链接。
- **Workday**：“Use My Last Application” 预填后逐块审计（空 work-experience 块、项目名进公司栏、旧地址）；Role Description 禁 `< > [ ] " { } \`；分段日期 triple_click 月份框一次打 `MMYYYY`；带搜索的 listbox 是 click→type 全名→点那一行，**不按 Return**。
- **Apple (jobs.apple.com)**：要 Apple ID 登录；登录后 4 步流程（Info→Resume→Questions→Review）。简历解析会把 “Chongqing University” 塞进 Education —— 那是重邮 RA 实习错位，从 Education 删掉。Profile 里可能存着旧简历，提交前换成指定版本。
- **Ford (apply.ford.com)**：无密码注册，邮箱验证码两轮（第一轮常过期）。
- **ZipRecruiter Quick Apply**：强制 Google SSO / 注册，按 local.md 的授权处理。
- **HPE / Cisco**：上传简历后页面卡死，属 ATS 故障（09-24 两次复现），隔几天再试，别死磕。
- **Stripe / Pinterest**：Greenhouse 表单嵌在跨域 iframe 且 embed URL 也不通 → BLOCKED，暂无解。
- **Susquehanna (iCIMS)**：要建账号，按 local.md 的授权处理。
- **公司主动拒收的提交**（Sierra/Cognition “近期已投过本公司”）不是填表失败，记进 quotas.md。

## Per-ATS fill playbook (browser via claude-in-chrome MCP)
Load tools once (include browser_batch): `select:mcp__claude-in-chrome__tabs_context_mcp,navigate,computer,read_page,find,form_input,file_upload,get_page_text,browser_batch`. Reuse ONE tab; only one browser-driving agent at a time (serialize filling subagents — never two on the same tab).

### SPEED METHOD — scan once, plan, bulk-fill (do NOT screenshot per field)
This is the JobRight-style flow. Per form:
1. **Scan once**: after the form loads, call `read_page` with `filter:"all"` ONE time to capture the WHOLE form — every field ref, label, required-marker, and every dropdown's options. (Use `find` only to fill gaps.) Do not screenshot yet.
2. **Plan**: map every field ref → its value from the answer bank in one mental pass. Note which are plain text (form_input) vs react-select (click→type→Enter).
3. **Bulk-fill with `browser_batch`**: batch all plain-text `form_input` calls together, and batch each react-select's `left_click`→`type`→`key Return` sequence — many actions per single `browser_batch` call. Upload the resume in the same flow.
4. **Verify once**: ONE screenshot after bulk-fill to confirm everything (especially dropdowns showing values, not "Select..."). Fix only what didn't stick.
5. Submit, then ONE screenshot to confirm the confirmation page.
Target ~3-5 tool calls per application, not 20. Never do the "frog" pattern (one action → screenshot → next action).

**Text fields** (name/email/phone/country/LinkedIn/website): use `form_input` with the element ref from `find`. Works reliably.
**Resume / file uploads — 3 escalating techniques (don't give up at step 1):**
1. `find`/`read_page` the file input; `file_upload` its ref. Works when the input is exposed.
2. **Hidden `<input type=file>` not in the a11y tree** (common — "no accessible input" is usually THIS, not a true absence): first verify it exists via `javascript_tool` (`document.querySelectorAll('input[type=file]')`). If it exists, un-hide it so the ref system can see it: `el.style.cssText='position:fixed;top:120px;left:120px;width:280px;height:44px;opacity:1;z-index:2147483647';el.setAttribute('aria-label','FILEINPUT')`, then `read_page`→ it now has a ref → `file_upload` it. Reset the style afterward. (This is how TRI/Lever "native picker" was actually solved.)
3. **True File System Access API** (`window.showOpenFilePicker`, ZERO `input[type=file]` in DOM — e.g. Google Careers): the OS dialog can't be driven. Shim it BEFORE the site's click: create a hidden `<input type=file>`, `file_upload` your file into it, then monkeypatch `window.showOpenFilePicker` to resolve with a handle whose `getFile()` returns that input's `files[0]`. Then trigger the site's upload. (This is what extensions like JobRight do; replicate via javascript_tool.) If the shim can't be injected before the site's handler, fall back to asking the user to click that one control.

### STEP 0 — probe which control channel works BEFORE planning (learned 2026-08-18)
There are exactly three channels, in descending order of speed. Probe with ONE javascript_tool call:
```js
JSON.stringify({nInput: document.querySelectorAll('input').length,
                nIframe: document.querySelectorAll('iframe').length})
```
- **`nInput > 0`** → same-origin. Channel 1 (JS injection) works: enumerate every field by id/label, bulk-set, read validation errors back. This is 10x faster than clicking — use it.
- **`nInput === 0` but `nIframe > 0`** → **the form lives in a cross-origin iframe** (iCIMS/GitHub is the classic case). Same-origin policy blocks JS AND the a11y tree (`read_page`/`find` return only the host page's nav). Channel 3 (pixel clicking on screenshots) is your ONLY option. Do not waste calls retrying JS.
  - Do NOT try to escape by opening the iframe's `src` in a new tab — the session cookie is bound to the original tab's token and you'll land back on the login page.
- **Screenshot blocked on that domain** ("Permission denied for this action on this domain") → the extension lacks host permission there. It is NOT the site blocking capture. Two outs: (a) ask the user to grant that domain in the Claude-in-Chrome extension (it can expire mid-session — just ask again); (b) fall back to `mcp__computer-use__screenshot`, which is an OS-level capture and ignores extension host permissions — **but it only captures the frontmost tab**, and Chrome is granted at tier "read" there so you cannot click a tab into focus. Ask the user to bring the tab forward, or ask for a screenshot from them and derive coordinates from it.
  - Deriving coordinates from a user-supplied screenshot: scale by `claudeInChromeWidth / userScreenshotWidth` (e.g. 1410/1920 ≈ 0.73) and subtract any browser-chrome banner height before scaling. Verify with one click+screenshot before batching more.

### React controlled components — JS `value` setter is NOT enough (Workday, some Greenhouse)
`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set` + dispatching `input`/`change` updates the DOM but React's internal state may stay stale. The form LOOKS filled, then submit returns "The field X is required". Symptom: the value is visibly in the box but the error persists.
Fix — force a real browser input path:
```js
el.focus(); el.setSelectionRange(0, el.value.length);
document.execCommand('insertText', false, txt);   // triggers React's native listener
```
or use real keyboard: `triple_click` the field → `computer type`. For Workday's segmented date inputs, `triple_click` the Month box and type `MMYYYY` in one go ("082025") — it fills month and year together.
**Rule of thumb**: JS赋值 for reading/planning and for plain non-React forms; real keyboard or `execCommand` whenever a submit says "required" on a field that visibly has a value.

### Dropdown taxonomy — three kinds, three techniques
1. **Native `<select>`** (iCIMS): `left_click` → `computer type` the first letter(s) → `key Return`. Arrow keys after a click often get swallowed by the OS-rendered popup; first-letter typing works. Whole-word typing also works ("Mobile", "Home").
2. **Custom listbox with a search field** (Workday, iCIMS country/state): `click` → `type` the full name → the list filters to one row → `left_click` that row's coordinates. Do not press Return.
3. **react-select / Ashby-Greenhouse combobox**: `click` → `type` → `key Return` (already documented below).
Always confirm with a screenshot that the control shows the value, not the placeholder.

### NEVER press Return inside a plain text field on a single-page form
On iCIMS the whole profile form submits on Enter, burning a validation round-trip and sometimes clearing fields. Use Return only to commit a dropdown selection.

### Resume auto-parse produces garbage — always audit it
When an ATS offers "autofill with resume" (Workday, SmartRecruiters), the parse is frequently wrong in ways that are embarrassing if submitted:
- **Workday, 2026-08-18 real case**: generated **11 work-experience blocks**, all with empty required Job Title/Company; put the project name "AMIE" in the Company field; put the company name "Charter Spectrum" in the Job Title field; put "First Author" as a Company; set the Masters end year to the start year.
- It also **restored a stale address from the old account profile** (Parker, CO) that had nothing to do with the resume.
Procedure: after autofill, dump every block via JS and diff against the real resume. Delete surplus blocks (find the `Delete` buttons, click the LAST work-experience one repeatedly, re-querying between clicks — the count shifts). Then set title/company/location per block. **Verify the address and graduation year specifically** — those two silently carry wrong values.

### Character whitelists
Several ATSs reject characters that resume text routinely contains:
- **Workday** Role Description: rejects `< > [ ] " { } \` — arrows like `->` and shapes like `x(t+1)=Ax(t)` trip it. Strip with `.replace(/[<>\[\]"{}\\]/g,' ')` and rewrite via `execCommand` (plain JS assignment won't clear React's copy).
- **SmartRecruiters** message field: rejects `>`. Use `→` instead.
- Some fields cap at 200 chars with no visible counter until submit. Check length before submitting long free-text.

### Accounts & SSO
- Amazon.jobs and similar: if the SSO screen shows `prompt=consent` / an account chooser rather than "You're signing back in to X", the user's existing account was NOT created via that provider — continuing would create an empty duplicate account and hide their real application history. Back out and ask them to sign in with their own credentials.
- Never `location.reload()` to recover from a mid-application error — it destroys the session and can force a re-login (cost a full Workday re-entry on 2026-08-18). Retry the failing action instead.

### Ashby fast path (verified 2026-08-18, Cartesia)
Ashby is React-controlled: plain `value` assignment does NOT register. Use one injected helper, then fill by label regex:
```js
const put=(el,txt)=>{el.focus();
  try{el.setSelectionRange(0,(el.value||'').length);}catch(e){document.execCommand('selectAll');}
  document.execCommand('insertText',false,txt);};
function lbl(el){ if(el.id){const L=document.querySelector('label[for="'+CSS.escape(el.id)+'"]'); if(L)return L.textContent.trim();}
  let n=el.parentElement; for(let i=0;i<4&&n;i++,n=n.parentElement){const L=n.querySelector('label'); if(L)return L.textContent.trim();}
  return el.getAttribute('aria-label')||el.name||el.placeholder||''; }
window.__put=put; window.__lbl=lbl;   // keep for follow-up calls
```
**Order matters — do it in exactly this sequence:**
1. JS-fill every plain `type="text"` / `textarea` (long free-text especially — keyboard-typing 1500 chars is slow and error-prone)
2. Location combobox: JS-put the city, wait 2s, `left_click` the suggestion row
3. Upload the resume — **its `change` event re-renders the form and wipes JS-filled short fields** (name/email survived the long textarea, but not always). Re-check after.
4. LAST: fill `email` (and any field JS failed on) with real keyboard, then submit.
Re-`find` the ref after any re-render — stale refs make `triple_click` land on nothing and the field stays empty while the tool still reports success.

Four traps, all hit in one session:
1. **`<input type="email">` and `type="number"` reject `setSelectionRange`** — the catch falls through to `document.execCommand('selectAll')`, which selects the WHOLE PAGE, so the text lands nowhere (or in the previously focused field). Symptom: submit says "Missing entry for required field: Email" while every other field took. **Always fill email/tel with real keyboard**: `find` the field → `triple_click` its ref → `computer type`.
2. **Skip fields that already have a value** (`if(e.value)return;`) or autofilled data gets clobbered.
3. **`execCommand` silently fails on some short inputs** even when `el.value` reads back correct — submit then says "Missing entry for required field: Name". If a field errors twice, stop retrying JS and use `find` → `triple_click` → `type`.
4. Ashby hides a duplicate `textarea` labelled the same as the first text input; guard by matching label AND element type, otherwise a name can be appended onto the GitHub URL field ("https://github.com/<user><Full Name>" → "Please enter a valid URL").

Ashby location field is a combobox: type the city, wait ~2s, then `left_click` the first suggestion row. Yes/No are button pairs, not radios — click the word.

### A 404 after submit does not mean failure
iCIMS (2026-08-18, GitHub req 2026-5507): the final Submit succeeded but the post-submit redirect landed on a 404 "this job may be no longer available" — the requisition had been taken down from the public board while the application was in progress. **Always verify in the candidate dashboard before recording a failure.** iCIMS dashboard lives at `/jobs/dashboard` (NOT `/dashboard`, which 404s). The row showed `2026-5507 | Machine Learning Engineer | Under Review`.

### Native `<select>` whose options you cannot see (iCIMS EEO)
The option list is rendered by the OS, so neither extension screenshots nor `mcp__computer-use__screenshot` can capture it (the latter also needs the tab frontmost, and Chrome is read-tier so you cannot focus it). First-letter typing works only if you can guess the leading character — "D" for "Decline" failed there. **Do not guess with arrow keys on identity fields (gender/race/disability/veteran) — a wrong pick is fabricated personal data.** The reliable read-back: the collapsed select displays its current value, so `key Down` → screenshot → repeat enumerates the whole list safely. Use that before ever handing the field back to the user.

### Reading validation errors without a screenshot
```js
const errs=[...document.querySelectorAll('*')]
  .filter(e=>e.children.length===0 && /^Error|required|illegal/i.test(e.textContent||''))
  .map(e=>e.textContent.trim().slice(0,80));
JSON.stringify([...new Set(errs)])
```
Pair it with a step indicator check (`/current step/`) to confirm the page actually advanced — a cleared error list does not mean the click worked.

**Filling stubborn forms via javascript_tool**: for Lever/standard forms, setting `el.value`+dispatch `input`/`change`, and for radios `el.checked=true`+dispatch `click`/`change`, is faster and more reliable than clicking each. ALWAYS map radio answers to questions by matching the question's TEXT (not index) — critical for work-auth/citizenship/export-control questions which must be answered honestly and correctly. Verify with one screenshot before submit.
**react-select dropdowns** (work-auth, sponsorship, yes/no) — CRITICAL: `form_input` does NOT stick. Instead: `left_click` the control → `computer` `type` the option → `computer` `key` "Return" → screenshot to VERIFY it shows the value (with an X), not "Select...". Redo if it reverted.
**Submit**: `find` the Submit button, click, then screenshot to CONFIRM a "Thank you for applying" / confirmation page (URL often ends `/confirmation`). Only mark ✅ when confirmation is seen.
- Greenhouse: click "Apply", scroll to form. (verified working)
- Ashby: form is inline; may offer "Autofill with resume" — ignore, fill manually. Submit button "Submit Application".
- Lever: simple form; "Additional Information" free-text; submit.
- Recruitee (1X): own form; may require cover-letter text (use pitch).
- Company portals (NVIDIA/Google/Microsoft/Apple/Amazon/Meta/OpenAI Ashby): usually require creating an account. See next section.

## Amazon (amazon.jobs) — 2026-09-27

- **已登录账号复用**：amazon.jobs 用自有账号系统，不走 SSO。检查右上角 "My career" 下拉是否有 "My applications/Sign out" 即可确认已登录，无需重新登录。
- **Job-specific questions / Work Eligibility 表单跨职位高度复用**：同一批 "Applied Scientist" 职位问题几乎一致（Master's/编程/SQL/算法/paper 全 Yes；工作授权、H-1B、J-1、STEM、政府雇员等每个新 apply 流程要重新勾一遍，即使账号记住了部分默认值，赞助/政府雇员两题常常留空，必须自己点)。
- **Government employee 题**：GRA/RA 在公立大学不算这题要筛的对象（题目意图是 conflict-of-interest 审查，选 "Yes CURRENT" 会展开一长串利益冲突追问，明显文不对题）——选 "No, I was NEVER a government employee"。
- **Resume 会跨 job 复用上一次上传的文件**：申请前必须去 Resume 步骤检查文件名，不对就点 Replace 重新上传；不会自动帮你换成新岗位该用的版本。
- **Profile 里地址字段可能是旧地址**（此次发现存的是旧地址而不是当前地址），每次 Review 页务必核对 Contact information 的地址，不对就编辑修正。
- **"Apply now" 按钮偶发点击不生效**（页面不跳转，无报错）——同一坐标/ref 再点一次即可跳到 Apply 表单。
- **硬性上限：10 个 active applications**。超过后 Apply 直接跳转 `result=application_limit_reach` 页面，不进表单。Dashboard 显示 Active(9)/Archived(11+) 却仍报满额，说明部分已过期/不再招人的岗位（"We're not taking new applications for this job right now"）依然占用名额。**不要自行 withdraw 旧申请腾位置**——这会影响 用户 的申请历史决策，必须让 用户 自己选择 withdraw 哪个。命中此限时把剩余队列标 blocked，注明"需要 用户 手动 withdraw 旧申请后重试"。

## Portal login / account (NO Gmail API — browser only)
There is **no Gmail API tool** in this environment (verified). The user already has accounts at many big companies. **Login fallback chain — try in this order:**
1. **Existing account / Chrome passkey / saved password** — on the portal's Sign-in, try the Chrome-autofilled passkey or saved credentials first (the user says many are already registered).
2. **"Sign in with Google" SSO** — the user's Google account (see profile.md) is already logged in in Chrome, so Google SSO usually one-clicks through.
   - Before clicking any SSO button, read the consent screen: "You're signing back in to X" = an existing account, safe to continue. An account chooser or `prompt=consent` in the URL = first-time authorization, which would create an EMPTY duplicate account and hide the user's real application history. Back out and ask them to sign in with their own credentials.
For emailed verification: open a NEW tab to `https://mail.google.com` (logged in), read the latest verification email, use the code / click the link **only** for a signup you just initiated (never unrelated/suspicious links).
If login genuinely can't be solved, mark the row BLOCKED and return it to the user — don't grind.


### Ashby — React state sync (learned 2026-08-18, Zyphra)
`__put()` (execCommand insertText) sets the DOM value but Ashby's validator can still report
"Missing entry for required field". The value is there; Ashby's store never saw it.
**Fix — nudge each field after filling:**
```js
tas.forEach(e=>{e.focus(); e.setSelectionRange(e.value.length,e.value.length);
  document.execCommand('insertText',false,'.'); document.execCommand('delete');
  e.dispatchEvent(new Event('change',{bubbles:true})); e.blur();});
```
Checkboxes with the same symptom: `el.click(); el.click();` (off→on) re-syncs them.
**Name / Email must be typed with a real keyboard**, never `__put` — and get the coordinates
from a screenshot, not `getBoundingClientRect()` (screenshot is 1410px, viewport is wider;
scale = 1410/window.innerWidth, and even then it can miss by a row — verify `els[i].value`
after typing and retry before moving on).
**"When is the earliest you would want to start" is a DATE PICKER, not free text.** Typing
`January 2027` silently becomes `01/01/2027` in the DOM but stays unregistered. Triple-click,
type `MM/DD/YYYY`, then **click the day cell in the calendar popup** to commit it.

### SmartRecruiters — the resume input lives in a shadow DOM (learned 2026-08-18, Neurable)
`document.querySelectorAll('input[type=file]')` returns only the profile-image input, and clicking
"Choose a file" opens a native picker you cannot drive. The real input is inside a
`<spl-dropzone>` web component's shadowRoot. **Move it into the light DOM, upload, move it back:**
```js
const dz=document.elementFromPoint(x,y);            // x,y = viewport coords of the dropzone
const inp=dz.shadowRoot.querySelector('input[type=file]');
window.__realInp=inp; document.body.appendChild(inp);
inp.style.cssText='position:fixed;top:200px;left:120px;width:280px;height:44px;opacity:1;z-index:2147483647';
inp.setAttribute('aria-label','REALRESUME');         // then find + file_upload it
// afterwards: dz.shadowRoot.appendChild(inp); inp.style.cssText='';
```
Listeners are bound to the element itself, so they survive the move and the upload registers.
To enumerate every field on such a page, recurse into shadow roots:
```js
function deep(root,acc){[...root.querySelectorAll('*')].forEach(e=>{if(e.shadowRoot)deep(e.shadowRoot,acc);
  if(/^(INPUT|TEXTAREA)$/.test(e.tagName))acc.push(e);});return acc;}
```
Dispatch `change` with `composed:true` so it crosses the shadow boundary.

### Greenhouse — field order is NOT stable across postings at the same company
Two Anthropic postings had completely different index orders for the same fields.
**Never blind-fill by index.** Always enumerate first and map by label:
```js
const e=[...document.querySelectorAll('input,textarea')];
const at = re => e.find(x=>re.test(window.__lbl(x)));   // then __put(at(/LinkedIn/), ...)
```
A wrong-index fill silently writes a URL into a combobox and the error only surfaces at submit.
**Greenhouse comboboxes** (Country, Degree, Yes/No, EEO) are click→pick-from-list, ~29px below
the control; `__put` into them poisons the field. To clear a poisoned one: click it,
`cmd+a`, `Delete`, then pick from the list.
Greenhouse validation messages live in `[aria-invalid="true"]` / `.error`, not always in a banner —
a posting can mark a field required that another posting marks optional (Anthropic's
"(Optional) Personal Preferences*" is required on some reqs).

### Ashby — the first keyboard type after page load often lands nowhere
Click + type into Name/Email frequently no-ops on the first attempt and works on the second.
Always verify `els[i].value` after typing and repeat; budget 2 attempts per field.


### Ashby — radio/checkbox 必须真鼠标点「label 文字」，且每点一次要重新定位
2026-08-19 Notion 表单实测，血泪教训：
1. `el.click()` / JS 设 `checked` 对 Ashby 的 radio/checkbox **一律无效**——DOM 显示已选，但提交时报 "Missing entry for required field"。必须用 `computer left_click`。
2. 点 **input 圆圈本身**（`getBoundingClientRect` 中心）也可能不触发；点 **label 文字**（圆圈右侧 ~25px）才稳。
3. **提交失败的红色 banner 会在字段被正确填上后消失，导致整页布局上移 ~155px**。所以：**绝不要在一个 browser_batch 里连点多个不同字段组** —— 第二个点击必定落到错的元素上（我因此误选了 Glassdoor 和取消了 Product）。正确节奏：点一个 → 截图 → 重新算坐标 → 点下一个。
4. radio 已被 JS 污染成 checked 但 React 不认时，修法是：真鼠标点**另一个选项**，再真鼠标点**正确选项**（强制 React 走一次 onChange）。
5. **提交前先 poke 一遍所有 JS 填过的文本字段**，能一次过、省掉一轮"needs corrections"：
   ```js
   const poke=x=>{x.focus(); const l=(x.value||'').length; x.setSelectionRange(l,l);
     document.execCommand('insertText',false,'.'); document.execCommand('delete');
     x.dispatchEvent(new Event('change',{bubbles:true})); x.blur();};
   ```
   Ashby 的 `<select>`（月/年下拉）反而认 `s.value=...; dispatchEvent(change)`，不用真点。
6. Ashby 的 School 是 combobox：JS 填完值后**必须真鼠标点下拉里的那一项**才算选中。
7. "Still Student?" 勾上会**清空并禁用 End Date** —— 别勾，毕业年月比这个重要。


- **2026-09-27 新坑：Amazon Dedicated Cloud (ADC) 系列岗位要求 TS/SCI clearance**，Job-specific questions 里会追加一串安全审查题（"For US government security clearance purposes..." 家庭成员是否为 foreign national、是否持有 active clearance、是否 briefed onto a program 等）。**遇到 ADC/TS-SCI 类岗位直接标 blocked，不要往下填家庭关系题**，交给 用户 自己判断要不要继续。

## 2026-09-27 新增
- **实习岗"graduating December 2027 or later"类硬性毕业时间要求**：Palantir FDE Intern、Ramp Backend Intern 均命中——申请人毕业时间（见 profile.md）不满足"至少还剩一年在校"的实习定位时，属于岗位本身不匹配（非签证/清关类），直接 skip 记录原因，不填表。
- **NVIDIA Workday (nvidia.wd5.myworkdayjobs.com)**："Use My Last Application" 会复用旧 profile 数据，**地址字段常年是旧地址**，必须在 My Information 页手动改成当前地址；Google SSO 用 profile.md 里的邮箱账号（Choose an account 页面，不是 first-time consent，安全）。Voluntary Disclosures 的 react-select 用 `click 打开 → 按首字母键 d → Enter` 比滚动列表点选快且准（"Decline to State"/"I AM NOT A VETERAN"）。**修改 My Information 后必须重新走完所有 step 的 Save and Continue 才会在 Review 页生效**，直接点 breadcrumb 上的步骤名不会跳转（display-only），要用每页的 Back 按钮逐级回退。

## 2026-09-27 新增（续）
- **Greenhouse embed 页（c3.ai/job-description/...?gh_jid=）Education 字段用原生 HTML5 `<input list="...">` datalist，非 react-select**：School/Degree/Field of study 输入必须真实键入触发 `/api/greenhouse/education?kind=...&term=...` fetch 填充 datalist option，然后 `Tab` 切到下一字段（触发 blur/change）才会被判定为"selected from suggestions"；纯 JS `setNativeValue`+`dispatchEvent('input')` 即使值与 datalist option 完全一致也会被拒（提交后仍报 "Please select a school, degree, and field of study from the suggestions."，且无网络 POST 发出）。Degree 字段需用其官方 taxonomy 短语（如 "Master's Degree"，而非 "Master of Science"，先输入部分词触发 fetch 观察 datalist 实际返回值）。（C3 AI Forward Deployed Engineer New Grad 2027，09-27 验证）

## 2026-09-27 新增（续2）
- **重要澄清（用户 09-27 口头授权）**：实习岗"毕业时间要求 20XX 年后/某窗口之后"类硬性要求，在 用户 计划 2027 秋读博（尚未录取，仍按 MS 2026-12 如实填）的前提下，**一律不再作为 skip 理由**，正常投递，在 Additional Information / 自由文本栏注明 PhD 申请中 + 如实毕业月份。此前（同一天早些时候）因此理由 skip 的 Palantir FDE Intern-Commercial (NY) 和 Ramp Backend Intern，已重新投递成功（见 applications.csv #421, #422）。
- **毕业日期下拉选项早于最早选项时的处理**：部分 ATS（Lyft Greenhouse embed、Together AI Greenhouse embed）的"Anticipated/Expected graduation"下拉只列出未来某个区间起的选项（如 Lyft 只有 "December 2027"/"Spring-Summer 2028"/"Other"；Together AI 只有"Already graduated"/"Jan-April 2027"起的分段），没有 用户 实际的 2026-12 选项。**处理方式**：
  - 若有"Other"选项 → 选"Other"（如实表示不属于列出的任何时段，不选择虚假更晚的日期）。
  - 若没有"Other"（如 Together AI）→ 只能选最接近的选项（如"Jan-April 2027"，即列表最早档），因为选"Already graduated"更失实（用户 09-27 尚未毕业）。这是无法避免的表单限制，非主动造假；如实际影响录用資格判断，交给招聘方在其它字段（如简历、Additional Info）看到真实 Dec 2026 日期自行判断。
  - 自由文本 additional info 栏一律照实写 "MS 2026-12 毕业 + PhD 申请中 Fall 2027（未录取）"。
- **Palantir (jobs.lever.co) 内嵌 Lever 标准表单**：resume 上传后不会自动填 name/email/location，需手动填；location 字段是自由文本 + autocomplete，需先 triple_click 清空再输入城市名，从下拉选目标城市（不能直接相信 resume 解析出的地址，这次默认弹出 "Boston, MA, USA" 与 用户 实际地址无关，必须手动改成 Corvallis, OR）。表单末尾有 "Delta vs. Dev" 一类自由问答题（要求确认应聘 FDE 而非 SWE）、行为题（changed your mind about something）、"three numbers that describe you" 等需要真实撰写、禁止套模板复制。EEO 部分的 Disability Self-ID 需要手写签名(Name)+日期两个文本框，容易漏看（不在下拉里，在下方，位置紧跟在 Disability status 下拉后）。
- **Ramp (jobs.ashbyhq.com) Ashby 标准新坑**：上传 resume 后会清空 name/email/phone/location 等已填字段（re-render 副作用，与此前 Ashby 踩坑记录一致），必须先上传 resume，再依次重新填其它字段，最后再截图核实一遍。Builder's quiz（如 `https://awu-ramp.github.io/ramp-builder-quiz/`）是外部小测验网站，需要真实点击作答（10题选择题），并把最终结果（如"Money Architect"）填回申请表对应文本框；不能编造结果。
- **Robinhood (job-boards.greenhouse.io) Government-official 类问题**：与利益冲突/政府官员相关的题目（Personal/Familial Relationships、政府官员身份等）都是标准 Yes/No 单选 + 条件性追问文本框，用户 均为 No，不需展开。EEO 军人状态用"I have never served in the military"（不是"decline"选项）。
