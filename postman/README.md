# 转角 · Postman 接口自动化

针对 **本地 AI 客服服务**（`ai_service/server.py`，默认 `127.0.0.1:8093`）的接口自动化用例，  
纯 Postman 脚本实现，不需要写 Python。同一套集合也能用命令行（newman）跑，方便进 CI。

```
postman/
├── 转角AI客服.postman_collection.json          # 主集合：14 个请求 / 47 条断言
├── 转角AI客服-数据驱动回归.postman_collection.json  # 1 个请求 × N 行 CSV
├── 转角-本地8093.postman_environment.json      # 环境变量（baseUrl / token）
└── faq-cases.csv                              # 回归数据（UTF-8，勿用 GBK 保存）
```

---

## 1. 先跑起来

### 1.1 起服务

```powershell
cd "E:\zi\huali-corner-trial"
$env:HC_AI_MOCK="1"                     # 不花 token、不调 DeepSeek，先测接口行为
.\.venv-trial\Scripts\python.exe ai_service\server.py
```

看到 `AI 客服已启动：http://127.0.0.1:8093` 即可。浏览器打开 `http://127.0.0.1:8093/health` 应该有 JSON。

### 1.2 导入 Postman（中文界面）

1. 左上角 **导入** → 把两个 `.postman_collection.json` 和 `.postman_environment.json` 拖进去。
2. 右上角环境下拉框（默认「无环境」）→ 选 **转角-本地8093**。
3. 点开集合里的请求 → **发送**，看下方 **测试结果** 标签。

> 脚本写在哪：请求面板 **脚本 → 测试**（Tests）里；集合级的前置脚本在集合名右键 → **编辑 → 脚本 → 前置请求**。

### 1.3 命令行跑（推荐，能进 CI）

```powershell
npm i -g newman

cd "E:\zi\huali-corner-trial\postman"
newman run "转角AI客服.postman_collection.json" -e "转角-本地8093.postman_environment.json"

# 数据驱动回归：一行 CSV = 一次迭代
newman run "转角AI客服-数据驱动回归.postman_collection.json" `
  -e "转角-本地8093.postman_environment.json" -d faq-cases.csv
```

退出码非 0 = 有用例失败，可直接挂到 GitHub Actions / 本地提交前检查。

---

## 2. 脚本怎么写：本套用例用到的 5 个套路

### 套路一：断言不写「等于 200」就完事

```js
pm.test('状态码 200', () => pm.response.to.have.status(200));

const body = pm.response.json();          // 解析一次，复用

pm.test('ok 为 true',        () => pm.expect(body.ok).to.eql(true));
pm.test('知识库已索引',      () => pm.expect(body.chunks).to.be.above(0));
pm.test('模式是 mock 或 llm', () => pm.expect(body.mode).to.be.oneOf(['mock', 'llm']));
```

一条 `pm.test` 只断一件事：红了能一眼看出是「服务没起来」还是「知识库空了」。

### 套路二：集合级前置脚本统一加鉴权

不用每个请求手写 Header。在**集合**的前置脚本里：

```js
const token = pm.variables.get('token');
if (token) {
    pm.request.headers.upsert({ key: 'Authorization', value: 'Bearer ' + token });
}
```

服务端没设 `HC_AI_TOKEN` 时不加头，设了才加——同一套集合在两种环境下都能跑。

### 套路三：把响应里的值传给下一个请求

```js
pm.collectionVariables.set('faqTitle', body.sources[0].title);   // 存
// 下一个请求的 Body 里直接写 {{faqTitle}}（存的是变量名，不是值）
```

这是串起「登录 → 拿 token → 用 token 查数据」这类链路的唯一办法。

### 套路四：负向用例比正向更值钱

```
08 描述缺 title → 400      （必填项漏传不能变 500）
11 未知路径 → 404          （路由兜底不能抛堆栈）
12 非法 JSON → 400         （半截 JSON 不能把进程打挂）
```

### 套路五：数据驱动 + 条件断言

`faq-cases.csv` 每行是一道题：

```csv
question,expected_action,expected_keyword
怎么退款,reply,退款
我要转人工,transfer,人工
```

请求 Body 用 `{{question}}`，测试脚本用 `pm.iterationData.get(...)` 取值：

```js
const wantAction = String(pm.iterationData.get('expected_action') || '').trim();
if (wantAction) {
    pm.test(`[${q}] action = ${wantAction}`, () => pm.expect(body.action).to.eql(wantAction));
}
```

字段留空就自动跳过该断言——加题只改 CSV，不动脚本。  
**注意**：CSV 必须存成 UTF-8，用 Excel「另存为 GBK」会全是乱码。

---

## 3. 本套用例的现状（2026-10-22 实测）

| 集合     | 结果                         |
| ------ | -------------------------- |
| 主集合    | 14 请求 / 47 断言：**13 绿 1 红** |
| 数据驱动回归 | 11 次迭代 / 44 断言：**全绿**      |

### 红旗：`06 多轮对话（history 透传）` —— 这是个真 bug

带 `history` 的请求，服务端**直接断连**（客户端只看到 `socket hang up`），服务端 dmesg：

```text
File "ai_service\server.py", line 71, in _history
    if soc in rag.SOCIAL_REPLIES:
