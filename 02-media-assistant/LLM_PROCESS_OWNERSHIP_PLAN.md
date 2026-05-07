# LLM 进程所有权与生命周期治理方案

## 背景

当前本地 LLM 服务由 `llm_manager.py` 负责拉起与停止，但现状存在几个结构性问题：

1. 状态检查会隐式启动模型，页面轮询可能导致模型长期驻留。
2. `8080` 端口上若已有 `llama-server`，当前实现会“借用”该服务，但并未真正接管其生命周期。
3. 为清理端口冲突，当前逻辑会按端口杀进程，存在误杀用户其他项目 `llama-server` 的风险。
4. `llm_status`、`check_services`、`llm_stop` 三者对“谁拥有这个进程”的认知并不一致。
5. 没有空闲自动回收，未使用时仍持续占用端口、内存与模型加载时间窗口。

本方案的目标是建立“明确所有权、按需启动、空闲释放、状态一致”的本地 LLM 管理机制。

## 目标

1. 只有真实推理请求才拉起本地模型。
2. 只有当前应用自己启动的进程，才允许被本应用停止或回收。
3. 不再通过“端口上有健康服务”来默认接管外部进程。
4. 当模型空闲一段时间后自动释放端口和内存。
5. 所有状态接口输出一致，用户能明确看出：未启动、启动中、运行中、空闲待回收、外部占用冲突。

## 非目标

1. 不做多模型并行常驻。
2. 不做跨应用共享同一个 `llama-server` 的资源池。
3. 不在本期解决 GPU/Metal 显存细粒度统计。

## 设计原则

### 1. 所有权优先于可达性

`health_check == true` 只能说明端口上有服务，不代表该服务属于当前应用。

后续所有生命周期操作必须先回答两个问题：

1. 这个 `llama-server` 是不是我启动的。
2. 我有没有它的 ownership record。

只有答案都为“是”，才能执行 stop、reload、idle unload。

### 2. 状态检查不能改变状态

`check_services`、页面轮询、状态面板只能读状态，不能触发模型加载。

也就是说：

1. 状态接口只能看文件是否存在、记录是否存在、进程是否还活着、端口是否健康。
2. 真正的启动动作只能发生在翻译、画面分析、总结等推理入口，或显式的“手动启动”接口。

### 3. 进程管理必须可回溯

应用启动本地模型时，必须同步写下 ownership record，包含：

1. `app_pid` — 当前应用（Python 后端）的进程 ID，作为唯一归属标识
2. `llm_pid`
3. `port`
4. `model_path`
5. `mmproj_path`
6. `started_at`
7. `last_used_at`
8. `inflight_requests`

建议存放路径：

`<config_dir>/runtime/llm-owner.json`

**为什么用 `app_pid` 而不用 UUID？**

本项目是单进程 Python 后端 + 单进程 Electron 的桌面应用：
- 应用重启 → `app_pid` 变了 → stale record
- 应用崩溃 → `app_pid` 进程不存在 → stale record
- 两个实例同时运行 → `app_pid` 不同 → 外部占用

UUID 方案适合多实例 / 分布式场景，在本项目中只会增加判定分支但不提供额外安全性。

### 4. 内存引用 `_process` 与文件 record 的主从关系

- **`self._process`（Popen 对象）是权威来源**，文件 record 是跨重启的补充。
- 启动时：先 `Popen` 成功拿到 pid，再写 record 文件。
- 停止时：先通过 `self._process` 发信号，进程退出后再删 record。
- 应用正常退出时（`atexit` / `SIGTERM` handler）同步清理 record 文件。
- 若 record 写入成功但 `_process` 后续意外 None（极端情况），下次 `ensure_running` 时通过 stale record 检测清理。

## 核心机制

## 1. Ownership Record

新增一个统一的数据结构：

```json
{
  "app_pid": 12345,
  "llm_pid": 45678,
  "port": 8080,
  "model_path": "/path/to/model.gguf",
  "mmproj_path": "/path/to/mmproj.gguf",
  "started_at": 1710000000,
  "last_used_at": 1710000123,
  "inflight_requests": 0,
  "status": "starting"
}
```

`status` 建议使用以下枚举：

1. `stopped`
2. `starting`
3. `ready`
4. `stopping`
5. `error`

本地模型进程启动成功后写入；进程退出或 stop 成功后删除。

## 2. 所有权判定规则

### 2.1 我方拥有的进程

满足以下**全部**条件时，判定为"我方进程"：

1. ownership record 存在。
2. record 中 `app_pid == os.getpid()`（当前应用实例启动的）。
3. record 中 `llm_pid` 对应进程仍存活。

> 注意：不做命令行比对。macOS `ps -o command=` 会截断长路径（通常 1024 字符），模型路径往往超过此限制，用命令行匹配做归属验证不可靠。

### 2.2 Stale Record（崩溃残留）

满足以下条件时，判定为 stale record：

1. record 中 `app_pid` 对应进程已不存在。
2. 或 record 中 `llm_pid` 对应进程已不存在。

stale record 应被自动清理。若 `llm_pid` 仍存活但 `app_pid` 已死，说明是上次崩溃残留的 llama-server，可安全停止后清理。

