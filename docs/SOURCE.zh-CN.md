# 源代码、许可与重新构建

[English](SOURCE.md) | 简体中文

Follow Executor 的原创应用代码、安装/构建工具及原创文档采用
GPL-3.0-or-later（GPL 第 3 版或任何后续版本）。请阅读 [LICENSE](../LICENSE)、
[NOTICE](../NOTICE) 和[第三方声明](../THIRD_PARTY_NOTICES.md)。你可以按许可条件
查看、修改和重新分发软件。软件不提供担保。

## 普通用户不需要编译

继续使用安装包和[零基础安装指南](SETUP.zh-CN.md)即可。Docker 镜像是为了安装方便。
获取源代码不以维持信号订阅为条件。信号服务另行授权；软件许可不会提供订阅令牌、
服务商策略、签名私钥或客户凭据。

匹配的应用源码压缩包位于安装包的 `sources/` 目录。文件名和 SHA-256 记录在
`RELEASE.json`，安装包的 `SHA256SUMS` 也会校验它。源码包包含应用、向导、启动器、
Dockerfile、构建脚本、依赖版本和校验值、测试、文档及许可声明。
`SOURCE.json` 记录每个源码文件的哈希值。不包含 Git 历史或本机配置。

对于容器安装包，还可以从**下载安装包的同一个发布页面**下载
`follow-executor-0.3.1-dependencies.tar.gz`。其 SHA-256 位于 `RELEASE.json`
的 `third_party_source` 字段。这个单独的下载供查看和重新构建使用，正常安装不需要。
它包含完全相同且未经修改的官方 IBKR API 压缩包、Python 依赖源码包、CPython 源码，
以及镜像对应的 Debian 软件包源码、补丁和声明。重新分发容器发布版时，请一并保留并
提供这个源码包；我们并不是只提供一个上游链接来履行源码交付要求。

## 从源码构建客户发布版

使用 Ubuntu 24.04 ARM64、CPython 3.12 和 Docker。在独立的开发目录中操作，
不要覆盖正在运行的安装目录。构建和离线测试不需要 IBKR 登录或订阅令牌。
不要通过对真实账户运行 setup/start 来测试构建。以下命令在解压后的应用源码目录中
执行，该目录根部有 `pyproject.toml`。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
./scripts/install-ibapi.sh
.venv/bin/ruff check .
.venv/bin/python -m unittest discover -s tests -v
python3.12 scripts/build-bytecode.py
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
curl --fail --location --output /tmp/follow-dependencies.tar.gz https://github.com/quantmnq/executor-container/releases/download/v0.1.12/follow-executor-0.1.12-dependencies.tar.gz
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.3.1 --reuse-archive /tmp/follow-dependencies.tar.gz --reuse-sha256 c2740a33b3f91508c70116d4c0a4389b47fe2fd1748b16b5cf9f480dac0bb769
python3.12 scripts/build-container-kit.py --build dist/executor-container/BUILD.json --third-party dist/third-party/SOURCES.json
```

这些脚本需要联网，从官方地址下载固定的构建输入。构建前会校验 API ZIP 的 SHA-256，
Python 镜像依赖固定了版本和 wheel 哈希值，基础镜像固定了摘要。保留的依赖源码包
使上游下载失效后仍能取得这些源码；它并不是自动使用的离线构建缓存。

为兼容现有安装器，应用 wheel 仍采用 CPython 3.12 字节码，同时另行提供完整匹配的
源代码。wheel 声明 GPL-3.0-or-later，并附带 LICENSE/NOTICE。
`build-bytecode.py` 使用全新的隔离解释器编译，避免已导入的应用影响 wheel 字节。
要生成完全相同的 wheel，使用 `RELEASE.json` 中 `build_python_version` 记录的相同
CPython 补丁版本；这不代表整个 Docker
镜像已经实现逐字节可复现。镜像保留上游声明，并包含 `/usr/share/licenses/ibapi`
及 `/usr/share/licenses/follow-executor`。

修改后的版本也需要附带匹配源码和声明。校验值用于完整性检查，不是 DRM；可以使用
提供的构建脚本重新生成安装包。源码交付和发布步骤请参阅[发布说明](RELEASING.zh-CN.md)。

0.3.1 的依赖固定版本与 0.1.12 相同，上述命令按可信 SHA-256 复用该版准确的依赖源码。
收集器验证压缩包及文件哈希，组合包构建器继续核对镜像完整依赖清单。依赖变更时，不带
`--reuse-archive` 重新收集并核对来源；不得用较新源码替代实际安装的依赖版本。
