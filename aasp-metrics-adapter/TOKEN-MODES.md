# Token 两种使用模式说明

AASP Metrics Adapter 访问预测 API 需要 `X-Auth-Token`（或 Bearer）。Token 有时效，本组件支持两种用法，**可并存**：

| 模式 | 一句话 | 何时用 |
|------|--------|--------|
| **模式 A：手动 Token** | 只往 Secret 里填/更新 Token | 联调、PoC、暂时不想把 IAM 密码放进集群 |
| **模式 B：IAM 自动重登** | 再配 IAM 账号，401 时 Adapter 自己换票 | 长期跑、不想因过期反复滚 Pod |

未配置 IAM 密码时，行为与「只有手动」完全一致。

---

## 模式对照

```text
模式 A（手动）
  人/脚本 → IAM 拿 Token → Secret(token) → Pod env TOKEN
  过期后：再更新 Secret + 删除/重建 Pod

模式 B（自动重登）
  Secret(token 可选种子) + Secret(iam-password) + IAM_* env
  启动可用手上的 Token；AASP 返回 401/403（或临近过期）
    → Adapter POST IAM /v3/auth/tokens
    → 读响应头 X-Subject-Token
    → 写入进程内存 → 重试 AASP（一般无需重启 Pod）
```

| 项 | 模式 A | 模式 B |
|----|--------|--------|
| 必填 | `TOKEN` | `IAM_AUTH_URL`、`IAM_USER`、`IAM_PASSWORD`、`IAM_DOMAIN`，以及 `IAM_PROJECT_NAME` **或** `IAM_PROJECT_ID` |
| 可选 | — | 初始 `TOKEN`（有则先用，过期再自动换） |
| 过期处理 | 运维更新 Secret + 重建 Pod | 进程内换票；日志有 `IAM token refreshed` |
| 集群内敏感信息 | 仅短期 Token | Token + IAM 用户密码（权限面更大，单独 Secret） |
| 网络 | 能访问 AASP | 能访问 **AASP + IAM** |
| 镜像 | 任意已部署版 | 建议 **0.5.0+**（含自动重登） |

---

## 模式 A：手动填写 Token

### 1. 用 IAM 拿票（在笔记本/跳板机）

```bash
IAM_URL="https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true"
# HCS 请换成实验室 IAM 地址

RESP_HEADERS=$(mktemp)
curl -sS -D "$RESP_HEADERS" -o /tmp/iam-body.json \
  -H "Content-Type: application/json" \
  -d '{
    "auth": {
      "identity": {
        "methods": ["password"],
        "password": {
          "user": {
            "domain": { "name": "<IAMDomain>" },
            "name": "<IAMUser>",
            "password": "<IAMPassword>"
          }
        }
      },
      "scope": {
        "project": { "name": "cn-north-5" }
      }
    }
  }' \
  "$IAM_URL"

token=$(awk 'BEGIN{IGNORECASE=1} /^X-Subject-Token:/ {print $2}' "$RESP_HEADERS" | tr -d '\r')
echo "TOKEN_LEN=${#token}"
```

也可用 `"project": { "id": "<PROJECT_ID>" }` 做 scope。

### 2. 写入集群 Secret

```bash
NS=aasp-scale-demo
kubectl -n "$NS" create secret generic aasp-api-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 3. ModelServing 只挂 TOKEN（不要配 IAM_PASSWORD）

```yaml
- name: AUTH_HEADER
  value: "x-auth-token"
- name: TOKEN
  valueFrom:
    secretKeyRef:
      name: aasp-api-token
      key: token
# 不要设置 IAM_USER / IAM_PASSWORD 等，保持手动模式
```

### 4. Token 过期后

```bash
# 重新执行步骤 1 得到新 token，再：
kubectl -n "$NS" create secret generic aasp-api-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -

# env 不会热更新，必须重建 Pod
kubectl -n "$NS" get pods -o name | grep mock-predict | xargs -r kubectl -n "$NS" delete pod
```

### 5. 验证

```bash
POD=$(kubectl -n "$NS" get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}')
kubectl -n "$NS" logs "$POD" --tail=20 | grep 'updated peaks'
# 启动日志应含：iam_auto_refresh=False
```

---

## 模式 B：IAM 自动重登（保留可选手填）

### 启用条件（需全部满足）

- `IAM_AUTH_URL`
- `IAM_USER`
- `IAM_PASSWORD`
- `IAM_DOMAIN`
- `IAM_PROJECT_NAME` **或** `IAM_PROJECT_ID`

缺任一密码/项目字段 → 仍走模式 A。

### 1. Secret：Token（可选）+ IAM 密码

```bash
NS=aasp-scale-demo
kubectl -n "$NS" create secret generic aasp-api-token \
  --from-literal=token="$token" \
  --from-literal=iam-password="$IAM_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