### 2.3 外部进程

满足以下任意条件时，判定为"外部进程"：

1. 端口健康，但没有 ownership record。
2. 有 record，但 `app_pid` 对应的进程仍存活，且 `app_pid != os.getpid()`（另一个应用实例启动的）。

外部进程只能被报告冲突，不能被自动 stop，更不能被按端口误杀。

## 3. 启动策略

### 3.1 被动状态检查

`check_services` 只返回如下信息，不触发启动：

1. `model_present`
2. `ownership_state`
3. `port_state`
4. `healthy`
5. `vision_capable`
6. `status_text`

若发现端口上有外部进程，返回：

1. `llm: false`
2. `llm_detail: local-port-conflict-external-owner`
3. `llm_text: 端口 8080 被外部 llama-server 占用`

### 3.2 按需启动

只有以下入口调用 `ensure_running_for_inference()`：

1. 翻译
2. 单帧分析
3. 多帧分析
4. 总结生成
5. 手动预热接口

启动流程：

1. 若 ownership record 有效且进程健康，直接复用。
2. 若 ownership record 有效但进程已死，清理 stale record。
3. 若端口有外部进程，直接报冲突，不启动。
4. 若端口空闲，则拉起新进程并写入 ownership record。
5. 等待 `/health` 就绪后将 `status` 更新为 `ready`。

## 4. 停止策略

### 4.1 显式停止

`/api/llm_stop` 只允许停止“我方拥有的进程”。

流程：

1. 读取 ownership record。
2. 校验 `llm_pid` 是否仍是该模型进程。
3. 将状态改为 `stopping`。
4. 发 `SIGTERM`，等待一段时间。
5. 超时后仅对该 `llm_pid` 发 `SIGKILL`。
6. 删除 ownership record。

绝不再使用“按端口枚举 + 杀掉所有 llama-server”的方式。

### 4.2 配置切换停止

当模型路径、mmproj、api_base 从本地切到外部，或模型切换时：

1. 仅停止我方拥有的进程。
2. 如果端口上是外部进程，则只提示冲突，不做 kill。

## 5. 空闲自动回收

### 5.1 触发条件

引入空闲回收器线程或定时任务，每 30 秒检查一次：

1. ownership record 是否存在。
2. `inflight_requests == 0`
3. `now - last_used_at >= idle_timeout_seconds`

建议默认值：

`idle_timeout_seconds = 300`

即 5 分钟未使用自动停止本地模型。

### 5.2 使用计数

在每个真实推理入口外围加一个统一上下文，例如：

1. 请求开始前 `inflight_requests += 1`
2. 同时刷新 `last_used_at`
3. 请求结束后 `inflight_requests -= 1`
4. 无论成功失败都要在 `finally` 中执行

**线程安全**：FastAPI (uvicorn) 下推理请求可能并发，`inflight_requests` 的读写必须用 `threading.Lock` 保护。建议在 `LLMManager` 中封装 `acquire_inference()` / `release_inference()` 方法，内部持锁操作计数器并刷新 `last_used_at`。

这样可防止长任务执行中被误回收。

### 5.3 状态呈现

空闲中但仍驻留时，状态接口可返回：

1. `status = ready`
2. `idle_seconds = N`
3. `will_auto_stop_in = max(0, idle_timeout - idle_seconds)`

前端可展示：

`就绪 · 本地模型 · 空闲中`

> 不做精确倒计时显示。倒计时需要高频轮询或 WebSocket，实现成本高但用户价值有限。

## 6. 状态机

```text
stopped
  -> starting      真实推理请求触发启动

starting
  -> ready         /health 成功
  -> error         进程退出或超时

ready
  -> stopping      手动停止 / 配置切换 / 空闲超时
  -> ready         新请求刷新 last_used_at

stopping
  -> stopped       进程退出并清理 record
  -> error         清理失败

error
  -> starting      下一次真实推理请求重试
```

> `conflict`（外部进程占用端口）不是进程的状态，而是 `check_services` 返回值中的一个布尔字段 `external_conflict: true/false`。
> 状态机只管理"我方进程"的生命周期，与外部进程检测解耦。

## 7. 接口调整建议

### 7.1 `/api/check_services`

改为纯只读，不启动服务。

建议返回新增字段：

1. `llm_owned`
2. `llm_running`
3. `llm_healthy`
4. `llm_conflict`
5. `llm_idle_seconds`
6. `llm_auto_stop_in`

### 7.2 `/api/llm_status`

应返回完整 ownership 视角：

1. `owned_by_app`
2. `owner_record_present`
3. `pid`
4. `status`
5. `healthy`
6. `model`
7. `mmproj`
8. `vision_capable`
9. `idle_seconds`
10. `external_conflict`

### 7.3 `/api/llm_start`

去掉旧 `mode` 参数。

只保留显式预热语义：

```json
{ "prewarm": true }
```

**语义**：预热为异步操作，接口立即返回 `202 Accepted`，后台启动进程。前端通过轮询 `check_services` 获取启动进度。不阻塞 HTTP 请求。

