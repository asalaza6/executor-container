# 从这里开始——安装 Auto Quant

[English](START_HERE.md) | 简体中文

**先使用 Codex 或 Claude Code。**将解压目录作为工作区打开，并粘贴第 2 步的提示，
让助手从零开始带你设置。[零基础安装指南](docs/SETUP.zh-CN.md)包含 Windows／Mac
打开终端、连接 Ubuntu、上传安装包及回答向导的步骤。Gateway 和执行器均使用容器，
[English guide](docs/SETUP.md)。

**已经在运行 0.1.12、0.2.0 或 0.3.0？** 不要重新安装。请在空仓时按[升级指南](docs/UPGRADE.zh-CN.md)操作：它会保留交易日志、令牌和仓位设置，安装本安装包，并重新生成服务。[Upgrade guide (English)](docs/UPGRADE.md)。

如果压缩包以 `follow-executor-…` 而非 `follow-stack-…` 开头，请使用
[原生指南](docs/SETUP_NATIVE.zh-CN.md)。下方 AI 流程适用于两种安装包，
助手必须先识别类型再选择命令。

请使用具备文件和终端访问能力的 Codex 或 Claude Code 阅读指南并带你完成设置。你不需要事先读完整份指南。助手会执行它能完成的技术步骤，并解释哪些浏览器、终端或手机操作需要你参与。

## 1. 准备资料

向 Auto Quant 获取**安装压缩包及配套校验文件**、个人 relay token、预期的信号提供方公钥指纹，以及可选的 Auto Quant Discord 邀请。保留原始下载文件，并准备好 IBKR Mobile。尚无 IBKR 账户或模拟登录时，让助手先从[账户准备](docs/IBKR_ACCOUNT_SETUP.zh-CN.md)开始。

你需要自己拥有 AI 工具的使用权限；Auto Quant 不会安装 AI 工具，也不包含其订阅。请按工具自身的流程登录。工具需要能够读取安装包，并在你的电脑或 Ubuntu 云电脑上运行命令。只能阅读附件的聊天工具可以解释步骤，但不能直接安装到你的云电脑。

## 2. 在 AI 工具中打开安装包

在**自己的电脑**上，把压缩包的一份副本解压到文件夹，让助手读取，并将此文件夹作为工具的项目或工作区打开。本机副本用于阅读；实际安装必须在 **Ubuntu 24.04 ARM64、Python 3.12** 上进行。请保留原始压缩包和校验文件，之后验证并传到 Ubuntu。

如果已在 Ubuntu 云电脑上解压，也可以在那里打开 AI 工具。如果助手运行在自己的电脑上，可以在你已有虚拟机和可用 SSH 连接后，通过 SSH 操作。告诉它私钥的**文件位置**，不要提供私钥内容。助手应先帮助你建立连接，再安装软件。

安装包包含面向客户设置的 `AGENTS.md` 和 `CLAUDE.md` 入口说明。即使工具会自动加载这些文件，也请粘贴下面这段提示，确保它阅读指南：