AttributeError: module 'rag' has no attribute 'SOCIAL_REPLIES'
```

原因：`rag.py` 里闲聊标签 `SOCIAL_REPLIES` 已经随「删除 sad/cheer/lonely 词表」那轮一起删掉了，  
但 `server.py` 的 `_history()` 还在引用。**影响**：网页客服的第二轮、第三轮对话在本地 8093 这条链路上会失败。

最小修法（二选一，改完重启服务）：

```python
# ai_service/server.py:71 —— 兼容写法，rag 里没有这个常量时当空表
if soc in getattr(rag, 'SOCIAL_REPLIES', {}):
```

```python
# 或者直接删掉 social 标签那段（现在规则已经不看这个标签了）
if role == 'user':
    depth = h.get('depth')
    if isinstance(depth, int) and 0 < depth < 99:
        item['depth'] = depth
```

修好后 `06` 应当变绿；这条用例就是为它留下的回归防线。

---

## 4. 想扩到主站接口（8081）怎么加

主站（`Backend mission/server.py`）比 AI 服务多一道门槛：**要登录拿 token**。标准三步：

1. 新建文件夹 `40 · 主站`，第一个请求 `POST {{baseUrl}}/api/auth/login`  
   （试运营账号：卖家 `13800000001` / 买家 `13800000002` / 客服 `13800000003`，密码见 `docs/TRIAL.md`）。
2. 该请求的**测试**里存 token：
   ```js
   pm.collectionVariables.set('userToken', pm.response.json().token);
   ```
3. 后续请求在 Header 加 `Authorization: Bearer {{userToken}}`（或改成集合级前置脚本按文件夹判断）。

注意：主站点端口是 **8081**（`--trial` 模式），别和 AI 服务的 8093 混；两个服务都要在跑。

---

## 5. 常见坑

| 现象                      | 原因 / 处理                                                                      |
| ----------------------- | ---------------------------------------------------------------------------- |
| 全部请求 502 / 连接被拒         | 本地代理把 `127.0.0.1` 也代理走了；Postman 设置 → 代理 → 关掉「使用系统代理」，或加 `NO_PROXY=127.0.0.1` |
| `mode=mock` 但断言期望 `llm` | 你启动时带了 `HC_AI_MOCK=1`；不设这个变量才会真的调 DeepSeek                                   |
| 改完 `faq.md` 答案没变        | 先 `python ai_service/ingest.py`，再 `POST /reload`（集合里的 14 号用例）                |
| 401 全红                  | 服务端设了 `HC_AI_TOKEN`，但环境里 `token` 没填                                          |
| 跑完发现数据被改                | 这套用例**只读**，唯一有副作用的是 `/reload`（只重载内存索引）                                       |
