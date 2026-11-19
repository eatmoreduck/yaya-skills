---
name: yaya-corpus
description: Turns rough drafts into listenable study material — proofreads English narration scripts (or translates a Chinese broadcast script into conversational English with the user's sign-off), cleans and segments the text, then synthesizes MP3 entirely offline with Kokoro-82M, plus bilingual LRC/SRT subtitles and embedded ID3 lyrics and cover art, then optionally publishes the batch fully-automatically to the NetEase Cloud Music cloud drive and a playlist (OAuth-free, scan-QR once). Use when the user says "做语料" as well as "传网易云", "上传云盘", "发到歌单". Input can be docx, PDF, or plain text; a PDF whose text layer is font-subset-scrambled can be decoded first. Use when the user says "做语料", "把稿子做成 MP3", "转成音频", "生成精听素材", "校对这篇稿子", "翻译口播稿", "加双语字幕", or wants audio files for a listening or podcast platform. The mirror of yaya-asr: text in, audio out.
version: 0.2.0
metadata:
  openclaw:
    homepage: https://github.com/eatmoreduck/yaya-skills#yaya-corpus
    requires:
      anyBins:
        - uv
---

# yaya-corpus —— 文字稿 → 可听语料

**文字稿进 → 可上架的中英双语音频出。** 校对、清洗、分段、离线合成、双语字幕、标签内嵌，一条流水线走完。合成全程本地跑，稿子不出你的机器；免费、零登录、不需要任何云端账号。

这是 [yaya-asr](../yaya-asr/) 的**镜像**：yaya-asr 把声音变成文字，本 skill 把文字变成能听的内容。两者都是原子能力，不认识业务概念——不知道稿子是导游词、课程还是播客。

**核心价值在「校对」而不是「合成」。** 原稿来源不可控（网络素材、扫描稿、自己口述的转写），直接念出来连语法错误一起念。本 skill 的契约是：**输入的稿子可以很糙，产出的语料永远干净、可以直接学**。

## 何时使用

- 用户给一份 docx / PDF / 文本稿，要**做成音频**（"把这个稿子做成 MP3""搞几段语料"）
- 用户要**校对英文讲解稿**、把**中文口播稿翻成英文**
- 用户要**双语字幕**（LRC 英文在上中文在下，或 SRT）
- 用户要**能直接上传**的音频（内嵌歌词、封面、专辑/歌手标签）
- 用户说"做语料""转成音频""生成精听素材""加双语字幕""歌词内嵌"

**不适用**：手里已有音频要文字 → 用 `yaya-asr`；要 X Space 干货笔记 → 用 `yaya-xspace`。实时朗读、交互式语音助手不在范围（本工具处理已有的文字稿）。

## 快速开始

```bash
# 1. 取文本（docx / pdf / txt，默认带英文清洗）
bash {baseDir}/run.sh extract 讲解稿.docx -o draft.txt

# 文本被字体子集混淆时，先破密再抽
bash {baseDir}/run.sh decrypt 加密导游词.pdf -o out/decrypted/

# 2. 写 plan.json（结构见下），合成 MP3 + LRC/SRT
bash {baseDir}/run.sh synth out/plan.json

# 3. 写入歌词 / 封面 / ID3 标签
bash {baseDir}/run.sh tags out/mp3/ --album "专辑名" --artist eatmoreduck
```

首次运行用 `uv` 自建 `.venv` 并装依赖；Kokoro 模型（约 350MB）缺时自动下载，落在本 skill 的 `models/kokoro/`。

## 子命令

| 子命令 | 输入 | 输出 |
|---|---|---|
| `extract` | docx / pdf / txt | 纯文本（`--raw` 关闭清洗，`--headings` 只列小标题） |
| `decrypt` | 文本层混淆的 pdf | `*.txt` 解码文本 + `*.suspect.txt` 可疑词 + `decode_report.json` |
| `synth` | `plan.json` | `<段名>.mp3` + `.lrc` + `.srt` |
| `tags` | 目录 | 就地改写 mp3 标签（USLT + SYLT + APIC + TIT2/TPE1/TALB/TCON） |

## plan.json

```json
{"outdir": "/abs/out", "voice": "af_heart", "speed": 1.0, "bit_rate": 96,
 "segments": [{"name": "01-豫园-开篇",
               "paragraphs": [{"text": "English sentence.", "zh": "中文翻译", "pause": 0.6}]}]}
```

**`paragraphs` 就是字幕句粒度**：一条 = 一条字幕（1-2 句英文，≤150 字符）。逐句合成再拼静音，时间戳才准；整段合成再估算时间会对不上。

## 产物

```
<outdir>/
├── 01-区域-关键词.mp3   24kHz 单声道，峰值归一 0.95
├── 01-区域-关键词.lrc   英文在上、中文在下，同一条时间戳
└── 01-区域-关键词.srt   同序，不带 zh-CN 头
```

LRC 是给「每日英语听力」这类工具用的，**英上中下共用时间戳**是硬要求：

```
[00:12.40]It was first constructed in 1559 during the Ming Dynasty.
[00:12.40]它始建于1559年的明代。
```

## 流程（Agent 按此执行）

### 第 0 步 · 问清楚（熟客走默认）

- 切分粒度 / 只读英文还是双语都读 / 音色（**先出试听让用户挑**，别替他决定）
- **已确认的默认**：按片区中等切分 8-10 段；只读英文；af_heart / 语速 1.0；换景点停顿 1.6s、段首 0.6s、句间 0.25s；标注"不讲/跳过"的段落不生成

试音流程：同一段文本用 4-5 个 voice 各出 20-30s MP3，放 `_试听/` 让用户 A/B。

### 第 1 步 · 校对与翻译（必做，本 skill 的差异化）

原稿来源不可控，合成前必须过语言关：

1. **英文稿校对**：逐句修拼写、语法、搭配、时态，**直接改**（不是只报告）。典型病症：
   - `was should be sent` → `was supposed to be sent`；`eyecatching` → `eye-catching`
   - 主谓一致（`the stone stay here` → `stays here`）、冠词缺失、中式搭配（`open the light` → `turn on the light`）
   - 修正**同步生效于朗读文本和中文字幕**
   - 交付时附**修改清单**（原句 → 改句 + 一句话理由）；**事实性内容（数字/年代/人名）不确定先问，不擅自改**
2. **中文口播稿**：先翻译成地道口语化英文讲解稿（导览语气、短句优先、避免书面腔），**用户确认译文后**再合成；中文原文直接做字幕 `zh`，不二次翻译
3. **中英混排**：英文为主中文零星夹杂 → 重组英文句（`or "玉玲珑" in Chinese` → `or Yu Linglong in Chinese`）；中英各半且内容重复 → 英文朗读、中文字幕

### 第 2 步 · 清洗文本

`extract` 已覆盖：全角标点转半角、弯引号归一、剔除中文残句、数字字母粘连补空格、句末/逗号后补空格。

**仍需人工处理的**：

- **含中文的段落必须逐段重写**，直接删中文会留残句：
  `Mr.江泽民` → `Mr. Jiang Zemin`；`陆家嘴Financial Center` → `the Lujiazui Financial Center`
- **序数词/年代转读音**：`18th` → `eighteenth`、`1950s` → `nineteen fifties`。否则会念成"一九五零 S"。这项清洗不会做，必须手动补进 plan 的 `text`

### 第 3 步 · 分段

按动线/场景分组，保持原文顺序，边界落在"换地点"处。段名 `序号-区域-关键词`，不要空格。

### 第 4 步 · 合成

写 plan.json 交给 `run.sh synth`。约 **4x 实时**（40 分钟音频 ≈ 10-15 分钟合成），长任务放后台跑。

### 第 5 步 · 双语字幕

`synth` 自动出 LRC/SRT。两条硬规则：

- **字幕句 = 合成单元**，不要整段合成后估算时间
- **多句对话（引号套多句）必须作为 atomic 列表逐条给**，否则断句器会拆散引号、产生孤儿引号
- 断句白名单：`No.`、`Mr.`、`Dr.`、`St.`、`Co.`、`i.e.`、`e.g.` 后不切句

### 第 6 步 · 标签内嵌

```bash
bash {baseDir}/run.sh tags <输出目录> --cover 封面.jpg --album "专辑名" --artist "作者"
```

- USLT（整份 LRC）+ SYLT（毫秒级逐行）双写，APIC 封面，TIT2/TPE1/TALB/TCON
- `--album` 省略用目录名；`--artist` 省略用 `eatmoreduck`；`--cover` 省略依次找目录下 `cover.jpg` / `封面.jpg` / skill 自带封面，都没有就跳过 APIC
- 可重复执行（同名帧先删除）

### 第 7 步 · 校验交付

- 残留中文扫描 `[一-鿿]`（朗读文本应为空）
- 粘连扫描 `[a-z][A-Z]`、`[a-z]\.[A-Z]`
- `afinfo` 验时长
- 交付物：mp3 + lrc + srt + 目录 md（文件名/词数/时长/分区）+ 修改清单
- **重做时旧文件移 `_旧版*/` 或废纸篓（经用户确认），不直接 rm**

## PDF 文本层被混淆时

有些 PDF 的文本层做了**字体子集混淆**：页面显示正常，但复制/提取出来是 `!"#$"#%& '(#%)*.`。规律是「按首次出现顺序把第 k 个不同字符映射到 0x21+k」，同一份 PDF 内稳定，**不同 PDF 映射不同**，标点会撞码。

`extract` 会粗判并提示；改用 `decrypt`：

1. `pdftext.py` —— PyMuPDF 提取 + 水印行过滤 + 康熙部首归一
2. `final2.py` —— 按文件求解映射，候选（seed / crib / free）用**英文三元组概率**择优
   - 基准种子 `SEED_0003` 覆盖约 40 个字母，多数文件直接可用
   - 标题与正文用不同子集时 crib 会失效，改走 `free`
3. `normalize.py` —— 逐类修补残留（词尾 `.` 实为 `t`、词尾 `o` 实为逗号、行尾连字符断词、年份数字映射）

**必须人工核可疑词**：`decrypt` 输出 `*.suspect.txt`，按语言分升序排列（越靠前越像解码残留）。清单是「词典外词」，专名也在此列，需逐条确认；年份/专名/数字最容易错。

**`normalize.py` 的 `FIX` 表只在检测到密文（`方案 != plain`）时才套用。** 它是针对特定 PDF 的个案修补，含 `'t,'→'to,'` 这类短键——无条件全局替换会把 `The market,` 改成 `The marketo`（真实踩过的坑）。干净文本一律跳过。


## 发布分发（第四阶段：产物上传）

语料合成完只是半成品，最后一步是把它们送到能听的地方。两条渠道按用途选：

### 渠道 A：网易云音乐云盘（私人随身听）

全自动，无需手点。前提：本机装有 ego-browser（ego lite）与 node ≥18。

1. **扫码登录**：`ego-browser nodejs` 打开 `https://music.163.com/#/login`，出二维码截图给用户，用户用网易云 App 扫码（此步必须本人）。后台轮询「登录弹窗消失」判定成功——**不能用页面含「我的音乐」判断**，导航栏本来就这词，会误报。
2. **导出 cookie**：`ego-browser nodejs < scripts/ncm_cookie_export.mjs`（写死输出 `/tmp/ncm/cookie.txt`，`NCM_COOKIE_OUT` 可改）。cookie 含 `MUSIC_U`/`__csrf`，有效期较长，过期重扫即可。
3. **批量上传+入歌单**（前台跑，**后台任务会被沙箱断网**）：

```bash
node scripts/ncm_upload.mjs --dir <MP3目录> --playlist <歌单ID> \
  --album "专辑名" --artist "歌手名"
```

歌单 ID 从 `https://music.163.com/api/user/playlist?uid=<用户ID>&limit=100` 拿（浏览器页内 fetch 即可，无需加密）。

**踩坑记录（改脚本前必读）：**

- **weapi 加密**：双层 AES-128-CBC（`0CoJUm6Qyw8W8jud` 预置 key → 随机 16 位 key）+ RSA no-padding（`m^65537 mod n`，BigInt 实现即可）。参考实现（NeteaseCloudMusicApi 系）的响应都包一层 `body`，**直调时字段在顶层**：`check.songId`、`alloc.result.*`、`info.songId`——照抄参考代码会把 `body.` 一起带上然后 undefined。
- **NOS 上传节点**：`wanproxy.127.net/lbs` 在本机代理（fake-IP 模式）下 TLS 直接断连，浏览器内也拿不到（CORS）。节点地址由 lbs 下发，实际是 `http://nosup-jd1.127.net`（HTTP 不是 HTTPS，用 https 会 400「URL格式非法」）。拼法：`POST http://nosup-jd1.127.net/${bucket}/${objectKey}?offset=0&complete=true&version=1.0`，objectKey **不转义**，header 带 `x-nos-token` + `Content-MD5`（hex 大写）+ `Content-Type: audio/mpeg`。
- **加歌单**：`/weapi/playlist/manipulate/tracks` 的 `trackIds` 是**纯字符串数组** `["346...",...]` 加 `imme:'true'`；`[{id:...}]` 对象数组会报「传入的歌曲ID错误」（字符串/数字都不行）。code 512 时把数组翻倍重发。
- **云盘机制限制**：封面/歌词无法通过 API 写入云盘条目（`lyric:0/cover:0`），PC 客户端手动编辑也只对歌名等基本信息生效。内嵌在 MP3 里的歌词封面本地播放有效。标题/歌手/专辑在上传时通过 `info/v2` 写入，云盘正常显示。
- 上传后云盘列表接口是 `/weapi/cloud/get`（`/weapi/cloud` 已 404）。

### 渠道 B：每日英语听力（公共/精听）

官方用户上传后台：**`https://my.eudic.net/ting/index`**（欧路账号登录，仅网页端，App 不能传）。

- 上传 MP3（单文件 ≤70MB），填标题、选频道（可建「<账号名>的频道」，能设「仅自己可见」）
- **字幕格式与我们的产物严丝合缝**：「一行英文、一行中文为一段，段落间空行」——把 `.lrc` 去掉时间戳拼起来就是现成文本；带时间轴的字幕也可直接贴，无需勾选「制作同步高亮字幕」
- 也可勾选「生成 AI 字幕」（VIP 专享）让平台自动打轴，但自带字幕更准
- 传完在 App「我听」→「我的上传」收听，支持倍速、单句精听、跟读评分、词典联动查词——**正好补上「MP3 不能变速、不能逐句精听」的短板**
- 尚未自动化，计划用 ego-browser 走网页表单（选文件 + 填表 + 贴字幕），可行性已确认，待实测

**选渠道的口径**：私人随身听/当播客 → 网易云；要精听/跟读/词级学习或想公开分享 → 每日英语听力；纯阅读场景 → 微信读书（见下）。

**微信读书为什么不入选（2026-11 调研结论）**：支持传私有书（txt/epub/pdf/docx/mobi，每月 3 本限额，自动私密阅读），但**听书只有它自家的 AI 朗读**（音色/语速可调、能回原文定位），**没有上传自定义音频的入口**，也没有「音频+文字同步高亮」能力——「MP3 自己传 + 文字自己传」在它那儿是两件不相干的事，实现不了语音跟读高亮。若用户想要文字版随身读，可把双语稿拼成 docx/epub 传书架当私密阅读材料（AI 朗读可作兜底），但这不是分发音频语料的渠道。

## 环境要求

| 组件 | 用途 | 来源 |
|---|---|---|
| `uv` | 建 venv、装依赖 | 需预装 |
| `kokoro-onnx` | 离线 TTS（**不要装 `kokoro`**，它要 torch + 老 numpy，在 3.13 上编译失败） | 脚本自动装 |
| `lameenc` | MP3 编码（`afconvert` 不支持 MP3） | 脚本自动装 |
| `mutagen` | ID3 标签读写 | 脚本自动装 |
| `pymupdf` | PDF 文本提取 | 脚本自动装 |

模型：`models/kokoro/kokoro-v1.0.onnx`（310MB）+ `voices-v1.0.bin`（27MB），缺失自动下载。

## 上游与下游

- **镜像**：`yaya-asr`（文字 ← 声音）；本 skill 是反方向（声音 ← 文字）
- **不依赖任何兄弟 skill**，可独立使用
- 产物发布：网易云云盘（全自动，见「发布分发」渠道 A）；每日英语听力 my.eudic.net（渠道 B，字幕格式直接兼容）

## 已知边界

1. **只做英文合成为主**：Kokoro 走 `lang="en-us"`，中文合成本 skill 不做。
2. **翻译与校对由 Agent 完成**，不是脚本能力——脚本只管合。稿子质量取决于执行者。
3. **`normalize.py` 的 FIX 表是个案修补**，只在密文文档上套用；换新 PDF 要自己补词条。
4. **加密 PDF 破密是启发式**：同一份文档内稳定，跨文档不通用；年份/专名必须对照上下文人工核。可疑词清单是「词典外词」，专名也会列出，需逐条确认。
5. **内嵌标签本地播放全生效，但网易云「音乐网盘」不读内嵌标签**——只按标题/歌手匹配官方库，自制内容匹配不上。云盘条目的歌词/封面无法通过 API 或客户端设置，这是网易机制；但上传、入歌单已全自动化（见「发布分发」）。
6. **音色有限**：Kokoro-82M 小模型，接近真人但不如大型云 TTS。别拿它跟 ElevenLabs 比。
