# MCGS Full-Chain Studio

[![CI](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/codeql.yml/badge.svg)](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

面向 MCGS 工程交付的本地优先辅助平台：把项目参数、插接箱拓扑、机柜映射、动环协议与模板改造指导收敛到同一个受控工作流中。

> **非官方项目。** 本仓库与 MCGS 软件的开发商、商标权利人没有隶属、授权或背书关系。仓库不包含 MCGS 软件、许可证、帮助文档、`.MCP` 工程、模板二进制、客户图纸、真实点表、账号数据库或历史生成结果。

> **版本与部署警告。** 本文中的构建和部署合同面向 `v0.1.2`。公开的 `v0.1.0` 已标记为 prerelease，其部署脚本存在已知的生产安全缺陷；`v0.1.1` 的显式事务补偿路径会产生互相矛盾的最终安全结论，仅保留用于审计。**不得使用 `v0.1.0` 或 `v0.1.1` 执行部署、回滚或恢复。**仓库测试、静态合同检查或本文档本身都不表示 `v0.1.2` 已经在任何生产主机完成切换、回滚或恢复验收。

## 能做什么

- 用结构化参数描述项目拓扑、插接箱类型、回路与机柜映射；
- 生成动环协议、设备导入表和报警状态字脚本；
- 基于公开规则给出 MCGS 模板中确实需要人工修改的策略、变量和窗口指导；
- 使用统一的登录、会话、CSRF 和失败锁定边界保护网页与生成接口；
- 保留可下载产物与校验清单，便于复核和交接。

## 不能替代什么

本项目输出是工程辅助材料，不等于以下结论：

- 已写入真实 `.MCP` 工程；
- 已通过 MCGS Pro 编译或仿真；
- 已通过设备联调、现场测试或正式验收；
- 已证明协议与项目图纸、上位机点表完全一致。

正式交付仍须由具备权限的工程师在合法安装的 MCGS 环境中完成 GUI 回读、编译、仿真、设备联调和现场验收。

## 架构

```text
浏览器
  ├─ /              全链条项目装配台
  ├─ /protocol/     动环协议高级制表台
  └─ /login         共用账号入口
          │
          ▼
protocol_studio     FastAPI、认证、生成 API、下载
  ├─ mvp_generator  协议模型与 Excel/CSV 渲染
  ├─ assembly_studio
  │                 MCGS 改造指导前端
  └─ resources      公开 schema、seed 与合成示例
```

生产中的运行结果与账号数据库应放在发布目录之外：

```text
/srv/apps/protocol-studio/
  ├─ releases/<release-id>/   每个版本独立源码与 .venv
  ├─ current -> releases/...  原子切换
  ├─ .deploy-state/           root-only 锁、备份、日志与已归档事务证据
  ├─ .deploy-transaction.json schema 3 未完成事务标记（仅事务期间存在）
  └─ shared/
      ├─ runs/                历史生成结果
      └─ security.sqlite3     账号与会话数据
```

## 本地启动

要求 Python 3.11+。Node.js 20+ 仅用于 JavaScript 测试。

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.production.txt
python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port 8123
```

打开 `http://127.0.0.1:8123/`。本地开发默认不启用账号系统；不要把未启用认证的实例暴露到公网。

`v0.1.2` 的直接生产依赖固定为 FastAPI `0.140.7`、Starlette `1.3.1`、Uvicorn `0.38.0`、Pydantic `2.12.5`、Jinja2 `3.1.6` 和 openpyxl `3.1.2`。生产部署不使用上述本地开发安装命令，而是按全哈希的 17 包传递锁从受信离线 Wheelhouse 安装。该 17-wheel 输入已在目标 Linux 主机完成摘要回读、无索引离线安装、`pip check` 和依赖导入 smoke；最终冻结源码归档的完整 Linux runner、staging 与生产验收仍是独立门禁。Wheelhouse 是受控部署输入，不包含在公开源码发布资产中。

应用从 `pyproject.toml` 读取项目版本，FastAPI 应用元数据因此与 `0.1.2` 保持一致；`Dockerfile` 也会把 `pyproject.toml` 与生产锁一同复制进镜像，并把官方 `python:3.11.6-slim-bookworm` 基础镜像固定到 manifest-list digest `sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b`。这里描述的是代码合同；本地发布工作站没有 Docker CLI，而且当前 Docker 构建上下文不会复制打包时生成的 `release-manifest.json`，所以容器没有 Release identity。正式容器发布与生产使用保持阻断，直到补齐 Manifest 身份、真实 build/run、基础镜像与 OS 漏洞扫描及运行验收。

## 启用账号系统

复制 `.env.example` 到不会提交的本地环境文件，生成初始密码哈希：

```bash
python scripts/generate_password_hash.py
```

将输出写入 `PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH`，再设置：

```dotenv
PROTOCOL_STUDIO_AUTH_ENABLED=true
PROTOCOL_STUDIO_COOKIE_SECURE=true
PROTOCOL_STUDIO_EXTERNAL_ORIGIN=https://your.example.com
PROTOCOL_STUDIO_ALLOWED_HOSTS=your.example.com,127.0.0.1
```

不要提交环境文件、密码、哈希、Cookie、SQLite 数据库或生成目录。首次密码变更后，数据库中的当前凭据是唯一真值；部署不得重建或覆盖该数据库。

## 测试

```bash
python -m pip install -r requirements.dev.txt
python scripts/validate_repository.py
python scripts/check_public_tree.py --root .
python scripts/run_tests.py
python packaging/build_release.py --version 0.1.2 --check-only
```

上述检查覆盖 Python 编译、JavaScript 语法与测试、协议回归、认证回归、JSON/YAML/TOML 基础校验和公开目录隐私扫描。部署合同测试只检查脚本文本约束与 Shell/Python 静态边界；它不会执行真实的 systemd 切换、故障补偿或断电恢复。测试通过既不代表生产部署通过，也不代表 MCGS 运行验收通过。

## 构建公开发布包

打包器只读取 [`packaging/release-allowlist.json`](packaging/release-allowlist.json) 中的白名单；拒绝符号链接、客户常见文件格式、运行缓存和绝对路径条目。验证器还要求策略与 Manifest 精确覆盖九棵非空发布树，并在每棵树中找到稳定入口 sentinel；树中的其他可选文件不会因为一次构建中存在就被误设为全部必需。

```bash
python packaging/build_release.py --version 0.1.2
python packaging/verify_release.py dist/mcgs-full-chain-studio-0.1.2.tar.gz
```

发布包内的 `release-manifest.json` 只记录 POSIX 相对路径、字节数与 SHA-256，不记录构建机器路径。构建器同时生成 `.tar.gz.sha256`；生产命令必须显式传入经过可信渠道核验的 `--archive-sha256`，不能只依赖部署主机重新计算的摘要。

正式 release 树启动时会计算 `release-manifest.json` 的 SHA-256；`/api/health` 同时在 JSON 字段 `release_manifest_sha256` 和唯一响应头 `X-MCGS-Release-Manifest-SHA256` 返回该小写摘要。没有 Manifest 的源码/开发树会返回 JSON `null` 并省略该响应头，因此普通 HTTP 可用性不能冒充 release identity。

仓库中的 [`packaging/generate_sbom.py`](packaging/generate_sbom.py) 已在代码与合成合同测试中实现以下 v0.1.2 门禁：校验 `pyproject.toml` 的项目名、版本和六个 exact direct pins，要求非空全哈希生产锁与精确匹配的纯 `.whl` Wheelhouse，并按 OpenCloudOS/Linux x86_64、CPython 3.11.6 评估适用的 `Requires-Dist` markers 和传递依赖闭包，再生成 CycloneDX 1.5 JSON 与 SHA-256 sidecar。本地独立回读已确认 17 个锁定应用依赖组件和 18 条依赖记录；这不自动包含 `venv`/`ensurepip` 带入的 pip、setuptools 等部署工具。官方 CycloneDX Schema 验证、同一冻结提交上的正式生成、GitHub provenance 和目标运行验收仍是独立门禁：

```bash
RELEASE_COMMIT='replace-with-reviewed-release-commit'
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct "$RELEASE_COMMIT")"
python packaging/generate_sbom.py \
  --lock requirements.production.lock.txt \
  --wheelhouse dist/wheelhouse-v0.1.2 \
  --output dist/mcgs-full-chain-studio-0.1.2.cdx.json \
  --application-name mcgs-full-chain-studio \
  --application-version 0.1.2
```

`v0.1.2` 正式 Release 的**资产计划**是同时发布 `.tar.gz`、`.tar.gz.sha256`、`.cdx.json` 和 `.cdx.json.sha256`。这是发布门禁计划，不表示正式 SBOM、这些资产、GitHub Release 或目标 Linux 验证已经完成；正式资产必须在同一冻结提交上重新生成并逐项回读。离线 Wheelhouse 仍是单独的受信部署输入，不因存在 SBOM 而自动获得真实性。

## v0.1.2 部署合同摘要

- `--archive-sha256` 与 `PROTOCOL_STUDIO_WHEELHOUSE` 都是必填项；生产依赖只从 root-owned 离线 Wheelhouse 按 `requirements.production.lock.txt` 和哈希安装。
- 生产 EnvironmentFile 禁止出现 `PROTOCOL_STUDIO_RESOURCES_ROOT`（空值也拒绝），强制协议库、地址与导出模板来自已纳入 Manifest 的 Release 内置 `resources/protocol`；该 override 只保留给非生产开发场景。
- 部署、回滚、恢复脚本及其 Python/打包 helper 必须作为同一 `v0.1.2` 控制包，从 root-owned、父目录链不可被 group/other 写入的位置执行，不能混用版本或直接从普通用户可写的 checkout 执行。
- `run_with_env.py` 在 POSIX `exec` 前关闭全部继承的 `fd > 2`；回滚与恢复 Shell 在长期 canary 启动前还会显式关闭 `fd 8/9`。这属于分层隔离合同，Windows 静态/单测结果不能替代 Linux `/proc/self/fd` 运行验证。
- 部署、回滚、恢复三类事务中，modern release-local 运行时的每个 local/public 健康门禁都必须取得唯一、格式正确且与记录值精确相同的 Manifest 摘要；只有已注册、早于该响应头的 legacy baseline 使用 availability-only 检查，不能据此声明 release identity 或完整 provenance 通过。
- `deploy/check-production.sh` 默认要求 `PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256`，并对所选部署根内的外置 runtime baseline、immutable guard、完整 fingerprint、两条有序 `ExecStartPre` 以及 local/public Manifest 身份做组合校验。modern release 只有在 `installed_runtime_identity=passed` 且 local/public 两端精确匹配时才输出 `release_identity=passed`；任一输入缺失或漂移都会 fail closed。只有显式设置 `PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY=true` 才执行兼容性 availability-only 检查并输出 `installed_runtime_identity=not_requested` 与 `release_identity=not_requested`，且该开关不得与摘要同时设置、不得用于 modern release 的正式验收。
- 四份部署 Shell 的每次 `curl` 都以 `--disable` 禁用 `.curlrc`，显式绕过代理，并在入口清除常见代理与 `CURL_HOME` 环境变量；这是防环境注入合同，不替代 TLS、Host、Manifest 摘要和真实 ingress 验证。
- `--prepare-only` 是 **ephemeral dry-run**：它验证后会删除 `.incoming-*` 候选，不保留 release，也不修改 `current`、systemd、生产服务或 `shared/` 业务数据；root-only `.deploy-state` 中的锁和验证日志/证据会保留。因此正式切换可以复用同一个 release ID，但会从同一归档、摘要和 Wheelhouse 重新构建并重新验证。
- 正式事务使用严格 schema 3 active marker：部署从 `switching`、回滚从 `rolling_back` 开始。deploy/rollback 的普通阶段切换只改 `status`，不增删顶层字段；precommit recovery 进入 `recovery_committed_pending_activation` 时，还会原子绑定 `recovery_activation_release_id` 与 `recovery_activation_runtime_mode`，随后这些字段保持不变。外置 runtime baseline 保持 schema 1，但强制包含 64 位小写 SHA-256 字段 `runtime_guard_helper_sha256`；实际执行的 helper 会被重新哈希并与该字段精确比对，缺字段的旧 schema 1 baseline 不能批准 modern restart。新发布的 deploy/rollback/recovery passed evidence 使用 schema 5，并绑定 public origin/host、EnvironmentFile、base unit、managed drop-in、两条有序 `exec_start_pre_argvs`、外置 runtime baseline/guard/fingerprint、ordinary-restart integrity gate 和最终 publication configuration gate。schema 2–4 passed record 只保留为离线审计证据：v0.1.2 仅识别并在任何 systemd 或事务状态变更前拒绝激活，不会为它们隐式生成 baseline、改写 provenance，也不能把它们作为 deploy 当前版本、显式 rollback 目标或 recovery 激活目标。独立注册的 legacy shared-runtime baseline 是另一套兼容合同，仍支持首次升级、precommit 恢复和显式 legacy 回滚。服务先持久 disable，再安装 `/run` 下 `Restart=no`、`RuntimeMaxSec=300s` 的临时 guard，stop、切换并在 disabled 状态下启动验证。`/run` guard 重启后不会保留，但 service 的 persistent-disabled 状态会保留；active marker 未处理完前仍不应重启主机。
- 目标通过有 guard 的健康/来源检查并写好 pending record 后，marker 才进入 `deploy_committed_pending_activation` 或 `rollback_committed_pending_activation`。之后该目标已经逻辑承诺：脚本移除 guard、用正常重启策略重新启动，扫描全部 systemd `.wants`/`.requires` 符号链接并按 canonical target 核对，只接受唯一标准 `multi-user.target.wants` 链接；不同文件名但指向同一 unit 的 alias 也会拒绝。
- Enablement 和最终 provenance/health 复核通过后，脚本先协调或发布 passed record，确认 final/pending 同 inode 合同、目录持久化、pending unlink 及再次持久化成功，才归档 active marker。发布中断或失败时 marker 保留；`recover-transaction.sh` 可对 pending-only、pending+final 或 final-only 状态幂等重入，不允许人工把未完成证据改写成 PASS。
- 任一 active marker 都不能人工删除。`switching`/`rolling_back` 这类 precommit recovery 恢复 marker 中的 previous；committed recovery 只能完成已承诺 target，必要时使用 `recovery_committed_pending_activation`。失败处理必须真实回读 persistent-disabled、inactive/dead、`MainPID=0`、原进程消失和 marker 保留；未确认 fail-closed 时必须 **DO NOT REBOOT** 并转人工 systemd 恢复。
- 受管 drop-in 保持 `UMask=0077`，先用空的 `ReadWritePaths=` 与 `Environment=` 清除累加值，再只开放 `/srv/apps/protocol-studio/shared` 并固定设置 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONUNBUFFERED=1`；同时以精确 `UnsetEnvironment` 清除 glibc/OpenSSL/Python/Bash/Uvicorn 启动注入变量。普通启动严格先由系统 Python 执行外置 runtime guard，再由 Release 内 `.venv` 执行环境 validator；validator 与 Uvicorn 都使用 `python -I -B -u`。`StartLimitIntervalSec=60s`、`StartLimitBurst=3` 用于约束完整性失败后的重复全树哈希。脚本不会覆盖管理员维护的 base unit，只管理 `90-release-runtime.conf`；这些 systemd 与 `/proc` 合同仍须 Linux staging 实测。
- transient systemd canary 使用同一候选源码和 `.venv`、私有数据库与私有运行目录检查受限 systemd 启动、健康接口和登录重定向。Windows 合同已覆盖危险环境与 Uvicorn app-dir 劫持，但 rollback/recovery canary 的实际 `/proc/<pid>/environ` 仍必须在 Linux staging 单独回读；它不证明生产共享状态、`current`/drop-in 正式切换、公网完整业务流程、回滚或中断恢复已经通过。
- runtime 配置切换和证据提交不等于共享业务状态事务：SQLite 备份是受保护证据与人工恢复输入，脚本不会自动恢复 live 数据库，代码回滚也不会撤销切换窗口内产生的账号、会话或 runs 写入。生产必须先确认数据 schema 向后兼容、演练备份恢复，并在外部流量隔离或明确维护窗内切换；恢复并完成公网验收后才能重新放流。
- 生产前还必须只读确认 EnvironmentFile 中的管理员用户名已经存在于共享账号库，bootstrap scrypt hash 可用且不会新增意外管理员，并以真实账号验证登录、旧会话/权限复用和三类生成下载。静态 validator 的前缀检查、health 与 `/login` 重定向不能代替这些认证验收。

以上为实现和合同测试边界；本次同步没有执行 Docker build、staging 或 production 部署验收，任何容器发布以及未隔离外部流量、未验证账号与数据恢复的生产切换都保持阻断。

完整的控制包、准备、切换、恢复和回滚步骤见 [`deploy/README.md`](deploy/README.md)。

## 数据与隐私规则

允许提交：

- 人工合成且不对应任何客户的示例；
- 通用 schema、类型规则和最小公开 seed；
- 不含专有资料的测试夹具。

禁止提交：

- `.MCP`、工程备份、客户 Excel/XML/CSV、图纸和截图；
- 真实项目名称、机房编号、设备清单、IP/端口、地址映射；
- `runs/`、`protocol_runs/`、SQLite 数据库、日志和缓存；
- 密码、密码哈希、Token、Cookie、私钥和生产 `.env`；
- 未取得再分发权的 MCGS 帮助文档、软件文件或模板资源。

详见 [CONTRIBUTING.md](CONTRIBUTING.md)、[SECURITY.md](SECURITY.md)、[SUPPORT.md](SUPPORT.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可证与权属放行

代码拟按 [Apache License 2.0](LICENSE) 发布。**公开发布前，发布者必须确认自己有权许可仓库中的每一份源码、数据、图像和第三方资产。** Apache-2.0 不会替代第三方许可，也不会授予任何 MCGS 商标或软件权利。

Copyright statements in a release must reflect verified ownership; see [NOTICE](NOTICE) and [TRADEMARKS.md](TRADEMARKS.md).
