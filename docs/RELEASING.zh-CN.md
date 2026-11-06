# GPL 客户发布版

[English](RELEASING.md) | 简体中文

所有者已选择让客户执行器采用 GPL-3.0-or-later。信号服务和服务商策略保持独立、私有。
只发布经过审查的公开导出目录，不要发布本 VM 的整个工作目录、Git 历史、用户主目录、
验证记录、凭据或交易日志。参阅[源码与构建说明](SOURCE.zh-CN.md)。

## 构建与验证

0.3.1 是 0.3.0（余额仓位：领单方区间的杠杆比例、每个信号携带的权重以及 NQ + MNQ 组合）的维护版本，不改变交易行为。`follow-stack upgrade` 接受 0.3.0（兼容性摘要相同）、经过审查的 0.2.0 迁移，以及 `maintenance.REVIEWED_GATEWAY_MIGRATIONS` 中经过审查的 0.1.12 Gateway 字节码对。因此 journal、gateway 和 gateway_docker 模块必须与 0.2.0/0.3.0 字节一致；请用 `follow_executor.release.verify_release` 对每个安装包核对。0.3.0 自身的 config/local 摘要不在已审查迁移中，修改上述任一模块也会阻止 0.3.0 升级，除非新增审查条目。使用 Ubuntu 24.04
ARM64、CPython 3.12 和 Docker。同步更新 `pyproject.toml`、启动器/测试的默认镜像
标签和中英文示例中的版本号。旧发布压缩包保持不变。

```bash
.venv/bin/ruff check .
bash -n follow follow-container follow-stack install.sh deploy/install-bytecode.sh scripts/*.sh
.venv/bin/python -m unittest discover -s tests -v
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
curl --fail --location --output /tmp/follow-dependencies.tar.gz https://github.com/quantmnq/executor-container/releases/download/v0.1.12/follow-executor-0.1.12-dependencies.tar.gz
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.3.1 --reuse-archive /tmp/follow-dependencies.tar.gz --reuse-sha256 c2740a33b3f91508c70116d4c0a4389b47fe2fd1748b16b5cf9f480dac0bb769
python3.12 scripts/build-container-kit.py --build dist/executor-container/BUILD.json --third-party dist/third-party/SOURCES.json
python3.12 scripts/build-source.py --output dist/source --export dist/public-repository
```

源码导出只读取 `deploy/public-files.txt` 的明确白名单。不包括 Git 历史、本机配置、
`vendor/`、`dist/`、私有交接文档或任何服务商后台服务。新增应用模块必须加入白名单；
构建器拒绝遗漏模块。审查每个新加入的文件。不要在 VM 工作目录中用 `git add .`
来准备公开仓库。

镜像构建使用最小白名单上下文，加入应用许可元数据，并将官方 IBKR 压缩包中的
LICENSE、NOTICE 和 THIRD_PARTY_LICENSES 保留在最终镜像。不要删除依赖自己的声明。
依赖收集器使用临时容器，只挂载输出目录，下载准确版本的 Debian、Python 和 API 源码。
它不会登录 IBKR、连接信号服务或修改宿主机服务。

合并安装包构建器会拒绝过期镜像输入、不匹配的 wheel、错误架构、变化的依赖源码包
以及不匹配的镜像依赖版本。每个安装包包含匹配的应用源码。wheel 和源码必须来自
同一份经过审查的文件。还应从解压后的源码运行测试，并比较重新生成的 wheel 哈希。

使用模拟数据进行真实 Docker 凭据隔离及生命周期测试，再使用最终安装包的启动器
重复隔离检查。验证压缩包校验值、源码哈希、中英文文档链接，以及私有状态未发生变化。
自动化测试不能证明盈利能力，也不能代替实际未进行过的登录测试。

## 发布经过审查的源码

