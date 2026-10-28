# 部署到 Ubuntu 24.04 云服务器

目标机器：Ubuntu Server 24.04 LTS 64bit / 2 核 / 4 GB 内存 / 60 GB SSD / 5 Mbps 出口。

## 1. 一键部署

在服务器上以 root（或 `sudo`）执行：

```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/kami519/PROPOSAL.git /opt/clipdock
cd /opt/clipdock
sudo bash deploy/deploy.sh
```

脚本会：

1. 安装 Python 3.12、venv、Node.js/npm、Nginx、git。
2. 创建系统用户 `clipdock`，拉取/更新代码到 `/opt/clipdock`。
3. 建立 `.venv` 并安装 `requirements.txt`。
4. 构建前端到 `frontend/dist`。
5. 首次生成 `/opt/clipdock/.env`（不会覆盖已有配置）。
6. 安装并启动 `clipdock.service`，配置 Nginx 反向代理。

重复执行脚本即可更新代码和依赖，`.env` 与 `data/` 保留。

## 2. 填写 AI 配置

```bash
sudo nano /opt/clipdock/.env
# 至少填 SUMMARY_API_KEY=
sudo systemctl restart clipdock
```

`deploy/server.env.example` 已针对 2 核 4G 调过：

| 变量 | 服务器值 | 原因 |
| --- | --- | --- |
| `SUMMARY_WORKERS` | 2 | 2 核下保留一个核给 HTTP/转写 |
| `SUMMARY_TRANSCRIBE_WORKERS` | 1 | 避免 Whisper 并行把内存打满 |
| `SUMMARY_ARTICLE_WORKERS` | 1 | 文案叠加会挤占总结并发 |
| `SUMMARY_QUEUE_MAX` | 12 | 小内存机器控制活跃任务 |
| `DOWNLOAD_WORKERS` | 1 | 5 Mbps 带宽 |
| `DOWNLOAD_CONCURRENCY` | 1 | 同一时间只下载一个视频，避免带宽争抢 |
| `MAX_FILESIZE_BYTES` | 2 GiB | 60 GB 系统盘，给临时文件和笔记留余量 |

## 3. 验证

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

重点看：

- `summaryConfigured: true`（填了 Key 后）
- `whisperAvailable: true`
- `summaryWorkers: 2`、`transcribeWorkers: 1`
- `freeBytes` 是否充足

浏览器访问 `http://124.221.244.234/`，任务中心在 `/#/tasks`。

## 4. 安全组 / 防火墙

腾讯云控制台安全组需要放行：

- `22/tcp`：SSH
- `80/tcp`：HTTP

如果之后配置 HTTPS（推荐），再放行 `443/tcp`。

服务器本身如果开了 ufw：

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
```

应用只监听 `0.0.0.0:8000`，但 Nginx 占用了 80，外部访问 8000 也建议在安全组里关闭。

## 5. Whisper 模型

第一次遇到无字幕视频时，`faster-whisper` 会从 Hugging Face 下载 `small` 模型（约 500 MB）。5 Mbps 带宽下需要几分钟。

如果服务器访问 Hugging Face 慢，可以先在本机下载后上传：

```bash
# 本机（Windows 缓存位置）
# C:\Users\<you>\.cache\huggingface\hub\models--Systran--faster-whisper-small
# 服务器目标位置
# /opt/clipdock/.cache/huggingface/hub/models--Systran--faster-whisper-small
```

前提是 `clipdock` 用户的 `HOME` 是 `/opt/clipdock`（脚本里已这样创建用户）。

也可以在 `.env` 里设置 `HF_HOME=/opt/clipdock/.cache/huggingface`。

## 6. 常用运维

```bash
systemctl status clipdock          # 服务状态
journalctl -u clipdock -f          # 实时日志
systemctl restart clipdock         # 重启
du -sh /opt/clipdock/data/cache    # 临时文件/缓存占用
cd /opt/clipdock && git log -1     # 当前版本
```

清理数据：

```bash
# 临时下载与 AI 缓存（30 天 TTL 也会自动清理）
rm -rf /opt/clipdock/data/cache/jobs/*
```

## 7. 关于 5 Mbps 带宽

应用是“服务器先下载、再转发给浏览器”，同一份文件会占用两次出口带宽：

- 下载一个 1 GB 视频，服务器先从平台拉取，用户再从服务器下载，实际接近 2 GB 流量。
- 500 GB/月 大约相当于 250 GB 左右的实际视频。
- `DOWNLOAD_CONCURRENCY=1` 能避免多个下载把 5 Mbps 占满造成互相卡顿。

如果流量是主要瓶颈，后续可以考虑“服务器下载完成后给用户一个限时直链”，或者限制可选画质。

## 8. 后续可选

- 配置域名 + HTTPS：`apt install -y certbot python3-certbot-nginx && certbot --nginx -d your.domain.com`。
- 访问保护：当前没有登录，公开 IP 上建议只给自己用，或加 Nginx Basic Auth。
- 反向代理加 Gzip/HTTP2：Nginx 已启用默认配置，HTTPS 后会更快。

## 9. 回滚

```bash
cd /opt/clipdock
git log --oneline -5
git checkout <之前的提交>
sudo systemctl restart clipdock
```
