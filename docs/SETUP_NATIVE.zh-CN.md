# Auto Quant 新手安装指南

本指南适用于单独提供的原生 `follow-executor` 安装包。组合 `follow-stack` 安装包请使用[零基础容器安装指南](SETUP.zh-CN.md)。不要用本流程直接迁移已有安装。

[English](SETUP_NATIVE.md) | 简体中文

本指南将带你在云电脑上安装 Auto Quant、连接自己的 IBKR **模拟交易账户**，并按需开通 Discord 私信通知。模拟交易使用虚拟账户，请先完成模拟测试，再考虑实盘。你不需要编程经验，也不需要访问源代码仓库。

**希望由 AI 助手带你完成？** 打开[从这里开始](../START_HERE.zh-CN.md)，把提示词粘贴给 Codex、Claude Code 或其他具备终端访问能力的助手。助手可以阅读本指南、执行支持的步骤，并在需要时向你提问。个人登录和手机批准仍由你完成。检查点和继续安装的说明见 [AI 助手指南](AGENT_SETUP.zh-CN.md)。下面的步骤仍可用于手动安装。

你会用**自己的电脑**配置另一台由 Oracle 托管的云电脑。设置完成后，即使自己的电脑关机，Oracle 云电脑仍可继续运行。

| 本指南中的名称 | 含义 |
| --- | --- |
| OCI / Oracle Cloud | 提供云电脑的公司及其管理网站 |
| Instance / VM | 运行 Ubuntu 的云电脑，也叫实例或虚拟机 |
| Terminal / 终端 | 可以粘贴操作指令（命令）的窗口 |
| SSH | 从自己的电脑安全连接 Ubuntu 的方式 |
| IB Gateway | IBKR 提供的程序，让 Auto Quant 连接到你的账户 |
| IBC | 自动打开 Gateway 并请求手机登录批准的辅助程序 |
| Executor / follower / 执行器 | 在你自己的账户中跟随信号的 Auto Quant 程序 |

请按顺序操作。**每次只粘贴一行命令**，按 **Enter（回车）**，等待执行完成。只复制命令本身，不要复制类似 `ubuntu@auto-quant:~$` 的示例提示符。输入密码时，屏幕可能不显示字母或圆点，这是正常现象。出现错误时先停止，不要继续下一步。