客户仓库为
[quantmnq/executor-container](https://github.com/quantmnq/executor-container)。
使用本版本经过审查的 `public-repository/` 导出内容更新它，保留现有公开提交历史。
可以用 GitHub Desktop，在该公开仓库的克隆目录中复制并提交这些文件，不需要访问
VM 的秘密文件。应包含 `.github/`、`.gitignore` 等公开隐藏文件，但不能复制工作
VM 的 `.git/` 历史。代码没有假定仓库网址。

创建与 0.3.1 对应的 release/tag，上传审核过的以下文件：

- `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz`
- 对应的 `.tar.gz.sha256` 校验文件
- `follow-executor-0.3.1-source.tar.gz`（安装包内部也包含）
- `follow-executor-0.3.1-dependencies.tar.gz`
- 覆盖这些发布文件的 `SHA256SUMS`

在二进制下载旁边免费提供对应源码下载。不能要求已经收到软件的用户续订信号服务，
才允许他们取得相应源码。不要增加与 GPL 冲突的软件保密、禁止修改或禁止转售条款。
信号服务访问仍然另行授权；公开源码不会提供订阅令牌或服务商策略。

保留每个发布版的二进制、准确对应的应用/依赖源码包、许可声明和哈希值。更换下载平台
时也要保持源码可获取。只有来自可信渠道的校验值才能用于确认完整性。

依赖源码包比安装包大，正常安装时不必下载。将它放在 GitHub Release 附件中，不要
放入 Git 源码目录。邀请客户前检查源码链接和校验值链接。私下交付每个客户的订阅令牌，
并确认服务商公钥指纹。

## 客户下载与 Discord

将源码发布到公开 GitHub 仓库，将上述五个附件放在 **v0.3.1 Release**。
在 GitHub 打开 **Releases → Draft a new release**，选择匹配的源码提交／标签，
上传附件并填写版本说明。首次模拟账户接入可标记为 pre-release（预发布）。
发布后先核实实际下载文件，再向客户发送链接。

在 Discord 置顶发布页面链接，以及同一标签下的英文 `docs/SETUP.md` 和
简体中文 `docs/SETUP.zh-CN.md`；已有客户另附 `docs/UPGRADE.md` 和 `docs/UPGRADE.zh-CN.md`。一般客户只需下载 `follow-stack` 压缩包及对应
`.sha256`，再按自己的语言阅读 SETUP 指南。GitHub 自动生成的 “Source code”
下载不是安装包。全部指南和截图也已包含在安装包中。

如果直接在 Discord 附加安装包，务必同时提供匹配校验文件，并在同一帖子中链接
对应的应用源码和依赖源码。先检查频道附件大小限制；依赖源码包远大于安装包。
优先提供一个 GitHub Release 链接，避免同一版本的文件散落在多条消息中。

`START_HERE` 和 `AGENT_SETUP` 用于主要的 Codex／Claude Code 安装流程；`CONTAINER_SETUP` 用于维护
与恢复；`EXECUTOR` 解释交易及安全行为；均有中文版本。`DISCORD` 是个人交易通知
设置文档，不是安装指南。此组合容器包的客户无需从 `SETUP_NATIVE` 或 `RELEASING` 开始。

## 推广与维护

使用中英文零基础安装指南。先让两到三位模拟账户客户尝试，包括从未使用终端的人。
每位客户都需要通过自己的就绪检查；安装不会自动开始交易。客户明确启动前，确认
模式、品种和数量。客户从 Codex 或 Claude Code 的 START_HERE 提示开始。已有安装需要在停止执行器且账户空仓时迁移，
保留交易日志，并重新生成服务以获得凭据隔离挂载。只加载新镜像还不够。

发布源码不会部署到正在运行的试点，也不会授权实盘交易。原生 Gateway 路径保留给
已有安装；AMD64 不是支持的客户平台。修改上游 Gateway 摘要需要单独进行登录/恢复
验收，与源码发布打包检查分开。

0.3.1 的依赖固定版本与 0.1.12 相同，上述命令按可信 SHA-256 复用该版准确的依赖源码。
收集器验证压缩包及文件哈希，组合包构建器继续核对镜像完整依赖清单。依赖变更时，不带
`--reuse-archive` 重新收集并核对来源；不得用较新源码替代实际安装的依赖版本。
