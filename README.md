# claude-local-bridge

在 Windows 的 VS Code Claude Code 面板里工作，让 VPS 上的 Claude Code 负责推理和 Agent 调度，通过 SSH + MCP 操作本地工程和开发环境。

这是一个实验性桥接项目，已验证真实模型回复、本地文件读取、同时打开两个会话、恢复会话及历史镜像。它复用 Claude Code 的界面和工具实现，不重新实现 Agent，也不分发 Claude Code 本体。

## 架构

```text
Windows                                      VPS
VS Code Claude Code 面板
        │
claudeProcessWrapper
        │
自建进程包装器 ─── SSH stdin/stdout ─────────► Claude Code
        │                                        │
        │                                  Anthropic / 兼容服务
        │                                        │
        │          同一条 SSH 的反向隧道           │ MCP 工具调用
        ◄────────────────────────────────────────┘
127.0.0.1:8765/mcp
        │
mcp-proxy → 本地 claude.exe mcp serve
        │
Read / Edit / Write / Bash / Git / 编译 / 测试
        │
Windows 工程与开发环境
```

本地 Claude Code 以 MCP 工具服务器模式运行，不承担模型推理。VPS 上禁用内置工具，并注入 `windows-local-claude` MCP 配置。每个对话随机选择一个远端回环端口，SSH 同时承载界面协议流和工具隧道，MCP 无需开放公网端口。

复用的能力：

