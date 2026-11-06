# Auto Quant 安装指南——从未用过命令行也可以开始

[English](SETUP.md) | 简体中文

本指南使用 `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz` 安装包，
将 **Gateway 和 Auto Quant 执行器一起安装在容器中**。先使用 IBKR **模拟账户
（paper）**，不涉及真实资金交易。请用 **Codex 或 Claude Code** 按[从这里开始](../START_HERE.zh-CN.md)
打开安装包并粘贴提示，让助手从零指导。你无需编写代码、使用 GitHub 或构建镜像。

如果你的压缩包以 `follow-executor-…` 开头，请使用[原生安装指南](SETUP_NATIVE.zh-CN.md)。
如果这台虚拟机已经安装 Auto Quant，请先看[更新说明](#update)，不要直接重装。

你用自己的电脑设置一台运行 Ubuntu 的云端电脑。设置完成后，关闭笔记本也不会关闭
云端电脑。Docker 负责运行两个程序，向导会安装所需组件。**安装完成后，交易仍保持停止。**

## 第一次输入命令之前

**终端**是输入或粘贴指令的窗口；这些指令叫做**命令**，输入后按 **Enter（回车）**执行。
不要把命令粘贴到浏览器地址栏或 AI 聊天框中。

- **Windows 10/11：**点击开始菜单，输入 **PowerShell** 并打开。普通窗口即可，
  不需要选择“以管理员身份运行”。
- **Mac：**按 **Command + 空格**，输入 **Terminal（终端）**，按回车。
- PowerShell 用 **Ctrl + V** 或鼠标右键粘贴；Mac 用 **Command + V**。
- 每次只粘贴一行命令，按回车，等它完成再继续。不要复制 Markdown 标记或
  `ubuntu@host:~$` 这样的示例提示符。
- Ubuntu 中以 `$` 结尾的提示符通常表示可以输入命令。如果屏幕正在提问，先回答
  当前问题，不要把下一条命令当作答案粘贴进去。
- 输入密码或 token 时可能**没有任何字符或圆点显示**。这是正常的隐藏输入；
  输入一次再按回车即可。不要把这些内容发送到聊天中。
- `[paper]` 表示直接按回车采用默认值；`[y/N]` 表示只有你想同意时才输入 `y` 并回车。

**SSH** 是连接云端电脑的安全通道；**私钥**是你电脑上的文件，不是 IBKR 密码。
**VM / instance（虚拟机／实例）**就是云端电脑。**Gateway** 登录 IBKR；
**executor（执行器／跟单端）**根据 Auto Quant 信号操作账户。

1. [准备安装包和账户资料](#prepare)
2. [创建或连接 Ubuntu](#cloud)
3. [上传并校验安装包](#transfer)
4. [运行向导，完成首次重启并继续](#install)
5. [填写模拟账户设置](#follower)
6. [完成 Gateway 登录及就绪检查](#gateway)
7. [可选：连接 Discord](#discord)
8. [决定是否启动模拟交易](#paper)
9. [日常使用、更新与帮助](#daily)

请使用 **Codex 或 Claude Code** 按[从这里开始](../START_HERE.zh-CN.md)打开安装包、粘贴提示，
让助手从零逐步带领你设置。本指南也提供手动操作的完整命令。
个人登录及手机操作仍需你自己完成。

<a id="prepare"></a>

## 1. 准备安装包和账户资料

**操作位置：你自己的电脑、浏览器和手机。**向 Auto Quant 获取：

| 资料 | 用途与保存方式 |
| --- | --- |
| `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz` | 保存到电脑的 **Downloads（下载）**文件夹，暂时不要解压。 |
| 匹配的 `.tar.gz.sha256` 文件 | 与安装包放在一起，用于检查下载是否完整且未改变。 |
| 个人 relay token（信号服务访问令牌） | 私密保存，稍后在向导中输入，用于连接信号服务。 |
| 预期的提供方公钥指纹 | 与就绪检查结果对比，确认信号提供方身份。 |
| 支持联系方式及可选的 Discord 邀请 | 使用客户下载渠道提供的联系方式。 |

从 Auto Quant 的可信渠道取得两个下载文件。Discord 可以提供附件或下载链接。
本指南使用 **0.3.1**；如果你拿到的版本不同，请使用该版本包内的指南和匹配文件名，
不要混用不同版本的文件。

先完成 [IBKR 账户及第二用户名准备](IBKR_ACCOUNT_SETUP.zh-CN.md)：
在 **Settings → Open an Additional Account** 开立附加账户，再到
**User icon → Settings → User & Access Rights → Users → “+” Add**，为本人创建第二用户名。
OCI Gateway 与手机交易使用不同登录；手机用 Gateway 的同一用户名交易可能踢掉 Gateway。
已有合适的专用账户及登录时核对并复用。必须单独核验模拟登录，创建实盘第二用户名不代表已获得模拟访问权限。
IBKR 申请中选择 **Futures**，如实填写经验年数，确有数年经验才选择对应区间。
设置前点击 **Market Data API Acknowledgement** 和 **Market Data Subscriber Status** 的**齿轮**，
完成两份表单。符合资格时下拉菜单选 **Non-Professional**，在 **Level 1** 选
**CME Real-Time (L1)**，非专业公开价 **每月 $1.55**；自行确认当前循环费用。
[IBKR 指南](IBKR_ACCOUNT_SETUP.zh-CN.md)说明表单、交易权限及模拟行情访问。

准备好 **专用 IBKR 模拟交易用户名、密码及模拟账户 ID**。账户 ID（例如虚构的
`DU1234567`）**不是登录用户名**。在 IBKR 模拟账户的账户选择器或模拟账户结单中
查找实际 ID。不要照抄示例，也不要填入真实账户 ID。不确定时请联系 Auto Quant
协助确认，不要将账户资料贴到公开聊天中。

账户需要相应的期货交易权限及行情访问权限。不要在该账户混入无关的 MNQ/NQ
持仓或订单。如果你的登录需要 IBKR Mobile 批准，请准备好手机。部分模拟登录
不会触发手机请求，单凭没有通知不能判断登录失败。

Docker Engine 直接从 **Docker 官方 Ubuntu 软件源**下载；Gateway 从固定版本的
上游 **GitHub 容器仓库**下载；执行器镜像已经包含在 Auto Quant 安装包中。
你的笔记本无需 Docker Desktop，也不需要 GitHub 账户。

<a id="cloud"></a>

## 2. 创建或连接 Ubuntu

**操作位置：你自己电脑的浏览器，然后是终端。**按[图文 Oracle Cloud 指南](OCI_ARM.zh-CN.md)
完成注册、费用／容量选择、网络设置、SSH 私钥下载及首次连接。
新账户 Home Region 建议 **US West (San Jose)，`us-sanjose-1`**。
Oracle Mobile 双重验证时，**先勾选 “Offline mode or use another authenticator app” 再扫码**。
**创建 VCN 前**，先到 **Billing & Cost Management → Upgrade and Manage Payment** 添加或核对付款方式，
自行审阅并接受升级费用和条款，等待 Plan Type 从 **Free Tier** 变为 **Pay As You Go**。
详见[必需的付款检查点](OCI_ARM.zh-CN.md#oci-payment)。选择
**Ubuntu 24.04 LTS、Ampere A1 / ARM64**。可从 2 OCPU、12 GB 内存开始；
创建前确认页面显示的费用。

已有虚拟机？按该指南的[连接](OCI_ARM.zh-CN.md#oci-connect)和
[检查](OCI_ARM.zh-CN.md#oci-check)步骤确认：`aarch64`、Ubuntu `24.04`、
Python `3.12`，且时钟已同步。本安装包不支持 AMD64。

以下示例假设私钥名为 **auto-quant.key**，保存在你电脑的 Downloads 文件夹中。
如果文件名不同，换成你的实际文件名。将 `YOUR_OCI_PUBLIC_IP` 替换为实例页面上的
**公网 IPv4 地址**，其余部分保持不变，不要原样输入占位文字。

**在你自己的电脑上：**

```bash
cd ~/Downloads
```

**仅 Mac：**设置私钥文件权限。Windows 跳过这条命令：

```bash
chmod 400 auto-quant.key
```

**Windows 或 Mac：**连接 Ubuntu：

```bash
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

首次连接时，按照 OCI 指南核对主机身份后再回答 `yes`。已有连接突然出现主机密钥
改变的警告，需要先查明原因。如果 SSH 意外要求输入密码，不要输入 Oracle 或
IBKR 密码；按 OCI 指南的故障排查步骤处理。

**本步完成标志：**出现类似 `ubuntu@auto-quant:~$` 的提示符。
将这个窗口称为 **窗口 A——Ubuntu**。此后在这里输入的命令运行在云端电脑上。

<a id="transfer"></a>

## 3. 上传并校验安装包

保持**窗口 A**打开。再在你自己的电脑上打开一个 PowerShell 或终端窗口，称为
**窗口 B——本机**。暂时不要在窗口 B 中运行 SSH。

| 窗口 | 常见提示符 | 用途 |
| --- | --- | --- |
| **A——Ubuntu** | `ubuntu@…:~$` | 安装和操作 Auto Quant |
| **B——本机** | Windows 为 `PS C:\Users\…>`；Mac 为本机名称及 `%` 或 `$` | 上传文件，之后可用于连接恢复画面 |

**窗口 A——Ubuntu：**创建接收文件的目录。

```bash
mkdir -p ~/Downloads
```

**窗口 B——本机：**确认私钥和两个下载文件都在 Downloads 文件夹中。

```bash
cd ~/Downloads
```

替换 IP 占位文字，将下一条作为**完整的一行**粘贴。`scp` 表示安全复制文件，
保留末尾的冒号和 `Downloads/`。

```bash
scp -i ./auto-quant.key follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256 ubuntu@YOUR_OCI_PUBLIC_IP:Downloads/
```

等待两个文件都上传完成。**回到窗口 A——Ubuntu**，一次运行一行：

```bash
cd ~/Downloads
sha256sum -c follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256
```

**本步完成标志：**文件名后显示 **`OK`**。如果显示 `FAILED`，停止操作，从可信
渠道重新获取匹配文件，不要解压或安装校验失败的文件。

解压到 Ubuntu 家目录中的固定版本目录：

```bash
tar -xzf follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz -C ~
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
```

`tar` 或 `cd` 没有输出通常是正常的。保留这个目录的原路径，已安装的 Gateway
服务需要使用它；不要在安装后改名、移动或删除。

<a id="install"></a>

## 4. 启动向导并完成首次重启

**窗口 A——Ubuntu，在解压目录中：**

```bash
./follow-stack setup
```

组合安装包不要加 `sudo`，也不要运行 `install.sh`。向导只在必要时请求权限。
**程序本身目前显示英文**；下面逐项解释屏幕上的英文问题。

在 **`1/5 Docker and startup permissions`（Docker 与启动权限）**阶段：

| 英文提示 | 新建专用虚拟机如何回答 |
| --- | --- |
| `Install Docker from its official Ubuntu repository using sudo? [y/N]:` | 是否从官方软件源安装 Docker：输入 `y` 并回车，等待完成。 |
| `Finish local Docker startup permissions using sudo? [y/N]:` | 是否补全 Docker 权限：如果出现，输入 `y`，完成此前中断的权限步骤。 |
| `Enable services after logout and reboot using sudo? [y/N]:` | 是否允许退出登录或重启后继续运行服务：输入 `y`。 |

首次安装 Docker 或修改权限后，向导可能显示
**`Docker installed. Reboot ... reconnect and rerun './follow-stack setup'.`**
意思是已安装，请重启后重新连接并继续。这是**正常暂停，不是安装失败**。
等 Ubuntu 命令提示符重新出现后再操作。

**对于新建专用虚拟机**，在窗口 A 重启 Ubuntu：

```bash
sudo reboot
```

这会重启云端电脑，不是你的笔记本。出现 `Connection ... closed` 表示连接断开，
属于正常现象。共享虚拟机应先安排维护时间。等待约一分钟，再从自己的电脑连接；
如果仍在启动，稍后重试：

```bash
cd ~/Downloads
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

**看到 Ubuntu 提示符后**，回到同一个目录继续：

```bash
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
./follow-stack setup
```

向导会复用已完成步骤，不必重新上传或解压。
在 **`2/5 Verified executor image and stopped service`（验证执行器镜像并安装停止状态的服务）**
阶段等待完成即可，无需自己构建镜像或登录容器仓库。

<a id="follower"></a>

## 5. 填写模拟账户设置

**窗口 A——回答向导，不要在这些问题处粘贴 shell 命令。**
在 **`3/5 Account and personal relay access`（账户及个人信号服务访问）**阶段：

| 提示 | 回答 |
| --- | --- |
| Account mode `[paper]` | 账户模式：按回车选择模拟交易。 |
| IBKR account ID | 输入模拟账户 ID，不是用户名。 |
| Sizing `[balance]` | 仓位方式：按回车选择余额仓位，即每次新入场时按账户余额计算 NQ 加 MNQ 余数。若要固定交易一种合约，输入 `MNQ` 或 `NQ`。 |
| Leverage fraction of the leader's 6x band | 杠杆比例：输入你选择的数字，大于 0 且不超过 1，例如 `0.5`。`1` 与领单方仓位完全一致，`0.5` 为一半。 |
| Your current IBKR NetLiquidation in USD, for a size preview `(Enter to skip)` | 可选：模拟账户的大致余额，仅用于预览数量，不会保存。 |
| Approximate current NQ price, for the preview `(Enter to skip)` | 可选：例如 `21000`。 |
| Number of contracts (1–10) `[1]` | 仅在选择固定 `MNQ`/`NQ` 数量时询问。 |
| Personal relay token `(hidden)` | 粘贴 Auto Quant 私下提供的个人令牌并回车；输入时可能没有任何显示。 |

选择余额仓位时，预览会显示示例权重下的数量，例如权重 1（最大仓位）为 `1 NQ + 7 MNQ`，
权重 0.25 为 `4 MNQ`。每个信号都带有该笔交易的权重。标为 `no entry` 的权重在该余额下取整为 0 张，使用该权重的交易不会执行。稍后的就绪检查会按你在 IBKR 的真实余额再次显示。MNQ 和 NQ 是不同的期货合约，
一张 NQ 等于十张 MNQ。不确定时先暂停，与 Auto Quant 确认。本指南示例使用
**paper、余额仓位、杠杆比例 0.5**。已有设置会被复用，应核对向导实际显示的内容。
此时还没有启动交易。

<a id="gateway"></a>

## 6. 完成 Gateway 登录及就绪检查

在 **`4/5 Gateway login`（Gateway 登录）**阶段，在窗口 A 私密输入：

| 提示 | 回答 |
| --- | --- |
| Schedule timezone | 时间区域：回车采用 `America/New_York`，即美国东部时间，自动处理夏令时。 |
| Daily automatic restart | 每日自动重启：回车采用东部 `23:45`，通常对应美国太平洋时间晚上 8:45。 |
| Sunday mobile approval time | 周日手机批准时间：回车采用东部 `12:00`，通常对应太平洋时间上午 9:00；需要手机批准的账户请届时在线。 |
| Recovery desktop password | 恢复画面密码：选择**恰好 8 个英文字母和／或数字，不含空格**，不要使用 IBKR 密码。 |
| Confirm recovery desktop password | 再输入一次完全相同的 8 字符密码，两次输入都不可见。 |
| IBKR login username `(hidden)` | 输入模拟交易登录用户名。 |
| IBKR password `(hidden)` | 输入该用户名对应的密码。 |

默认重启时间必须适合你的交易时段。如果不适合，应在启动交易前安排其他时间。
凭据和恢复密码保留在虚拟机上，不要发送给客服或 AI。

向导会下载并启动 Gateway。收到预期的新 IBKR Mobile 请求后及时批准。
**模拟登录可能不发手机请求。**如果没有通知，给登录留出时间，然后在下面的问题处按回车：

```text
After login, press Enter to check readiness, or type later to pause:
```

意思是“登录后回车检查，或输入 later 暂停”。需要查看登录提示时，使用下方恢复画面。
要离开时输入 `later` 并回车：配置已保存，Gateway 保持可用，交易仍停止。
回来后在同一个 Ubuntu 目录运行 `./follow-stack setup` 继续。

在 **`5/5 Relay, account, journal and margin checks`（中继、账户、交易记录及保证金检查）**
阶段，还会检查行情。**完成标志：**显示
**`Setup checks passed, including a live quote for the selected contract.`**
即检查通过，已取得所选合约的实时行情。这里的 **live quote 指实时行情，不是切换到真实交易账户**。

将 `leader_key_id` 与 Auto Quant 提供的预期公钥指纹对比，并确认模拟模式、账户和
仓位：余额仓位时核对 `sizing` 部分的 NetLiquidation、杠杆比例及示例权重下的 NQ/MNQ 数量。失败时查看[帮助](#help)，不要用启动交易绕过检查。

<a id="gateway-api"></a>

### 恢复画面——仅在登录窗口需要处理时使用

向导会自动配置 Gateway API，通常无需桌面或手动调整 API。需要查看未完成的登录时：

1. 在窗口 A 的登录问题处输入 `later` 并回车，回到 Ubuntu 提示符，保留 Gateway 运行。
2. 如果没有 VNC 查看器，在**你自己的电脑**安装例如 [TigerVNC](https://tigervnc.org/)
   的查看器，用它显示远程 Gateway 画面。
3. 在 **窗口 B——本机**的 Downloads 目录中，替换 IP 后运行：

   ```bash
   ssh -i ./auto-quant.key -o ExitOnForwardFailure=yes -N -L 127.0.0.1:5901:127.0.0.1:5901 ubuntu@YOUR_OCI_PUBLIC_IP
   ```

4. 窗口空白、没有新提示符属于正常现象，请保持打开。TigerVNC 连接地址为
   **`localhost::5901`**（两个冒号）；其他查看器填写主机 `localhost`、端口 `5901`。
   输入单独设置的恢复密码。
   macOS 也可在 Finder 按 **Command+K**，连接 **`vnc://127.0.0.1:5901`**。
   SSH 命令必须在 Mac 本机运行，不是在 Ubuntu 或 OCI Cloud Shell 中运行。
   如果提示启用 Screen Sharing／Remote Management，不需要为此开启 Mac 的共享服务；
   先确认窗口 B 的 SSH 连接仍在且没有报错，再在窗口 A 用
   `./follow-stack gateway status` 确认 Gateway 正在运行且已启用恢复画面。
5. 确认模拟登录并自行处理 IBKR 提示。如果客服需要你检查 API 设置，位置如下图：
   **Configure → Settings**，然后 **API → Settings**。不要仅为与截图一致而改变
   账户模式、端口或已有设置。
6. 回到窗口 A，运行 `./follow-stack setup` 完成就绪检查。完成后关闭查看器；
   在窗口 B 按 Ctrl+C 只关闭恢复连接。

![Gateway 的 Configure 菜单，选择 Settings 打开设置](images/ib-gateway-configure-menu.png)

![Gateway API 设置位置，仅在需要排查时查看](images/ib-gateway-api-settings.png)

恢复画面通过 SSH 连接访问。不要在 Oracle 或 Ubuntu 防火墙中向公网开放
5901、4001 或 4002 端口。

<a id="discord"></a>

## 7. 可选：连接 Discord 私信

不需要通知可以跳过。关联后，Auto Quant 通知服务会向你的 Discord 发送交易详情和
服务状态。关联不会启动交易，应在执行器停止时进行。

**窗口 A——Ubuntu，向导结束并回到命令提示符后：**

```bash
./follow-stack discord link
```

阅读并回答同意提示。短期有效的关联码会显示在**你自己的终端**。
在 Discord 加入提供的 Auto Quant 服务器，进入 **#bot-setup**，选择
**AQ Bot 的 `/link` 命令**，将关联码填入 **code** 字段并在十分钟内提交。
不要把关联码作为普通频道消息发布，更不要在那里粘贴 relay token。

![Auto Quant 的 #bot-setup 频道：AQ Bot /link 命令及 code 字段](images/discord-bot-setup-link.png)

截图中的码只是示例，使用你终端中刚生成的码。你不需要“Edit Channel”按钮，也
不需要自己创建 Discord 机器人。等待私密的“Account linked”回复和测试私信（DM）。
然后回到窗口 A：

```bash
./follow-stack discord status
./follow-stack discord enable
```

没有私信时，允许该服务器的私信并查看消息请求。如果 `/link` 显示
“The application did not respond”，联系 Auto Quant，不要重装。
[更多通知帮助](DISCORD.zh-CN.md)。

<a id="paper"></a>

## 8. 决定是否启动模拟交易

安装及券商登录不会自动启动执行器。你可以停在这里，保持“安装就绪、交易停止”。

准备启动时，先在 **窗口 A——Ubuntu** 运行：

```bash
./follow-stack check
```

确认完整检查通过，包括行情、预期的提供方指纹，以及**你选择的模拟模式和仓位**。先解决报告中的问题。检查可能请求保证金估算，但不会提交可执行订单。

启动前阅读[执行器如何保护持仓](EXECUTOR.zh-CN.md)。观察到入场成交后 30 秒仍无
匹配止损，或已有止损意外失效后 60 秒仍未恢复时，本版本会启动紧急平仓。
经验证的计划退出使用自身固定期限；确认空仓后也会清理自己的遗留止损。
这些检查需要执行器保持运行，券商或网络延迟可能延迟实际平仓。

启动后**可能立即提交模拟订单**，并启用虚拟机重启后的执行器自动启动。
如果这正是你的意愿：

```bash
./follow-stack start
```

阅读实际显示的设置。对于 **paper、余额仓位 0.5**，确认文字为 `START PAPER BALANCE 0.5`（固定数量类似 `START PAPER 1 MNQ`）。
只有设置符合你的意愿才输入。如果显示 `LIVE` 或其他数量，不要确认，先寻求帮助。
提示以实际保存的配置为准，不以本指南示例为准。

成功启动后：

```bash
./follow-stack service-status
./follow-stack status
```

服务运行中可能只是在等待下一条符合条件的信号。不要为了看到成交而手动下测试单。

<a id="daily"></a>

## 9. 日常使用和下次回来

每次重新 SSH 登录，通常不在版本目录中。按第 2 步连接后先运行：

```bash
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
```

| 目的 | 命令／操作 |
| --- | --- |
| 交易仍停止时继续未完成的安装 | `./follow-stack setup` |
| 查看 Gateway 登录及 API 健康状态 | `./follow-stack gateway status` |
| 查看执行器服务 | `./follow-stack service-status` |
| 查看交易状态 | `./follow-stack status` |
| 停止时检查完整就绪状态 | `./follow-stack check` |
| 持续查看执行器日志 | `./follow-stack logs`；Ctrl+C 仅退出查看，不停止交易。 |
| 停止跟单并禁用执行器开机自启 | `./follow-stack stop` |

**Stop 不会平仓或撤单。**应检查 IBKR 持仓及订单，按约定的退出流程处理；
“已停止”不代表“空仓”。关闭 SSH 或笔记本也不会停止交易。
不要对正在交易的安装重新运行 setup。

每日重启自动完成。周日计划重启时，如果账户需要手机批准，请及时批准预期的新请求。
未回答的请求会在约五分钟加 60 秒重启等待后自动重新登录一次，通知送达可能更晚。
只批准最新请求；再次超时后需要人工处理。按[登录恢复说明](CONTAINER_SETUP.zh-CN.md)
操作，不要反复重装。

<a id="update"></a>

## 10. 更新或迁移已有安装

首次更新前联系 Auto Quant。保留旧版目录、配置、Gateway 数据及交易记录，不要删除
状态来“从头开始”。原生安装需要审查后的迁移流程，本指南的全新安装步骤不是迁移流程。

**从 0.1.12、0.2.0 或 0.3.0 升级到 0.3.1？** 请按[升级指南](UPGRADE.zh-CN.md)操作。它会保留交易日志和令牌，
安装新安装包并重新生成服务；从 0.1.12 或 0.2.0 升级后再选择杠杆比例。

兼容的容器版本使用[容器维护参考](CONTAINER_SETUP.zh-CN.md)中的停止且空仓更新步骤。
升级本身不代表同意启动交易。不要把私密备份发送到聊天或 Discord。

<a id="help"></a>

## 11. 常见问题

| 现象 | 处理 |
| --- | --- |
| Windows 不认识 `ssh` 命令 | 按 [Microsoft OpenSSH Client 说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)在电脑安装**客户端**，不是服务器，再重新打开 PowerShell。 |
| SSH 超时或 `Permission denied (publickey)` | 按 [OCI 帮助](OCI_ARM.zh-CN.md)检查 IP、用户名 `ubuntu`、私钥文件名及访问规则，不要分享私钥内容。 |
| `No such file or directory` | 检查所在窗口、目录及完整文件名；下载可能被加上 `(1)`，请使用匹配的原始名称。 |
| 找不到 `./follow-stack` | 在窗口 A 先 `cd` 进入解压后的版本目录。 |
| 校验显示 `FAILED` | 停止，从可信渠道重新获取匹配安装包及校验文件。 |
| 输入密码／令牌无显示 | 正常隐藏输入，输入一次后按回车。 |
| 恢复密码长度／字符不符或两次输入不同 | 选择恰好 8 个英文字母／数字，不含空格，两次输入完全一致。向导会重新询问（Gateway 时间表问题会重复，按回车保留默认值），Ctrl+C 暂停。旧版本会报 `Use matching recovery passwords of exactly 8 printable ASCII characters` 并退出；重跑 setup 会复用已保存账户设置。 |
| `Run './follow-stack setup' first`／`Setup is incomplete` | 账户设置可能已保存，但 Gateway 尚未配置完成。运行 `./follow-stack doctor`，用相同 Ubuntu 用户在原目录重跑 `./follow-stack setup`，完成第 4/5 步并等待第 5/5 步检查通过；不要删除已保存配置。 |
| VNC 连接失败／`Address already in use` | 在本机单独的终端窗口保持隧道运行。端口占用可能是已有隧道，不要重复启动或终止不明进程；检查原隧道及 Gateway 状态。不要向公网开放 VNC。 |
| Docker 权限或重启提示 | 按指示重启、重新连接，在同一目录重跑 setup，不要给 `follow-stack` 加 sudo。 |
| 没有 IBKR Mobile 请求 | 模拟登录可能不需要。先尝试就绪检查；登录未完成时查看恢复画面。 |
| `10197`／其他会话占用行情 | 在适当时自行释放其他会话的行情占用再检查；断开真实会话前先确认其用途。 |
| `354`／行情状态 `denied`，但登录和保证金检查通过 | IBKR 表示未订阅所请求的行情。在 Client Portal 的 **Settings → Trading Platform → Market Data Subscriptions** 检查所选合约及 Gateway 登录用户名的实时行情和 API 权限；订阅前确认费用。交易权限、保证金与行情权限是分开的。重跑 `./follow-stack check`；实时行情通过前仍不能启动交易。 |
| 行情超时 | 没有收到可用报价。检查交易时段、行情权限及登录，行情恢复后重试；超时不等于已确认休市。 |
| 已有安装、账户不符、存在持仓／订单或 journal halt | 停止安装并联系支持。不要删除配置／历史，也不要用 `resume` 绕过检查。 |

向支持提供**步骤、版本及脱敏后的错误文字**。去除用户名、账户 ID、令牌、密码、
认证码及关联码。不要上传配置文件夹、原始日志、交易记录或整台虚拟机备份。

## 源代码与许可

客户执行器采用 GPL-3.0-or-later。安装包包含匹配的应用源码，依赖源码在同一个
发布页面提供。安装时不需要阅读或编译源码。参阅[源码与许可说明](SOURCE.zh-CN.md)。
