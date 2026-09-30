# 排查说明

## SSH 无法连接或返回 255

先在 Windows 验证独立 SSH，排除界面和工具服务器：

```powershell
ssh -vv -o BatchMode=yes -o ConnectTimeout=10 dev@vps.example.com "printf 'SSH_OK\n'"
```

- `Permission denied`：检查用户名、密钥、`authorized_keys` 和加密密钥是否加入 `ssh-agent`。
- `Host key verification failed`：核对 VPS 指纹与 `known_hosts`，不要直接关闭主机密钥校验。
- 超时：检查本机网络出口、VPS 防火墙、云安全组及 SSH 端口。
- `remote port forwarding failed`：检查 SSH 服务端是否允许远端转发、绑定回环地址，或端口是否被占用。

如果 VPS 安装了 fail2ban，可由管理员检查 `fail2ban-client status sshd` 及认证日志。多次失败的密码登录可能导致来源地址被封；本机如果走代理或多出口，VPS 看到的来源地址可能不同。只对确认属于自己且误封的地址解封，不需要关闭整个防护。

正常 VS Code 会话为每条连接随机选择 49152–65151 范围内的远端端口；偶发碰撞在尚未收到会话数据时可重试。`windows/start-tunnel.ps1`、`vps/mcp.json.example` 和 `vps/check-bridge.sh` 是手动诊断用的固定端口流程，默认 18765；不是正常会话的必需步骤。

## 找不到 Claude 或本地工具服务器

在本机重新执行 `windows/install.ps1`；确认 Claude Code 扩展安装完整。工具服务器可以手动运行查看错误：

```powershell
.\windows\start-tool-server.ps1
```

该命令会持续占用终端。若服务器已自动启动，请先查看 `.state` 下的日志，避免重复占用 8765。需要指定 Claude 可执行文件时使用 `-ClaudeCommand`。

VPS 上 `claude` 不在非交互环境的 PATH 中时，重新配置 `-RemoteClaude` 为绝对路径。模型认证错误则在 VPS 独立运行 `claude` 或 `claude --settings /path/to/settings.json` 验证。

## 看不到会话历史或不能续聊

确认本机打开的是原 Windows 工程，VPS 记录尚在，且两端 Claude Code 的版本支持当前镜像协议。VPS stdout 中的 `transcript_mirror` 帧不会直接展示在界面中，包装器将其保存到本机工程历史目录。

修改 VPS 的 `RemoteWorkdir` 后，原会话可能位于旧的远端工程记录目录；恢复原工作目录后再尝试续聊。旧版桥接没有镜像的记录可使用 `windows/recover-history.py` 补回，参数说明见 `--help`。

## 恢复普通本地 Claude Code

在 VS Code 用户设置中删除 `claudeCode.claudeProcessWrapper` 和 `claudeCode.disableLoginPrompt`，然后执行 **Developer: Reload Window**。本地 Claude Code 将重新使用本机登录与模型配置。

不要在任务仍在执行时更换包装器或关闭隧道。公开日志前请清理凭据、路径、来源地址和会话内容。
