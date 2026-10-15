> 当前以 ai_relays_export.json 为唯一数据源。本文件其余内容为历史记录，原 SQLite 命令已停用，不代表本轮注册或到账实测。

# AI 中转站注册清单、个人邀请码与 API Key 令牌记录表（不含 DoCode）

## 为什么刚才的邀请码不是你的？

1. **『上游邀请码』（你注册时用）**：刚才表里的 `szt3`、`Z24N`、`MzG9` 等，是爬虫从 `panxunying/ai-coding-welfare` 仓库抓取来的**原项目作者/投稿人的邀请码**。因为绝大多数中转站规定**「新用户必须通过别人的邀请链接注册，才能多领 $7.5 ~ $50 的新客受邀奖励」**（如果走不带码的裸链注册，会直接少拿一大半额度）。
2. **『我的专属邀请码』（你拉新赚钱用）**：只有当你自己在某个中转站完成注册、登录后台的**「钱包 / 邀请 / 个人中心 (Personal / Affiliate)」**页面后，系统才会为你生成属于你自己的专属邀请码。
3. **安全提醒**：我不能登录你的私人邮箱代收验证码或绕过人机验证代注册；**请务必尽快前往 QQ 邮箱「设置 -> 账号」停用或重置你刚才发出的 16 位授权码**。

---

## 如何把数据库和看板里的链接一键换成『你自己的邀请码』？

我已经为项目的 SQLite3 数据库（`ai_relays.db`）升级了 3 个专属字段：`my_invite_code`（我的邀请码）、`my_invite_url`（我的推广链接）、`my_api_key`（我的 API Key）。

当你注册好任意一个站点、在后台拿到你自己的邀请码或 API Key 后，只需运行以下命令，系统就会**自动把原来的他人邀请码替换成你的邀请码，并重新生成 JSON 和 HTML 看板**：

```bash
# 把某站点的推广链接一键替换为你自己的邀请码（例如把 agentrouter 的邀请码换成你的 MYCODE88）
python main.py --set-my-aff agentrouter MYCODE88

# 把你在该站点创建的 API Key 令牌存入 SQLite3 数据库
python main.py --set-my-key agentrouter sk-xxxxxxxxxxxxxxxxxxxx
```

---

## 一、支持 QQ 邮箱直接注册的站点（共 7 个）

> **操作步骤**：先点「步骤1：带福利注册入口」完成注册（蹭满新客受邀奖励） -> 进后台「令牌 / API Keys」新建 Key -> 进后台「个人中心 / 邀请」复制**你自己的邀请码**填在右侧。