```

`token` 可先塞一个当前有效票；也可以不放（空），启动后靠 IAM 登录（需网络与账号正确）。

### 2. ModelServing 增加 IAM 环境变量

```yaml
- name: AUTH_HEADER
  value: "x-auth-token"
- name: TOKEN
  valueFrom:
    secretKeyRef:
      name: aasp-api-token
      key: token
      optional: true          # 若允许无初始 token；否则可去掉 optional
- name: IAM_AUTH_URL
  value: "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true"
- name: IAM_DOMAIN
  value: "<账号域名>"
- name: IAM_USER
  value: "<IAM用户名>"
- name: IAM_PASSWORD
  valueFrom:
    secretKeyRef:
      name: aasp-api-token
      key: iam-password
- name: IAM_PROJECT_NAME
  value: "cn-north-5"
# 或：
# - name: IAM_PROJECT_ID
#   value: "5dfed145e29a43f7b42c5ecc17d4d98c"
# 可选：
# - name: IAM_REFRESH_SKEW_SECONDS
#   value: "300"   # 过期前 5 分钟预刷新
```

HCS 实验室请把 `IAM_AUTH_URL` 换成**内网真实 IAM 地址**；Pod 必须能访问该地址。

### 3. 运行时行为

1. 优先用当前内存中的 Token（启动时来自 `TOKEN` env）。  
2. 若已知 `expires_at` 且进入 `IAM_REFRESH_SKEW_SECONDS` 窗口 → 预刷新。  
3. 调 AASP 若 **401/403** → 调 IAM 换票 → **同一轮再请求一次** AASP。  
4. 新票只在 **进程内存**；不自动写回 K8s Secret（避免额外 RBAC）。  

### 4. 验证

```bash
POD=$(kubectl -n "$NS" get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}')

# 启动应看到 iam_auto_refresh=True
kubectl -n "$NS" logs "$POD" | head -5

# 正常拉取
kubectl -n "$NS" logs "$POD" --tail=30 | grep -E 'updated peaks|IAM token refreshed'

# 可看是否配了 IAM（不要打印密码）
kubectl -n "$NS" exec "$POD" -- env | grep -E '^IAM_|^AUTH_HEADER|^TOKEN' | sed 's/TOKEN=.*/TOKEN=***/;s/IAM_PASSWORD=.*/IAM_PASSWORD=***/'
```

人为验证重登：把 Secret 里的 `token` 改成乱码并重建 Pod，若 IAM 配置正确，日志应出现 `AASP HTTP 401; attempting IAM re-login` → `IAM token refreshed` → `updated peaks`。

---

## 怎么选

| 场景 | 建议 |
|------|------|
| 第一次打通 AASP / 演示 | **模式 A** |
| 线上常驻、Token 几小时就过期 | **模式 B** |
| 安全要求不能把 IAM 密码放进业务 ns | 保持 **A**，用外部 CronJob 只更新 `token` |
| 已开 B，仍想偶尔手填新票 | 可以：更新 Secret `token` 并滚 Pod，或等 401 走自动逻辑 |

---

## 常见问题

**Q: 配了 IAM 但日志仍是 `iam_auto_refresh=False`？**  
检查是否缺 `IAM_PASSWORD` / domain / user / project；改 env 后需重建 Pod。

**Q: 自动重登后 `kubectl get secret` 里的 token 还是旧的？**  
正常。刷新在内存里；Secret 可仍作种子或不管。

**Q: IAM 也 401/403？**  
账号、密码、domain、project name/id、IAM URL（公有云 vs HCS）是否正确；是否被安全组拦住。

**Q: 和选主、扩缩容的关系？**  
无关。只有 **Leader** 会拉 AASP / 调 IAM；Follower 不访问。

**Q: 镜像版本？**  
自动重登需要包含该功能的构建（文档建议 **0.5.0+**）。旧镜像只有模式 A。

---

## 相关文件

- 实现：`adapter.py`（`iam_auto_refresh_enabled` / `fetch_iam_token` / 401 重试）  
- **完整样例（Secret + ModelServing）：** [`deploy-mode-b.example.yaml`](./deploy-mode-b.example.yaml)  
- 示例注释：`deploy-real-env.notes.yaml`  
- 真机步骤：`REAL-SCENARIO-TEST-GUIDE.md` §4.2  
- 设计背景：`DESIGN.md` §3.4  
