# 将微信读书划线和笔记同步到Notion

## 本 fork 的同步配置

本 fork 已迁移到微信读书官方 API Key 网关（skill 1.0.5）。书架、独立笔记/划线库、阅读统计和热力图均使用 `WEREAD_API_KEY`，不再依赖网页 Cookie 或 CookieCloud。

在本仓库 **Settings → Secrets and variables → Actions → Repository secrets** 配置：

| Secret | 用途 |
| --- | --- |
| `WEREAD_API_KEY` | 从 [微信读书官方入口](https://weread.qq.com/r/weread-skills)获取，只保存在 Secrets |
| `NOTION_TOKEN` | 已授权相关页面和数据库的 Notion integration token |
| `NOTION_PAGE` | 包含书架、独立笔记、划线和统计数据库的总页面链接或 ID |
| `NAME` | 热力图显示名称，可选 |

注意：这里的 `NOTION_PAGE` 是 Pro 的总页面；不要套用新版普通版填写书架数据库 ID 的配置方式，也不要把 Cookie 填到这个 Secret。

- `read time sync`：UTC 每 3 小时执行，北京时间 02:00、05:00、08:00、11:00、14:00、17:00、20:00、23:00。
- `weread note sync`：每天北京时间 08:00 执行。
- 两条写入任务串行排队；`schedule` 可能因 GitHub 队列延迟。
- 日统计恢复范围为 2025 年起，热力图保留原年份起点并自动延伸到当年。日库的“时长”支持已有数字或文本类型。
- 同步保留历史笔记和划线，不自动建库或修改字段结构；结构不匹配时明确停止。
- `weread authentication diagnosis` 仅供手动只读检查，日志输出接口结构、独立库最新日期、今日时长是否匹配及热力图年份色块，不输出密钥和笔记正文。诊断脚本成功不代表最新日期已满足验收，应查看 `verification` 结果。

Key 被撤销或失效时，在官方入口取得有效 Key 后更新 `WEREAD_API_KEY` 并重跑。服务端要求升级 skill 时，先核对官方文档，再更新 `scripts/gateway.py` 中的版本号。不要在聊天、代码或提交记录中粘贴密钥。

以下保留原项目的介绍与链接。


本项目通过Github Action每天定时同步微信读书划线到Notion。

预览效果：[https://malinkang.notion.site/malinkang/534a7684b30e4a879269313f437f2185](https://malinkang.notion.site/9a311b7413b74c8788752249edd0b256?pvs=25)


## 使用

> [!IMPORTANT]  
> 关注公众号获取教程，后续有更新也会第一时间在公众号里同步。

![扫码_搜索联合传播样式-标准色版](https://github.com/malinkang/weread2notion/assets/3365208/191900c6-958e-4f9b-908d-a40a54889b5e)


## 群
> [!IMPORTANT]  
> 欢迎加入群讨论。可以讨论使用中遇到的任何问题，也可以讨论Notion使用，后续我也会在群中分享更多Notion自动化工具。微信群失效的话可以添加我的微信malinkang，我拉你入群。

| 微信群 | QQ群 |
| --- | --- |
| <div align="center"><img src="https://github.com/malinkang/weread2notion/assets/3365208/e28d1fb8-a861-47e1-b5e8-b25f17a6a285" ></div> | <div align="center"><img src="https://images.malinkang.com/2024/04/b225b17d60670e4a6ff3459bbde80d28.jpg" width="50%"></div> |


## 捐赠

如果你觉得本项目帮助了你，请作者喝一杯咖啡，你的支持是作者最大的动力。本项目会持续更新。

| 支付宝支付 | 微信支付 |
| --- | --- |
| <div align="center"><img src="https://images.malinkang.com/2024/03/7fd0feb1145f19fab3821ff1d4631f85.jpg" width="50%"></div> | <div align="center"><img src="https://images.malinkang.com/2024/03/d34f577490a32d4440c8a22f57af41da.jpg" width="50%"></div> |

## 其他项目
* [WeRead2Notion-Pro](https://github.com/malinkang/weread2notion-pro)
* [WeRead2Notion](https://github.com/malinkang/weread2notion)
* [Podcast2Notion](https://github.com/malinkang/podcast2notion)
* [Douban2Notion](https://github.com/malinkang/douban2notion)
* [Keep2Notion](https://github.com/malinkang/keep2notion)