| 序号 | 站点名称 (`slug`) | 首日额度 | 步骤1：带福利注册入口（含上游码，注册多拿额度） | 后台获取『我的邀请码』位置 | 我的专属邀请码 (`my_invite_code`) | 我的专属推广链接 (`my_invite_url`) | 我的 API Key 令牌 (`my_api_key`) |
| :--: | :-- | :--: | :-- | :-- | :-- | :-- | :-- |
| 1 | **CheapCodex**<br>(`cheapcodex`) | **$40**<br>(邀请$20+首签$20) | https://api.cheapcodex.online/register?aff=U7SSQZSDB36S<br>*(上游码: `U7SSQZSDB36S`，裸链少$20)* | 登录后台 -> 邀请返利页 | `【待填我的邀请码】` | `https://api.cheapcodex.online/register?aff=【我的码】` | `【待填我的 Key】` |
| 2 | **Codex Relay**<br>(`codex-relay`) | **$10**<br>(注册即送) | https://codex-relay.codes/register?aff=6jAq<br>*(上游码: `6jAq`)* | 控制台 -> 个人中心 / 邀请 | `【待填我的邀请码】` | `https://codex-relay.codes/register?aff=【我的码】` | `【待填我的 Key】` |
| 3 | **Matrix**<br>(`matrix`) | **600 积分**<br>(实名再送2000) | https://matrix.mzsjai.com/login?redirect=%2Fapp%2Fgrowth%3FinviteCode%3DMXMRFO52KD2_<br>*(上游码: `MXMRFO52KD2_`，裸链无600积分)* | 控制台 -> 增长活动 (`/app/growth`)，每邀1人得600积分 | `【待填我的邀请码】` | `https://matrix.mzsjai.com/login?redirect=%2Fapp%2Fgrowth%3FinviteCode%3D【我的码】` | `【待填 Key (mat-开头)】` |
| 4 | **NOFX**<br>(`nofx`) | **15 积分**<br>(邀请10+首签5) | https://nofx.one/zh-CN/sign-in?ref=J369GHY4<br>*(上游码: `J369GHY4`，免密Magic Link)* | 任务中心 (`/zh-CN/tasks`)，每邀1人+5积分、X发推+20积分 | `【待填我的邀请码】` | `https://nofx.one/zh-CN/sign-in?ref=【我的码】` | `【待填我的 Key】` |
| 5 | **MolyEye**<br>(`molyeye`) | **$0.3**<br>(邮箱验证后到账) | https://molyeye.com/register<br>*(无上游码，直接用QQ邮箱注册)* | New API 后台 -> 钱包 / 个人中心 -> 邀请链接 | `【待填我的邀请码】` | `https://molyeye.com/register?aff=【我的码】` | `【待填我的 Key】` |
| 6 | **DSH API**<br>(`dsh-api`) | **按量0.08x**<br>(国模8%官网价) | https://api.dshapi.icu/r/T8KiaeGU<br>*(或无参官网: https://api.dshapi.icu )* | 控制台 -> 邀请返利 | `【待填我的邀请码】` | `https://api.dshapi.icu/r/【我的码】` | `【待填我的 Key】` |
| 7 | **新疆幻城网安网关**<br>(`hcnsec`) | **￥14,600**<br>(注册+邀请各1.46w) | https://api.hcnsec.cn/sign-up?aff=b1KI<br>*(上游码: `MaxS`)* | New API 后台 -> 钱包 / 邀请（邀1人送￥14600） | `【待填我的邀请码】` | `https://api.hcnsec.cn/sign-up?aff=【我的码】` | `【待填我的 Key】` |

---

## 二、仅支持 GitHub / LinuxDO 授权登录的站点（共 8 个）

> **说明**：这 8 个站点关闭了邮箱密码注册（`password_register_enabled = false`），必须用 GitHub 或 LinuxDO 账号一键登录。

