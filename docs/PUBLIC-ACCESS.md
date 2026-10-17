# 让全国任意电脑访问（公网访问）

## 结论

能。三种做法，按门槛从低到高：

| 方案 | 成本 | 上手时间 | 地址形式 | 适合 |
| --- | --- | --- | --- | --- |
| **Cloudflare Tunnel** | 免费 | 5 分钟 | `https://xxx.trycloudflare.com` | 试用期、临时演示 |
| 云服务器 + 域名 | 约 100 元/月起 + 域名 | 1–3 周（国内备案） | `https://your.domain` | 正式上线 |
| 其他内网穿透（花生壳 / frp / ngrok） | 免费到几十元 | 10 分钟 | 各不相同 | 临时救急 |

共同点：**你的电脑（或服务器）必须一直开着**，页面才打得开。

---

## 方案一：Cloudflare Tunnel（推荐先用这个）

原理：在你电脑上开一条隧道，Cloudflare 给你一个公网 HTTPS 地址，流量转发到本机 8081。
不用公网 IP、不用域名、不用备案，数据仍在你电脑上。

### 1. 安装 cloudflared

任选一种：

```powershell
winget install --id Cloudflare.cloudflared
```

或从 <https://github.com/cloudflare/cloudflared/releases/latest> 下载
`cloudflared-windows-amd64.exe`，改名 `cloudflared.exe` 放进一个 PATH 目录（比如 `C:\Windows`）。

### 2. 双击 `start-public-8081.bat`

脚本会：
1. 用 `--trial --port 8081` 启动后端（只监听本机，由隧道对外转发）；
2. 启动 cloudflared 并打印一个 `https://xxxx.trycloudflare.com` 地址。

### 3. 验证

手机**关掉 WiFi、用 4G** 打开那个 `https://` 地址：
- 能看到首页 = 公网通了；
- 能登录 = 数据库和账号都是你本机这份。

### 4. 发给别人

把地址发微信/QQ 即可，全国任意网络都能打开。

### 注意

- 免费临时域名**每次重启都会变**，重启后要重新发地址。
- 关掉黑窗口或电脑关机，地址立刻失效。
- 想固定域名：注册 Cloudflare 账号 + 自己的域名，改用 named tunnel（`cloudflared tunnel create`）。
- 微信里打开 https 地址一般正常；小程序仍受「request 合法域名必须备案」限制，不能直接用这个域名。

---

## 方案二：云服务器（正式上线）

适合长期对外开放。国内服务器必须完成 **ICP 备案**（域名 + 服务器）。

1. 买一台云服务器（1 核 2G 足够）+ 一个域名，完成备案。
2. 把项目拷上去，装 Python 3.8+ 和 `Pillow`（`pip install -r requirements.txt`）。
3. 后端只绑本机：`python server.py --trial --port 8081`。
4. Nginx 反代 + HTTPS 证书（Let's Encrypt 免费）：

```nginx
server {
    listen 443 ssl http2;
    server_name your.domain;
    ssl_certificate     /etc/letsencrypt/live/your.domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain/privkey.pem;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

5. 后端会把 `X-Forwarded-Proto` 用于 Origin 校验，反代下不用手填 `--public-origin`。
   若要强绑定：`--public-origin https://your.domain --trust-proxy`。
6. 数据目录 `var-trial/` 记得纳入备份（`manage_trial.py` 有备份命令）。

---

## 方案三：其他内网穿透

- **花生壳**：国内，需实名，免费版限流量。
- **frp**：需要一台有公网 IP 的服务器做服务端，配置稍多但可控。
- **ngrok**：免费版有随机域名 + 浏览器提示页，不适合给同学直接看。

原理与 Cloudflare Tunnel 相同：把本机 8081 映射到一个公网地址。

---

## 安全与合规（务必读完）

1. **公网暴露 = 任何人都能访问登录页**。项目已有限流与失败锁定，但请把管理员密码设强，不要外泄。
2. **管理员初始密码**在数据目录的 `admin-initial-password.txt`，首次登录后请改掉并删除该文件。
3. **不要在试用环境放真实身份证、宿舍号、银行卡**。现在库里是模拟数据，但同学注册时会填真实手机号——公网期间等于把这些信息放在了公网上。
4. **国内正式对外提供服务涉及备案与个人信息保护要求**。校内小范围试用建议用 Cloudflare Tunnel，用完即关。
5. 公网期间建议把 `--trial` 的注册入口盯紧，发现异常账号及时停用/封禁。