- [Claude Code](https://code.claude.com/docs/en/overview)：VS Code 扩展、`claude mcp serve`、进程包装器入口。
- [Model Context Protocol](https://modelcontextprotocol.io/)：工具发现、调用和结果回传。
- [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy)：stdio MCP 转 Streamable HTTP。
- [OpenSSH](https://www.openssh.com/)：加密传输、密钥认证和反向端口转发。

## 准备条件

- Windows、VS Code 正式版，以及 Anthropic 的 Claude Code 扩展。
- Python 3.10+，推荐 3.11；`python` 可在 PowerShell 中运行。
- Windows OpenSSH 客户端，`ssh` 和 `ssh-keygen` 可用。
- 可通过 SSH 登录的 Linux VPS，具有 Bash 和已安装的 Claude Code。
- VPS 上可用的 Claude Code 订阅或 API 凭据；本项目不提供账号、免费额度或模型服务。

目前实测组合：Windows Claude Code 2.1.284、VPS Claude Code 2.1.285。更新版本前请确认扩展的 `claudeCode.claudeProcessWrapper` 设置及 CLI 的 `--session-mirror` 仍可用。

## 安装

### 1. 在 VPS 准备 Claude Code

按 [Claude Code 官方安装说明](https://code.claude.com/docs/en/setup)安装。在 VPS 上运行 `claude`，完成登录并确认能够回复。

也可以在 **VPS** 保存 API 配置，例如 `/home/dev/.config/claude-local-bridge/settings.json`，参考 [vps/settings.example.json](vps/settings.example.json)。将示例占位符替换为自己的凭据，并限制文件权限：

```bash
chmod 600 /home/dev/.config/claude-local-bridge/settings.json
claude --settings /home/dev/.config/claude-local-bridge/settings.json
```

第三方服务需要兼容 Claude Code 使用的 Anthropic API；按服务商说明在 VPS 配置 `ANTHROPIC_BASE_URL`、认证字段和模型。兼容性与费用由服务商决定。无需把 API 密钥复制到 Windows。

SSH 服务端必须允许远端端口转发，并允许绑定回环地址。默认 OpenSSH 配置通常支持；受限账号需要管理员配置相应权限。

### 2. 在 Windows 下载、安装和构建

在 PowerShell 中执行：

```powershell
git clone https://github.com/cheguevara-great-man/claude-local-bridge.git
cd claude-local-bridge
Set-ExecutionPolicy -Scope Process Bypass
.\windows\install.ps1
.\windows\build-wrapper.ps1
```

包装器会生成在 `bin\claude-vps-wrapper-history.exe`。仓库只发布源码，首次使用需要本地构建。

### 3. 配置免密 SSH

以下 `dev@vps.example.com` 都是示例，请替换为自己的 VPS 用户和地址；PowerShell 中 `@` 前不需要反斜杠。

先正常登录一次，核对服务器主机密钥指纹并建立 `known_hosts`：

```powershell
ssh dev@vps.example.com
# 登录成功后，在 VPS shell 中执行 exit 返回本机
```

若已能免密连接，可跳过引导脚本。否则执行：

```powershell
.\windows\bootstrap-ssh-key.ps1 -Vps dev@vps.example.com
ssh -o BatchMode=yes dev@vps.example.com "printf 'SSH_KEY_OK\n'"
```

引导脚本使用 SFTP 添加本机公钥，终端输入的是 **VPS 的 SSH 登录密码**，脚本不保存密码。若没有默认 Ed25519 密钥，会创建一个无口令密钥；已有加密密钥请先加入 `ssh-agent`。引导脚本要求 `user@host`，使用默认 `~/.ssh/id_ed25519`；包装器本身也可使用 OpenSSH 的 Host 别名和配置。

自定义 SSH 端口时，上面的 `ssh` 加 `-p 2222`，引导脚本加 `-VpsSshPort 2222`。

### 4. 连接 VS Code

使用 VPS 原有登录与配置：

```powershell
.\windows\configure-vscode.ps1 -Vps dev@vps.example.com
```

使用指定的 VPS API 配置文件：

```powershell
.\windows\configure-vscode.ps1 `
  -Vps dev@vps.example.com `
  -RemoteClaude /home/dev/.local/bin/claude `
  -RemoteSettings /home/dev/.config/claude-local-bridge/settings.json
```

`-RemoteClaude` 是 VPS 的可执行文件路径；若 `claude` 在非交互 SSH 环境的 PATH 中可用，可省略。`-RemoteSettings` 是 **VPS 文件路径**，默认留空。非默认 SSH 端口加 `-VpsSshPort 2222`。

脚本写入本机 `bin\bridge.conf`，并修改 VS Code 用户设置：

```json
{
  "claudeCode.claudeProcessWrapper": "C:\\work\\claude-local-bridge\\bin\\claude-vps-wrapper-history.exe",
  "claudeCode.disableLoginPrompt": true
}
```

脚本自动填写实际路径。执行 VS Code 的 **Developer: Reload Window**，打开本地工程，再打开 Claude Code 面板。可以发送：

> 请用 windows-local-claude 的工具读取当前 Windows 工程的 README，并报告文件路径和前五行。

确认读取的是本机工程，再尝试 Git、构建或测试。包装器自动启动本地工具服务器，无需另外运行隧道脚本。

## 历史记录如何工作

Claude 的原始会话保存在 VPS。`--session-mirror` 让远端进程在协议流中发出 `transcript_mirror` 消息，包装器消费这些消息，将记录写入 Windows 的 `~/.claude/projects/<工程目录编码>/`。它适配工作目录和界面入口元数据，保留会话 ID、消息及工具结果，其余界面协议继续转发给 VS Code。

因此本机能列出历史；重新打开时，使用同一个 `--resume` ID 恢复 VPS 的原始会话。这是 **VPS → Windows 的持续单向镜像**，不是完整的双向同步：本机重命名或删除记录不会自动修改远端，断线期间不会持续同步。

恢复镜像功能启用前的旧记录，可在目标 Windows 工程目录运行：

```powershell
C:\work\claude-local-bridge\.venv\Scripts\python.exe `
  C:\work\claude-local-bridge\windows\recover-history.py `
  --host vps.example.com --user dev `
  --remote-project /home/dev/.claude/projects/-home-dev
```

`--remote-project` 必须对应实际的 VPS Claude 工程记录目录；恢复脚本的默认值适用于 root 用户的 `/root` 工作目录。

## 边界与限制

- 本项目是实验性集成。`--session-mirror` 属于面向 SDK 的功能，Claude Code 升级可能改变协议。
- 本地工具服务器将模型地址设为不可用的回环端点，并关闭相关遥测和自动更新；这属于进程配置，**不是操作系统防火墙隔离**。本地 Bash 和其他工具仍具有电脑原有的网络与文件权限。
- 不应将 MCP 端口暴露到公网。VPS 会话可通过隧道调用本机工具，请仅连接可信 VPS；当前不提供文件目录沙箱或独立工具权限策略。
- 对本地 Agent、WebSearch 等工具的禁用约束目前来自系统提示，未实现 MCP 工具过滤，不能作为强制隔离保证。
- Git、编译和调试通过本地命令执行。VS Code 的原生差异展示、断点控制、IDE 集成、Skills 和额外 MCP 配置尚未完整适配；不能保证与原生本地 Claude Code 的所有功能一致。
- 本地模型配置不转发到 VPS；本地传入的 `--settings` 与 MCP 配置由桥接替换。需要的 API 设置应放在 VPS。
- 当前默认将各 Windows 工程的远端会话放在同一个 VPS 工作目录（`~`）。本机历史按 Windows 工程分开，但远端尚无自动工程目录映射。
- 本机历史使用默认 `~/.claude` 目录；自定义 `CLAUDE_CONFIG_DIR` 尚未适配。配置脚本面向 VS Code 正式版的用户设置目录。
- SSH 在尚未收到远端协议数据时最多尝试四次连接；已开始的会话不会自动重放，避免重复执行工具。断线后可从历史恢复。

## 排查与开发

参见 [排查说明](docs/troubleshooting.md)。常用文件：

| 文件 | 用途 |
| --- | --- |
| `wrapper/main.py` | VS Code 进程包装器、SSH 启动、每会话隧道 |
| `wrapper/history.py` | 历史镜像、路径校验、续聊去重 |
| `windows/configure-vscode.ps1` | 生成本机连接配置，设置 VS Code |
| `windows/start-tool-server.ps1` | 本地 Claude 工具服务器和 MCP HTTP 代理 |
| `windows/bootstrap-ssh-key.py` | 通过 SFTP 安装公钥 |
| `bin/bridge.conf.example` | 连接配置示例，无凭据 |
| `vps/settings.example.json` | VPS API 配置模板 |

运行测试和 PowerShell 语法检查：

```powershell
python -m unittest discover -s tests -v
foreach ($file in Get-ChildItem windows/*.ps1) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count) { throw "$($file.Name): $($errors.Message -join '; ')" }
}
```

测试覆盖协议转发、结果返回前写入历史、续聊去重、远端路径校验、独立 MCP 端口和默认 VPS 配置行为；真实模型与工具调用需自行端到端验证。

[ci/github-actions.tests.yml](ci/github-actions.tests.yml) 提供 Windows GitHub Actions 测试模板。发布所用凭据没有 `workflow` 权限，所以模板尚未启用；具备相应权限时，将其复制到 `.github/workflows/tests.yml` 并提交即可自动运行。

提交问题时请删除 API 密钥、SSH 凭据、私有 IP 和聊天内容。`.gitignore` 排除了运行目录、聊天记录、真实配置和构建产物。

## 许可证

桥接源码使用 [MIT License](LICENSE)。Claude Code 是 Anthropic 的产品，不属于本项目的开源范围；相关依赖遵循各自的许可证和使用条款。