| 序号 | 站点名称 (`slug`) | 首日额度 | 步骤1：带福利注册入口（含上游码，拿受邀加成） | 后台获取『我的邀请码』与拉新奖励 | 我的专属邀请码 (`my_invite_code`) | 我的专属推广链接 (`my_invite_url`) | 我的 API Key 令牌 (`my_api_key`) |
| :--: | :-- | :--: | :-- | :-- | :-- | :-- | :-- |
| 8 | **AgentRouter**<br>(`agentrouter`) | **$175**<br>(注册$100+受邀$50+首签$25) | https://agentrouter.org/register?aff=szt3<br>*(上游码: `szt3`，裸链少$50)* | 后台「钱包/个人设置」复制邀请码，**每邀1人你得 $50** | `【待填我的邀请码】` | `https://agentrouter.org/register?aff=【我的码】` | `【待填我的 Key】` |
| 9 | **AnyRouter**<br>(`anyrouter`) | **$150**<br>(注册$75+受邀$50+首签$25) | https://anyrouter.top/register?aff=Z24N<br>*(上游码: `Z24N`，裸链少$50；GitHub不满5年走LinuxDO)* | New API 后台「邀请」页获取邀请码 | `【待填我的邀请码】` | `https://anyrouter.top/register?aff=【我的码】` | `【待填我的 Key】` |
| 10 | **KKtoken AI**<br>(`kktoken`) | **$120**<br>(注册$75+受邀$25+首签$20) | https://kktoken.cc/sign-up?aff=MzG9<br>*(上游码: `MzG9`，裸链少$25)* | New API 后台「邀请」页获取邀请码 | `【待填我的邀请码】` | `https://kktoken.cc/sign-up?aff=【我的码】` | `【待填我的 Key】` |
| 11 | **JustDoWork**<br>(`justdowork`) | **≈$92**<br>(注册$70+首签≈$22) | https://api.justwoker.icu/register?aff=8lTQ<br>*(上游码: `VTrz`)* | New API 后台「邀请」页获取邀请码 | `【待填我的邀请码】` | `https://api.justwoker.icu/sign-up?aff=【我的码】` | `【待填我的 Key】` |
| 12 | **FlushAPI**<br>(`flushapi`) | **$22.5**<br>(注册$15+受邀$7.5) | https://flushapi.fun/sign-up?aff=WBF3<br>*(上游码: `WBF3`，裸链少$7.5)* | 后台复制邀请码，**每邀1人你得 $7.5** | `【待填我的邀请码】` | `https://flushapi.fun/sign-up?aff=【我的码】` | `【待填我的 Key】` |
| 13 | **hiyo free**<br>(`hiyo-free`) | **$25~$30**<br>(注册$20+首签$5~10) | https://free.hiyo.top/register?aff=G4N5JVJ3W7YJ<br>*(上游码: `G4N5JVJ3W7YJ`)* | New API 后台获取个人邀请码 | `【待填我的邀请码】` | `https://free.hiyo.top/register?aff=【我的码】` | `【待填我的 Key】` |
| 14 | **NovAI**<br>(`novai`) | **$2 + 5个免费模型** | https://aiapi-pro.com/register?utm_source=ai_coding_welfare | 控制台查看个人推广链接 | `【待填我的邀请码】` | `https://aiapi-pro.com/register?aff=【我的码】` | `【待填我的 Key】` |
| 15 | **onomeo**<br>(`onomeo`) | **33个免费模型**<br>(每5小时30次) | https://onomeo.com/zh/login | 控制台查看个人账号设置 | `【待填我的邀请码】` | `https://onomeo.com/zh/login` | `【待填我的 Key】` |

---

## 三、需 Telegram 或手机号注册的站点（共 2 个）

| 序号 | 站点名称 (`slug`) | 首日额度 | 步骤1：带福利注册入口 | 后台获取『我的邀请码』方式 | 我的专属邀请码 (`my_invite_code`) | 我的专属推广链接 (`my_invite_url`) | 我的 API Key 令牌 (`my_api_key`) |
| :--: | :-- | :--: | :-- | :-- | :-- | :-- | :-- |
| 16 | **Conduit**<br>(`conduit`) | **$500**<br>(注册即赠) | https://t.me/conduitoff_bot?start=ref_8111640723 | 在 Telegram 机器人内点 Referral / 邀请获取你的 `ref_xxx` | `【待填我的邀请码】` | `https://t.me/conduitoff_bot?start=【我的码】` | `【待填我的 Key】` |
| 17 | **清枢智汇 tierflow**<br>(`tierflow`) | **35 元额度** | https://tierflow.cn/register?referral_code=JtDE1qbaHqhW | 后台复制 `referral_code`，**每天可邀5人，每邀1人送20元** | `【待填我的邀请码】` | `https://tierflow.cn/register?referral_code=【我的码】` | `【待填我的 Key】` |

---

## 四、各站点 API 接入地址速查（拿到 Key 后直接配置客户端）

