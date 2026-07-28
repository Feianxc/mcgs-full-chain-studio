# MCGS Full-Chain Studio

[![CI](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/codeql.yml/badge.svg)](https://github.com/Feianxc/mcgs-full-chain-studio/actions/workflows/codeql.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

面向 MCGS 工程交付的本地优先辅助平台：把项目参数、插接箱拓扑、机柜映射、动环协议与模板改造指导收敛到同一个受控工作流中。

> **非官方项目。** 本仓库与 MCGS 软件的开发商、商标权利人没有隶属、授权或背书关系。仓库不包含 MCGS 软件、许可证、帮助文档、`.MCP` 工程、模板二进制、客户图纸、真实点表、账号数据库或历史生成结果。

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
python packaging/build_release.py --version 0.1.0 --check-only
```

上述检查覆盖 Python 编译、JavaScript 语法与测试、协议回归、认证回归、JSON/YAML/TOML 基础校验和公开目录隐私扫描。测试通过仍不代表 MCGS 运行验收通过。

## 构建公开发布包

打包器只读取 [`packaging/release-allowlist.json`](packaging/release-allowlist.json) 中的白名单；拒绝符号链接、客户常见文件格式、运行缓存和绝对路径条目。

```bash
python packaging/build_release.py --version 0.1.0
python packaging/verify_release.py dist/mcgs-full-chain-studio-0.1.0.tar.gz
```

发布包内的 `release-manifest.json` 只记录 POSIX 相对路径、字节数与 SHA-256，不记录构建机器路径。生产发布与回滚见 [`deploy/README.md`](deploy/README.md)。

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