> 请使用这个安装包帮我设置 Auto Quant。先阅读 `docs/AGENT_SETUP.zh-CN.md` 和
> `docs/SETUP.zh-CN.md`。请用中文交流，假设我从未用过 shell 或命令行。根据 `RELEASE.json` 识别安装包：
> 组合包用 `follow-stack setup`，原生包用 `docs/SETUP_NATIVE.zh-CN.md`。先询问我使用什么电脑、是否已有
> Ubuntu 云电脑，再检查哪些步骤已经完成。请执行你能完成的技术步骤，并在需要时询问缺少的信息。
> 新 OCI 账户建议选择 Home Region 为 US West (San Jose)，us-sanjose-1。
> Oracle Mobile 双重验证时，先让我勾选 “Offline mode or use another authenticator app” 再扫码。
> 创建任何 VCN 前，先指导我进入 Billing & Cost Management → Upgrade and Manage Payment，
> 添加或核对付款方式，阅读接受费用和条款，并等待 Plan Type 从 Free Tier 变为 Pay As You Go。
> 新 Ubuntu ARM64 实例使用 2 OCPU、12 GB 内存。按 `docs/IBKR_ACCOUNT_SETUP.zh-CN.md`，
> 在 Settings 中 Open an Additional Account，并到 User icon → Settings → User & Access Rights → Users → “+” Add，
> 为我创建第二用户名。Gateway 与手机交易使用不同用户名，向导前核验模拟登录和账户。
> 选择 Futures，由我如实填写经验年数，确有数年经验才选对应区间。
> 点击 Market Data API Acknowledgement 和 Market Data Subscriber Status 的齿轮，完成两份表单，
> 符合资格才在下拉菜单选择 Non-Professional。Level 1 选 CME Real-Time (L1)，
> 非专业公开价每月 $1.55，由我核对实际循环费用并接受，同时验证模拟行情访问。
> 已验证的已有资源和账户应复用，再继续安装。
> 需要我使用浏览器、终端或手机时，每次只给我一个操作。密码和 token 让我直接在自己的终端输入，
> 不要让我发到聊天中，也不要读取凭据文件。先使用模拟交易。在启动任何交易前，展示检查结果，
> 并让我确认账户模式和仓位：我选择的杠杆比例及示例权重下的 NQ/MNQ 数量，或固定数量。容器向导自动配置 Gateway API；如需人工检查，请先展示随附的 Gateway 截图再让我点击。如果我选择 Discord 通知，请在关联 AQ Bot 时展示 #bot-setup 截图。
> 请保留不含秘密资料的私密进度记录，以便以后继续。

如果工具找不到文件，请告诉它解压文件夹的位置。如果它无法使用 SSH 或终端，应明确说明，并引导你在自己的终端执行必要命令。不要给它 Auto Quant 机器人的 token；客户不需要这个 token。

## 3. 回答助手，并完成个人操作

助手会询问电脑类型、已有虚拟机、模拟账户、你的**杠杆比例**（大于 0 且不超过 1；1 表示完全按领单方 6 倍仓位）或固定数量，以及是否需要 Discord 通知。它会检查下载、安装软件，并带你完成现有的设置向导。

Oracle 注册及验证、费用决定、IBKR 条款和登录批准，以及加入和关联 Discord，仍由你完成。当终端步骤需要密码或 token 时，助手应给你命令，让你自己运行。隐藏输入时可能不显示字母或圆点，这是正常现象。完成后回复**已完成**，不要把秘密资料或未遮盖的截图发到聊天中。

默认周日批准时间为**美国东部时间中午 12:00**（`America/New_York`，冬季 EST、夏季 EDT）。需要其他时间时请告诉助手。已有设置应保留已保存的计划。

交易开始前，助手应说明哪些检查通过、哪些步骤仍需你处理。**安装软件和登录 Gateway 都不会启动交易。** 启动 Auto Quant 后可能立即提交模拟订单，并启用虚拟机重启后的自动运行；这一步由你单独决定。

## 暂停或遇到问题时

助手应在 Ubuntu 云电脑上的 `~/.local/state/auto-quant-onboarding/progress.md` 保存私密进度记录，不包含密码、token、账户 ID 或关联码。如果无法保存，应告诉你。开启新会话时，打开同一安装包文件夹，并粘贴：

> 请按照 `docs/AGENT_SETUP.zh-CN.md` 和私密进度记录继续我的 Auto Quant 设置。
> 修改前先重新检查服务的当前状态，告诉我下一个未完成步骤。
> 不要重新安装已完成的部分，也不要未经我确认就启动交易。

助手仍可能遇到不支持的登录界面或云资源容量问题。它应说明具体哪个步骤未完成。向 Auto Quant 求助时，请保留步骤编号和已遮盖敏感信息的错误文字。

如果希望手动安装，请使用[完整安装指南](docs/SETUP.zh-CN.md)。[AI 助手指南](docs/AGENT_SETUP.zh-CN.md)列出了详细检查点。无需访问 Auto Quant 的源码仓库。