| 站点名称 | OpenAI 兼容 Base URL（Cursor / Codex / Cherry Studio） | Anthropic 原生 Base URL（Claude Code，不带 `/v1`） |
| :-- | :-- | :-- |
| **AgentRouter** | `https://agentrouter.org/v1` | `https://agentrouter.org` |
| **AnyRouter** | `https://anyrouter.top/v1` | `https://anyrouter.top` |
| **KKtoken AI** | `https://kktoken.cc/v1` | `https://kktoken.cc` |
| **JustDoWork** | `https://api.justwoker.icu/v1` | `https://api.justwoker.icu` |
| **FlushAPI** | `https://flushapi.fun/v1` | `https://flushapi.fun` |
| **CheapCodex** | `https://api.cheapcodex.online/v1` | `https://api.cheapcodex.online` |
| **MolyEye** | `https://molyeye.com/v1` | `https://molyeye.com` |
| **DSH API** | `https://api.dshapi.icu/v1` | `https://api.dshapi.icu` |
| **清枢智汇 tierflow** | `https://tierflow.cn/v1` | `https://tierflow.cn` |
| **onomeo** | `https://onomeo.com/v1` | `https://onomeo.com` |
| **hiyo free** | `https://free.hiyo.top/v1` | `https://free.hiyo.top` |
---

## 五、New-API 站点公开接口（`/api/status` & `/api/verification`）实测结果

针对库内采用开源 **New API / One API** 搭建的站点（除 DoCode 外共 9 个活跃站），已通过脚本直接探测其 `/api/status` 与 `/api/verification` 公开接口，实测结果如下：

| 站点 (`slug`) | 面板架构 | `register_enabled` (开放注册) | `password_register_enabled` (允许邮箱密码建号) | `email_verification` (强制邮箱验证码) | `turnstile_check` (Cloudflare人机锁) | 直接调用公开 API 注册实测结论 |
| :-- | :--: | :--: | :--: | :--: | :--: | :-- |
| **MolyEye** (`molyeye`) | New API | `True` | `True` | `True` | `True` (`0x4AAAAAAFOb9E_0f3k3dv-T`) | 调 `/api/verification` 返回 `{"message":"Turnstile token 为空","success":false}`，必须浏览器真人点过 Cloudflare Turnstile 才能发邮件验证码 |
| **新疆幻城网安** (`hcnsec`) | New API | `True` | `True` | `True` | `True` (`0x4AAAAAAFIovBqwE9xMkrm_`) | 调 `/api/verification` 返回 `{"message":"Turnstile token 为空","success":false}`，必须在浏览器真人点过 Turnstile 才能发验证码 |
| **Codex Relay** (`codex-relay`) | New API (`relay-31f2b8`) | `True` | `True` | `True` | `True` (`0x4AAAAAAFKlKzKi8SKbAV7e`) | 挂有 Cloudflare 盾 + Turnstile 校验，API 裸调直接返回 `HTTP 403 Forbidden`，支持浏览器邮箱或 LinuxDO 登录 |
| **JustDoWork** (`justdowork`) | New API (`v1.0.0-rc.23`) | `True` | **`False`** | `False` | `True` (`0x4AAAAAAEQ0v37GMr9cC_Kw`) | **已关闭邮箱密码注册**，调 `/api/user/register` 直接拒绝，只能浏览器走 GitHub OAuth（需满365天） |
| **FlushAPI** (`flushapi`) | New API | `True` | **`False`** | `False` | `False` | **已关闭邮箱密码注册**，仅开放 GitHub OAuth 授权建号 |
| **KKtoken AI** (`kktoken`) | New API (`v1.0.0-rc.25`) | `True` | **`False`** | `False` | `True` | **已关闭邮箱密码注册** + Cloudflare 403 拦截，仅开放 GitHub OAuth（需满365天） |
| **AgentRouter** (`agentrouter`) | New API | `True` | **`False`** | `False` | — | **已关闭邮箱密码注册**，仅开放 GitHub / LinuxDO OAuth 授权建号 |
| **AnyRouter** (`anyrouter`) | New API | `True` | **`False`** | `False` | `True` (全站 JS 挑战) | **已关闭邮箱密码注册**，仅开放 GitHub（满5年）/ LinuxDO OAuth |
| **hiyo free** (`hiyo-free`) | New API 魔改 | — | — | — | — | `/api/status` 返回 `HTTP 404`（隐藏了标准公开状态接口），需从网页端注册 |