- [1. 准备账户和安装文件](#prepare)
- [2. 创建 Oracle 云电脑](#cloud)
- [3. 将安装文件传到 Ubuntu](#transfer)
- [4. 安装 Auto Quant](#install)
- [5. 设置 IBKR 登录和手机批准](#gateway)
- [6. 填写 Auto Quant 设置](#follower)
- [7. 关联 Discord 通知](#discord)
- [8. 检查并开始模拟交易](#paper)
- [9. 日常使用](#daily)
- [10. 备份与更新](#update)
- [11. 常见问题](#help)

<a id="prepare"></a>

## 1. 准备账户和安装文件

**操作位置：你自己的电脑和手机。**

向 Auto Quant 获取下面四项资料，并妥善保存：

| 资料 | 用途 |
| --- | --- |
| `follow-executor-0.3.1-ubuntu24.04-arm64-cp312.tar.gz` | 安装压缩包，请保留原文件名 |
| 配套的 `.tar.gz.sha256` 文件 | 一个小文件，让 Ubuntu 检查下载是否完整、是否发生变化 |
| 你的个人 relay token 和预期的 leader 公钥指纹 | 私人接入码，以及核对信号提供方身份的标识 |
| Auto Quant Discord 邀请链接 | 仅在需要交易私信时使用 |

将**两个下载文件**都放到自己电脑的 **Downloads（下载）**文件夹。保持 `.tar.gz` 为压缩状态，之后会在 Ubuntu 上解压。请通过 Auto Quant 可信的下载渠道获取这两个文件。

另外准备好 **IBKR 模拟交易登录凭据**、对应的**账户 ID**，以及手机上的 **IBKR Mobile**。确认账户支持所需期货品种，并启用了 **IB Key / 手机推送批准**。登录时需要用户名和密码；配置 Auto Quant 时另需账户 ID，例如 `DU1234567`。请使用专门用于跟随的账户，无关的 MNQ/NQ 订单或持仓可能导致 Auto Quant 暂停并要求检查。

先完成 [IBKR 附加账户与第二用户名准备](IBKR_ACCOUNT_SETUP.zh-CN.md)，Gateway 和手机交易使用不同用户名，并核验模拟访问权限。

**可以继续的标志：** 两个文件、Auto Quant 接入资料和可正常登录的模拟账户均已准备好。第 5 步会在自己的电脑上安装远程桌面查看器。

<a id="cloud"></a>

## 2. 创建 Oracle 云电脑

**操作位置：先用自己电脑的浏览器，再用终端。**

打开 [Oracle 云电脑图文指南](OCI_ARM.zh-CN.md)，按说明完成：

1. 注册 Oracle 账户，主区域建议 San Jose；双重验证先勾选离线验证器选项。
   创建 VCN 前完成付款方式及 Pay As You Go 升级并确认成功。
2. 创建网络，只允许自己的电脑连接。
3. 使用 **Ampere A1** 创建 **Ubuntu 24.04 LTS ARM64**。
4. 保存 SSH 私钥并连接 Ubuntu。

图文指南包含注册、网络、实例页面、Ubuntu 镜像选择和密钥下载的官方截图。起步配置为 **2 个 OCPU / 12 GB 内存**；创建前请核对 Oracle 费用及可用容量，不保证一定能免费获取。

如果你已有虚拟机，可直接查看图文指南中的[连接步骤](OCI_ARM.zh-CN.md#oci-connect)和[验证步骤](OCI_ARM.zh-CN.md#oci-check)。此安装包要求 **Ubuntu 24.04**、**ARM64/aarch64** 和 **Python 3.12**，请继续使用 Python 3.12。安装过程需要联网。

**可以继续的标志：** 已打开 Ubuntu 连接，看到类似 `ubuntu@auto-quant:~$` 的提示符。把这个窗口称为 **窗口 A — Ubuntu**，请保持打开。

<a id="transfer"></a>

## 3. 将安装文件传到 Ubuntu

现在需要**两个终端窗口**。这一部分最容易把命令粘贴到错误的电脑：

| 窗口 | 控制哪台电脑 | 用途 |
| --- | --- | --- |
| **A — Ubuntu** | 云电脑；提示符通常以 `ubuntu@` 开头 | 安装和运行 Auto Quant |
| **B — 自己的电脑** | 新打开的 PowerShell 或 Terminal 窗口 | 传送安装文件，之后建立远程桌面连接 |

**在窗口 A — Ubuntu 中**，创建用于接收文件的文件夹：

```bash
mkdir -p ~/Downloads
```

**在自己的电脑上打开窗口 B。** Windows：再开一个 PowerShell 窗口；Mac：再开一个终端窗口。此时不要在里面运行 SSH。以下命令假设两个安装文件和 OCI 指南中的 **auto-quant.key** 都在自己电脑的 Downloads 文件夹中。

```bash
cd ~/Downloads
```

将 `YOUR_OCI_PUBLIC_IP` 替换成实例的**公网 IPv4 地址**，然后将下面的命令作为**完整一行**粘贴。`scp` 表示“安全复制文件”。保留末尾的冒号和 `Downloads/`。

```bash
scp -i ./auto-quant.key follow-executor-0.3.1-ubuntu24.04-arm64-cp312.tar.gz follow-executor-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256 ubuntu@YOUR_OCI_PUBLIC_IP:Downloads/
```

等待两个文件都传送完成。如果首次连接要求确认，请先核对地址是否属于你的实例，再接受。

**回到窗口 A — Ubuntu**，检查下载文件：

```bash
cd ~/Downloads
sha256sum --check follow-executor-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256
```

你应看到压缩包名称后显示 **OK**。这能发现下载不完整或文件被更改的问题；你不需要理解或手动输入那串很长的校验值。如果显示 **FAILED**，请停止，从 Auto Quant 重新下载这两个文件。检查通过后，再解压到长期使用的安装位置：

```bash
mkdir -p ~/auto-quant
tar -xzf follow-executor-0.3.1-ubuntu24.04-arm64-cp312.tar.gz -C ~/auto-quant
cd ~/auto-quant/follow-executor-0.3.1-ubuntu24.04-arm64-cp312
./install.sh --verify-only
```

**可以继续的标志：** 最后一条命令显示 **Release checksums, OS, architecture and Python bytecode version verified.**，表示文件、系统、架构和 Python 字节码版本检查通过。请使用全新的安装文件夹，不要混入旧文件，安装后也不要移动它。

<a id="install"></a>

## 4. 安装 Auto Quant

**操作位置：窗口 A — Ubuntu，保持在第 3 步的安装文件夹中。**

```bash
./install.sh
```

安装器会下载需要的软件。等待它完成；屏幕滚动显示文字是正常现象。如果 Ubuntu 要求 sudo 密码，指的是 Ubuntu 用户密码，不是 Oracle 或 IBKR 密码。新的 OCI Ubuntu 账户通常通过 SSH 密钥访问，可能不会询问密码。

请按原样运行命令，**不要**额外添加 `sudo` 前缀：`./install.sh`、`./follow` 和 `./scripts/gateway-desktop.sh` 会自行请求所需权限。

**可以继续的标志：** 看到 **Installed** 和 **Trading has not been started**。安装不会下单，稍后才会填写账户资料。

<a id="gateway"></a>

## 5. 设置 IBKR 登录和手机批准

**可选容器试用：** 在兼容的模拟账户测试机器上，可以用 [Gateway 容器指南](GATEWAY_DOCKER.zh-CN.md)
替代整个第 5 步，完成后返回第 6 步。该方案下载固定摘要的镜像，省去手动安装 Gateway 和完整 Ubuntu 桌面。
下方步骤适用于原生安装包；新组合包客户使用[零基础指南](SETUP.zh-CN.md)。
继续已有安装时保留已选择的后端。

你将短暂使用远程桌面查看 Gateway 登录窗口。它显示的是 Ubuntu 云电脑的屏幕，而不是你自己电脑的桌面。

### 5a. 准备远程桌面

**在窗口 A — Ubuntu 中运行：**

```bash
./scripts/gateway-desktop.sh
```

按提示设置并确认 **VNC 密码**。这是新设置的远程桌面密码，不是 IBKR 密码。如果询问是否设置 view-only（仅查看）密码，请选择 **n**，因为你需要在桌面上点击和输入。等待脚本完成，它会下载并检查支持的 Gateway 安装器。

**在自己的电脑上**安装 VNC 查看器（如果尚未安装）。可以使用 [TigerVNC 官方网站](https://tigervnc.org/)提供的 Viewer，选择适合自己电脑操作系统的版本。自己的电脑只需要查看器。

**在窗口 B — 自己的电脑中**，保持在 Downloads 文件夹，替换公网 IP 后运行：

```bash
ssh -i ./auto-quant.key -N -L 5901:127.0.0.1:5901 ubuntu@YOUR_OCI_PUBLIC_IP
```

这会建立远程桌面的私密连接。**窗口没有输出、一直没有返回提示符是正常的，请保持打开。** 连接运行期间，不要在这个窗口输入后续命令。不要在 Oracle 防火墙开放 5901 端口。

打开查看器。**TigerVNC** 的地址填写 **localhost::5901**（两个冒号用于指定端口）；如果查看器把主机和端口分成两个输入框，分别填写 **localhost** 和 **5901**。输入刚才设置的 **VNC 密码**。

**检查点：** 你能看到 Ubuntu 桌面。如果看不到，请先按文末的常见问题处理，再继续。

### 5b. 在 Ubuntu 桌面中安装 Gateway

**操作位置：VNC 查看器显示的远程桌面。** 打开 **Applications → Terminal Emulator（终端模拟器）**，或点击桌面终端图标，然后运行：

```bash
sh ~/Downloads/ibgateway-latest-linux-arm.sh
```

按安装器提示操作，阅读 IBKR 条款，同意后继续。安装位置应在你的 Ubuntu 用户目录下，通常是 **~/Jts/ibgateway/1051**；如果另选位置，请记下来。本版本使用 **Gateway 10.51 ARM64**。

如果安装完成后自动打开 Gateway，**先关闭这个 Gateway 窗口**，再进行下一步。保持 Ubuntu 桌面运行，不要注销桌面。如果此前已在同一 Ubuntu 用户下安装完全相同的 Gateway 版本，使用原安装路径即可，不必再装一份。

### 5c. 选择账户和手机批准时间

**回到窗口 A — Ubuntu：**

```bash
./follow gateway configure
```

方括号中的内容是建议答案。直接按 **Enter** 接受，或输入替代值。首次设置模拟账户时：

| 提示 | 如何填写 |
| --- | --- |
| Gateway installation directory | 如果使用 `~/Jts/ibgateway/1051`，直接按回车；否则填写你记下的安装路径 |
| Account mode | `paper` |
| Schedule timezone | 按回车使用 `America/New_York` |
| Daily automatic restart | 按回车使用 `23:45`，或选择自己不交易的时段 |
| Sunday mobile approval time | 按回车使用 `12:00` |
| IBKR login username / password | 模拟账户的登录凭据，输入时不显示 |

默认周日登录时间为**美国东部时间中午 12:00**，每日重启为**东部时间 23:45**。冬季使用 EST，夏季使用 EDT。自己电脑或虚拟机的时区不会改变这一计划。例如，东部中午通常是**美国太平洋时间上午 9:00**。重新配置时，已保存的计划会作为默认值保留。[修改时间的详细说明](IBC.zh-CN.md)

IBC 将 IBKR 登录资料私密保存在**你自己的虚拟机**上，用于启动 Gateway 并请求认证。这些资料不会发送给 Auto Quant 或 Discord，你仍需在手机上批准请求。通行密钥等其他认证方式可能还需要在远程桌面中操作。

### 5d. 启动 Gateway 并在手机批准

**在窗口 A — Ubuntu 中运行：**

```bash
./follow gateway start
./follow gateway logs
```

在**手机上的 IBKR Mobile** 中批准通知。观察远程桌面中的 Gateway，处理剩余的 IBKR 提示。如果要求确认自动重启，请点击一次 **OK**。

<a id="gateway-api"></a>

#### 检查 Gateway 的 API 设置

**操作位置：VNC 远程桌面中的 IBKR Gateway 窗口。** 使用 **IB API** 模式。以下设置让 Auto Quant 连接 Gateway 并提交订单。

1. 在 Gateway 窗口顶部点击 **Configure（配置）**，再点击 **Settings（设置）**。

   ![IB Gateway：打开 Configure 菜单，再点击 Settings](images/ib-gateway-configure-menu.png)

2. 在左侧列表中展开 **API**，点击它下面的 **Settings**。

   ![IB Gateway API 设置：Read-Only API 不勾选，Socket port 为 4002](images/ib-gateway-api-settings.png)

   图中使用模拟账户。即使从 IB Gateway 打开设置，窗口标题仍可能显示 “Trader Workstation Configuration”。

3. 按下表检查。如果某个勾选框已经符合要求，就保持原样；再次点击会把它改成相反状态。

| 设置 | 模拟账户应使用 |
| --- | --- |
| Read-Only API（只读 API） | **不勾选**：小方框里不能有勾，这样程序才能下单 |
| Socket port（连接端口） | 本次模拟账户设置使用 **4002** |
| Allow connections from localhost only（仅允许本机连接） | **勾选**；看不到时向下滚动 |
| Trusted IPs（受信任的 IP） | **127.0.0.1**；看不到时向下滚动 |

仅允许本机连接和受信任 IP 的设置位于截图未显示的下方区域。

**找不到 “Enable ActiveX and Socket Clients” 勾选框？** 这是 IB Gateway 的正常情况：API 连接功能已自动启用，此 Gateway 界面不需要另行打开 ActiveX 选项。[IBKR 官方说明](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/)

点击 **Apply（应用）**，再点击 **OK（确定）** 保存。如果看不到底部按钮，请在远程桌面中放大设置窗口，或把窗口向上移动。其他选项保持原值即可。

IBC 会自动设置 API 端口和受信任地址；首次登录时仍请检查。不要向公网开放 **4001、4002 或 5901**。实盘使用 4001，但本指南请继续使用模拟模式。

在**窗口 A 中按 Ctrl+C** 退出滚动日志，这不会停止 Gateway。**可以继续的标志：** Gateway 已登录模拟账户，没有待处理的登录对话框。服务显示“运行中”本身不能证明登录成功，Gateway 登录也不会启动 Auto Quant 交易。

<a id="follower"></a>

## 6. 填写 Auto Quant 设置

**操作位置：窗口 A — Ubuntu。**

```bash
./follow configure
```

| 提示 | 如何填写 |
| --- | --- |
| Account mode | `paper` |
| IBKR account ID | Gateway 中显示的模拟账户，例如 `DU1234567`；它**不是**登录用户名 |
| Sizing | 按订阅约定选择 `balance`（默认：按余额交易 NQ 加 MNQ 余数）或固定数量的 `MNQ`/`NQ` |
| Leverage fraction | 选择 `balance` 时：你选择的数字，大于 0 且不超过 1；`1` 表示完全按领单方 6 倍仓位。随后是可选的预览提示，按回车可跳过 |
| Number of contracts | 选择固定数量时：你选择的整数合约数量，建议输入框的默认值为 1 |
| Personal relay token | Auto Quant 提供的私人接入码，输入时不显示 |

常用的服务地址和信号流已经预设。如果 Auto Quant 特别提供了自定义连接资料，首次设置时才使用 `./follow configure --advanced`，普通服务不需要它。

**可以继续的标志：** 保存结果显示正确的数量、品种及 **paper** 模式。如果选错账户或模式，请停止并按[切换账户说明](OPERATIONS.zh-CN.md)处理。对已有配置重新运行此向导，只能更改品种和数量，不会替换账户。

<a id="discord"></a>

## 7. 关联 Discord 通知（可选）

不需要 Discord 通知可以跳到第 8 步。**每位跟随者使用自己的 Discord 账户，不需要创建机器人，也不需要填写机器人 token。**

1. 在自己的电脑或手机上登录 Discord，或创建账户。
2. 接受 Auto Quant 邀请，进入 **Auto Quant** 服务器。
3. 在 Discord 隐私设置中，允许该服务器成员发送私信。
4. 保持 Auto Quant 停止，在**窗口 A — Ubuntu** 中运行：

```bash
./follow discord link
```

阅读将共享哪些信息，同意后输入 **LINK**。共享内容包括持仓方向、交易数量、入场/平仓价、毛盈亏、Gateway/服务状态、在线心跳及事件时间。一次性关联码会显示在**窗口 A**，十分钟后失效。

5. 在 Discord 中打开 **Auto Quant → #bot-setup**。
6. 输入 `/link`，选择 **AQ Bot** 的命令，把一次性关联码粘贴到 **code** 字段，然后提交这条斜杠命令。不要把关联码当作普通聊天消息发送到频道。

   ![Discord 的 #bot-setup 频道：AQ Bot 的 /link 命令及 code 输入框](images/discord-bot-setup-link.png)

   `xxxxxxx` 只是占位示例，请填写**你自己的窗口 A — Ubuntu 终端**刚显示的关联码。图中的 **Edit Channel（编辑频道）** 按钮属于服务器管理员视图，跟随者不需要编辑频道。

7. 查看私密确认回复和 AQ Bot 发来的测试私信，也请检查 Discord 的消息请求。
8. 回到**窗口 A — Ubuntu** 运行：

```bash
./follow discord status
./follow discord enable
```

**可以继续的标志：** 已收到测试私信，并成功启用通知。否则请查看 [Discord 指南](DISCORD.zh-CN.md)，或请 Auto Quant 检查频道权限。关联账户不会启动交易。

开始交易后，私信会根据已确认的成交显示 **LONG（多头持仓）**、**SHORT（空头持仓）** 或 **FLAT（已平仓）**。每条 FLAT 都包含整笔交易的 **Gross P/L（美元毛盈亏，未扣佣金和费用）**，包括分批平仓。止损挂单和追踪止损更新不再发通知，但止损实际成交并完全平仓时仍会发送 FLAT。Discord 可能延迟，实际持仓应以 IBKR 为准。

AQ Bot 还会报告 Gateway/API 或行情问题、经核实的恢复、Auto Quant 启动/停止及安全暂停，以及信号流中断。只有 API 对账完成且实时行情订阅得到确认，才会报告 Gateway 完全恢复。中继连续三分钟收不到服务心跳时，会提醒服务失联，可能是虚拟机、进程或网络问题；正常停止会取消这项心跳监控。示例及监控范围见[通知指南](DISCORD.zh-CN.md)。

客户安装包 **0.1.7** 需要配合提供方 **0.1.3 或更新版本**的通知服务器。已有客户应在空仓且停止后升级，Discord 关联会保留。请保留交易日志和通知数据库，以保留入场价及历史记录。旧包需要升级才能获得 LONG/SHORT/FLAT 和毛盈亏通知。

<a id="paper"></a>

## 8. 检查并开始模拟交易

**操作位置：窗口 A — Ubuntu。** 首先运行准备状态检查：

```bash
./follow check
```

它会读取券商和中继服务的状态，也可能向 IBKR 请求保证金估算。**它不会提交可执行成交的订单。** 输出可能看起来比较技术化，继续前只需重点核对下表。另外，请确认第 6 步输入的账户 ID 与 Gateway 中显示的账户一致：

| 检查项 | 要求 |
| --- | --- |
| `account_type` | `paper` |
| `root` 和 `quantity`，或 `sizing` | 与第 6 步选择的固定数量，或杠杆比例及示例权重下的数量一致 |
| `leader_key_id` | 与 Auto Quant 提供的指纹一致 |
| `problems` | 空列表：`[]` |

任何一项错误或检查失败，都应先解决。全部通过且你准备好允许程序提交**模拟订单**后，逐行运行以下命令。如果状态画面显示 **(END)**，请先按 **q** 返回提示符，再运行下一条命令：

```bash
./follow start
./follow service-status
./follow logs
```

**这一步才真正启动交易**，并启用虚拟机重启后的自动启动。符合条件的信号可能立即触发订单，否则程序会等待有效信号。已经错过或过期的入场会被跳过。

按 **Ctrl+C** 退出日志查看，交易仍继续。请在 IBKR 检查实际模拟成交和止损订单；启用了私信的话，也检查通知。不要因为安装成功就直接切换实盘：先完成包含登录、订单、止损和重连在内的完整模拟测试。实盘账户的独立设置请按[运维指南](OPERATIONS.zh-CN.md)进行。

**安装完成：** Auto Quant 已在云电脑上运行。不再需要操作时，可以关闭自己电脑上的窗口。关闭 VNC 查看器即可，不要注销 Ubuntu 桌面本身。

<a id="daily"></a>

## 9. 日常使用

以后需要操作时，在**自己的电脑上**打开终端并重新连接：

```bash
cd ~/Downloads
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

提示符变为 Ubuntu 后，进入安装文件夹：

```bash
cd ~/auto-quant/follow-executor-0.3.1-ubuntu24.04-arm64-cp312
```

之后在 **Ubuntu 上**使用这些命令：

| 你想做什么 | 命令 |
| --- | --- |
| 查看 Auto Quant 是否运行 | `./follow service-status` |
| 查看近期活动 | `./follow logs`，看完按 Ctrl+C |
| 查看保存的本地状态或停止原因 | `./follow status`，这不是券商的实时持仓报告 |
| 检查 Discord 关联 | `./follow discord status` |
| 查看 Gateway 服务和已保存计划 | `./follow gateway status`，登录状态仍需单独核实 |
| 停止 Auto Quant 并取消自动启动 | `./follow stop` |

**停止 Auto Quant 不会平仓，也不会取消订单。** 请在 IBKR 查看真实持仓。计划修改设置时，请等到**没有持仓，也没有尚未完成的订单**，这叫 **flat（空仓且无挂单）**。程序停止期间，无法更新止损或执行定时退出。不要把 `./follow resume` 当作普通重启命令；恢复操作可能接管并关闭券商持仓。

每周日**东部时间中午**的登录通常需要手机批准，虚拟机重启或 IBKR 另行要求认证时也可能如此。请在 IBKR Mobile 中批准，IBC 不能代替你确认。交易期间保持虚拟机运行。如果登录卡住，按第 5a 步重新打开私密桌面并检查 Gateway。

要更改每周时间，先确保空仓且无挂单，再运行 `./follow stop` 和 `./follow gateway stop`。运行 `./follow gateway configure`，填写所需的 IANA 时区及 24 小时制周日时间；其他想保留的设置直接按回车。然后运行 `./follow gateway start`，批准登录，运行 `./follow check`，确认通过后才运行 `./follow start`。[IBC 指南](IBC.zh-CN.md)解释了允许的时间及恢复方法。

要修改数量，请在空仓且无挂单、Gateway 已登录的情况下使用：

```bash
./follow stop
./follow settings --quantity 2
./follow check
./follow start
```

**2** 只是示例，不是交易建议。若同时修改品种，可用 `./follow settings --root NQ --quantity 1`。如果更改被拒绝，旧设置会保留；请先阅读错误再重试。

<a id="update"></a>

## 10. 备份与更新

安装文件夹中保存程序。你的私人设置和交易历史位于 Ubuntu 中另外两个文件夹：

| 文件夹 | 内容 |
| --- | --- |
| `~/.config/follow-executor/` | 设置、relay token、IBC 登录凭据及 Gateway/桌面配置 |
| `~/.local/state/follow-executor/` | 交易历史、待发通知和配套数据库文件 |

请将**这两个文件夹一起做私密备份**。其中包含敏感资料，不要上传到公开支持频道。如果不会复制文件夹，请先请 Auto Quant 协助完成私密备份，再更新。

更新前，在 IBKR 确认没有持仓和未完成订单。依次运行 `./follow stop`、`./follow gateway stop`，并在停止状态下备份。获取 Auto Quant 新的安装包和校验文件，使用**新版本文件名**重复第 3 步，并安装到独立的**新版本文件夹**。

运行新文件夹中的 `./install.sh`，它会沿用已有设置和历史，并更新启动路径。不要复制旧 `.venv` 文件夹。按顺序启动 Gateway、批准登录、运行检查，最后从新文件夹启动 Auto Quant。确认新版本正常之前，保留旧版本。

不要通过删除交易历史来消除错误，也不要在同一账户同时运行两份程序。回退版本前请先联系 Auto Quant；发生新交易后还原旧历史，会造成记录状态错误。如果从手动登录 Gateway 的 0.1.0 版本升级，请查看 [IBC 迁移说明](IBC.zh-CN.md)。

<a id="help"></a>

## 11. 常见问题

| 现象 | 下一步 |
| --- | --- |
| `./follow: No such file or directory` | 在 Ubuntu 中运行第 9 步的 `cd` 命令，进入安装文件夹。 |
| SSH 超时或拒绝密钥 | 查看 [OCI 常见问题表](OCI_ARM.zh-CN.md#oci-help)。 |
| 校验或验证失败 | 先停止，重新获取配套安装包和校验文件，确认 Ubuntu 24.04 ARM64 / Python 3.12。 |
| VNC 无法连接 | 保持窗口 B 的 SSH 连接打开，检查 TigerVNC 地址 `localhost::5901`，并使用 VNC 密码。不要开放公网 VNC 端口。 |
| SSH 转发提示 “Address already in use” | 之前的连接可能还开着；关闭旧的转发窗口后重试，不要修改 Oracle 防火墙。 |
| 没有 IBKR 手机请求，或 Gateway 拒绝连接 | 在远程桌面查看 Gateway，并运行 `./follow gateway logs`；确认模拟账户已登录，端口为 4002。 |
| Relay unauthorized | 请 Auto Quant 检查订阅和 token，不要把 token 发到聊天频道。 |
| 没有 `/link` 命令或测试私信 | 使用 #bot-setup，选择 AQ Bot，获取新关联码，并检查 Discord 私信权限和消息请求。 |
| 检查显示问题，或交易停止 | 查看 `./follow logs` 和 `./follow status`，在 IBKR 核对账户，再提供准确错误求助。不要删除状态文件或反复运行 resume。 |

求助时请说明**步骤编号**、当时是在**自己的电脑还是 Ubuntu**上操作，以及**错误文字**。截图中请隐藏登录资料、私钥、relay token 和一次性关联码。

更多说明：[IBC 与手机批准](IBC.zh-CN.md)、[Discord](DISCORD.zh-CN.md)、[日常运维与切换账户](OPERATIONS.zh-CN.md)、[执行器行为](EXECUTOR.zh-CN.md)。

## 源代码与许可

客户执行器采用 GPL-3.0-or-later。安装包包含匹配的应用源码，依赖源码在同一个
发布页面提供。安装时不需要阅读或编译源码。参阅[源码与许可说明](SOURCE.zh-CN.md)。