如果端口上是外部进程，返回明确冲突错误而不是尝试接管。

### 7.4 `/api/llm_stop`

只停止本应用拥有的进程；若当前为外部进程占用，返回：

```json
{
  "success": false,
  "reason": "external-owner"
}
```

## 8. 前端行为调整

### 8.1 去掉“状态即保活”

前端轮询 `check_services` 可以保留，但该接口必须是纯只读，因此不再导致模型被拉起。

### 8.2 增加“手动预热/释放”可视入口

建议在设置面板或状态栏增加两个按钮：

1. `预热本地模型`
2. `释放本地模型`

这样用户可以主动管理内存占用。

### 8.3 状态文案

建议区分以下状态：

1. `未启动`：模型存在，但当前未加载
2. `启动中`：正在加载 GGUF
3. `就绪`：可立即推理
4. `就绪 · 空闲中`：模型已加载但当前无请求，超时后将自动释放
5. `外部进程占用`：端口冲突，当前应用不接管

## 9. 日志要求

新增以下日志事件，便于排查：

1. `owner-record-created`
2. `owner-record-loaded`
3. `owner-record-stale`
4. `owner-record-removed`
5. `external-port-conflict`
6. `idle-timer-refresh`
7. `idle-auto-stop`
8. `stop-skipped-external-owner`

## 10. 兼容性与迁移

### 10.1 向后兼容

现有配置文件无需变更。

新增 runtime record 文件属于临时运行态，不写入主配置。

### 10.2 首次上线行为

上线后若检测到 `8080` 端口已有健康服务但无 ownership record：

1. 不接管
2. 不 stop
3. 标记为冲突
4. 提示用户关闭外部进程或切换端口

这是本方案最重要的安全边界。

### 10.3 外部 API 旁路

当用户配置 `api_base` 指向非本地地址（即不是 `http://127.0.0.1:{port}/v1`）时，说明使用的是外部服务（如 OpenAI、云端 Qwen）：

1. `ensure_running_for_inference()` 直接跳过，不启动本地进程。
2. `check_services` 中 LLM 状态标记为 `external`，不做本地进程检测。
3. 所有本地进程管理逻辑（ownership record、idle reaper、port conflict）不介入。

### 10.4 端口可配置

当前端口硬编码为 `LLM_PORT = 8080`。若后续支持端口配置：

1. 端口变更等同于模型切换 — 先 stop 旧端口进程，再以新端口启动。
2. ownership record 中的 `port` 必须与实际启动端口一致。
3. 切换端口时，旧 record 标记为 stale 并清理。

## 11. 实施步骤

### Phase 1：只读状态与所有权落盘

1. 新增 ownership record 读写封装
2. 新增 `is_owned_process()` / `detect_external_conflict()` / `detect_stale_record()`
3. 改造 `check_services` 和 `llm_status` 为纯只读
4. 增加 `atexit` / `SIGTERM` handler，应用退出时清理 record 文件
5. 应用启动时检测 stale record：若 `app_pid` 已死则清理 record，若残留 `llm_pid` 仍存活则安全停止
6. 增加外部 API 旁路判断（`api_base` 非本地时跳过所有本地管理）

### Phase 2：启动/停止治理

1. 改造 `start()` 仅在端口空闲时启动
2. 改造 `stop()` 只停止我方进程
3. 删除按端口误杀逻辑 `_kill_port_occupant()`
4. 修复 `/api/llm_start` 过期 `mode` 语义，改为异步预热

### Phase 3：空闲自动回收

1. 增加 `last_used_at` 和 `inflight_requests`（`threading.Lock` 保护）
2. 封装 `acquire_inference()` / `release_inference()` 方法
3. 为所有推理入口增加使用计数包装
4. 增加 idle reaper 后台线程

### Phase 4：前端提示与手动控制（可与 Phase 1 并行）

1. 状态文案升级
2. 新增“预热”和“释放”按钮
3. 展示冲突提示与空闲状态（不做精确倒计时）

## 12. 验证用例

### 用例 1：打开页面但不做推理

预期：

1. `check_services` 显示模型存在但未启动
2. 本地 `llama-server` 不被拉起

### 用例 2：开始翻译

预期：

1. 首次请求触发启动
2. ownership record 创建
3. 任务完成后模型保持 ready，等待 idle timeout

### 用例 3：空闲超时

预期：

1. 超时后自动 stop
2. 端口释放
3. ownership record 删除

### 用例 4：外部 llama-server 占用 8080

预期：

1. 页面显示冲突
2. 本应用不 stop 外部进程
3. 本应用不接管该进程

### 用例 5：应用崩溃后重开

预期：

1. stale record 能被识别并清理
2. 若旧进程仍活着但属于当前实例残留，可选择恢复或安全停止后重启

## 13. 推荐结论

建议按以下原则实施：

1. 状态接口只读。
2. 真实推理才启动模型。
3. 只管理自己启动的进程。
4. 空闲自动释放。
5. 遇到端口冲突，只报告，不接管，不误杀。

这是当前代码基础上最稳妥、风险最低、也最符合“未使用对应模型时避免持续占用端口资源或内存”的治理方案。