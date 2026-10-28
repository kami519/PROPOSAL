# 收片 ClipDock 项目文档

| 文档 | 面向 | 内容 |
| --- | --- | --- |
| [需求规格说明书](REQUIREMENTS.md) | 用户、验收人员 | 原始需求、范围、用户流程、功能模块、验收标准 |
| [方案设计说明书](DESIGN.md) | 开发、维护人员 | 技术路线、架构、模块、接口、数据结构、部署与风险 |
| [产品与技术方案](PROPOSAL.md) | 评审人员 | 参考站拆解、视觉系统、范围与分期方案 |
| [本次优化说明](04-本次优化.md) | 开发、验收人员 | 阅读模式、完整文案、缓存与提速变更 |
| [并行任务与任务中心方案](05-并行任务与任务中心.md) | 评审、开发人员 | 并行总结、任务中心、批量入队、取消重试与持久化方案（已实现） |
| [项目 README](../README.md) | 使用、部署人员 | 安装启动、环境变量、API、测试和限制 |

## 文档状态

- Phase 1 已实现。
- 并行任务与任务中心已实现（2026-10-28）：后端 57 个测试通过，前端构建与 lint 通过。
- 需求文档与设计文档已在 2026-10-28 整理归档。
- 当前后台服务已启动；AI 总结与完整文案需配置 `SUMMARY_API_KEY` 后启用。
- 当前实现包含 57 个后端测试、前端构建与 lint；并行任务中心已用 Headless Edge 做页面联调。
- 私人免费版：下载、暂停/继续/取消、AI 视频总结、AI 完整文案、Markdown 笔记仓库，没有 Pro 付费墙、邀请码或价格页。

## 截图

- [桌面首页](screenshots/home-desktop.png)
- [解析结果](screenshots/result-desktop.png)
- [移动端首页](screenshots/home-mobile.png)
- [移动端解析结果](screenshots/result-mobile.png)
- [4K 权限提示](screenshots/quality-notice.png)
- [4K 结果卡](screenshots/result-4k-notice.png)
- [剪贴板中文导致解析失败](screenshots/clipboard-issue.png)
- [AI 完整总结](screenshots/summary-full.png)
- [AI 总结移动端](screenshots/summary-mobile.png)
- [阅读模式：总结](screenshots/workbench-summary.png)
- [阅读模式：完整文案](screenshots/workbench-article.png)
- [阅读模式移动端](screenshots/workbench-mobile.png)
- [笔记仓库列表](screenshots/library-list.png)
- [笔记仓库预览](screenshots/library-preview.png)

## 维护约定

- 需求变化先更新 `REQUIREMENTS.md`，再同步 `DESIGN.md` 和验收项。
- 接口、数据结构或模块职责变化时更新 `DESIGN.md`，不要只改代码。
- 产品范围或视觉方向变化时更新 `PROPOSAL.md`。
- 启动方式和环境变量变化时更新根目录 `README.md`。
