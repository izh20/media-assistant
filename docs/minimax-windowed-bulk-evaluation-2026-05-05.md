# MiniMax 分窗 Bulk 字幕评估报告

日期：2026-05-05

## 结论摘要

- 在固定 ASR、固定字幕切分、只替换翻译器的前提下，MiniMax-M2.7 在两部完整视频上的翻译质量均优于当前 Qwen batch 基线。
- 两部视频的简体中文字幕 text_similarity 平均提升 +0.0779，说明质量提升不是单片偶然现象。
- 时间轴没有变化，因此 generated_midpoint_hit_rate 基本不变，这符合实验设计预期。
- 当前最稳妥的工程结论是：MiniMax 适合作为外部高准确度翻译模式，但默认工程实现必须使用分窗 bulk，而不能使用整集 one-shot。

## 决策建议

- 产品默认策略：当外部翻译 provider 为 MiniMax 时，默认走 bulk 分窗翻译。
- 当前生产默认参数：max_items=80，max_chars=6000。
- 质量优先场景：优先推荐 MiniMax 分窗 bulk。
- 本地离线或成本优先场景：继续保留当前 Qwen batch 作为备选路径。
- 后续优化方向：将 100/7000 作为下一轮整集验证候选，但在拿到完整稳定性结果前不替换当前默认值。

## 评估范围

- 固定 ASR 输出，直接复用已经生成的日文 SRT。
- 只替换翻译阶段，不改动语音识别与时间轴。
- 对比当前 Qwen batch 基线与 MiniMax-M2.7 分窗 bulk 翻译效果。
- 评估对象为两部完整视频：Ginga S01E01 和 Hanzawa Naoki S02E05。

## 实验设置

- 基线报告：/tmp/media_subtitle_eval_faster_report.json
- MiniMax 报告：/tmp/media_subtitle_eval_minimax_bulk_report.json
- MiniMax 接口地址：https://api.minimaxi.com/v1
- MiniMax 模型：MiniMax-M2.7
- 已验证稳定的 bulk 参数：max_items=80，max_chars=6000

## 方法说明

本次对比始终复用同一份 ASR 结果、同一份日文字幕分段与同一套时间轴，只替换翻译器。这样可以把翻译质量与 Whisper 精度、字幕对齐能力分离开来，避免指标混杂。

评估指标：

- text_similarity：与参考字幕进行归一化后的文本相似度
- pair_similarity：与参考双语字幕进行双语对相似度比较
- generated_midpoint_hit_rate：生成字幕时间中点命中参考字幕区间的比例

## 评估结果

### Ginga S01E01

Qwen batch 基线：

- 翻译耗时：355.568 秒
- translated_vs_zh.text_similarity：0.3189
- translated_vs_zh_traditional.text_similarity：0.1770
- bilingual_vs_mul.pair_similarity：0.4609
- generated_midpoint_hit_rate：0.7068

MiniMax 分窗 bulk：

- 请求耗时：379.732 秒
- window_count：8
- translated_vs_zh.text_similarity：0.4113
- translated_vs_zh_traditional.text_similarity：0.1964
- bilingual_vs_mul.pair_similarity：0.4788
- generated_midpoint_hit_rate：0.7068

相对基线增量：

- translated_vs_zh.text_similarity：+0.0924
- translated_vs_zh_traditional.text_similarity：+0.0194
- bilingual_vs_mul.pair_similarity：+0.0179
- generated_midpoint_hit_rate：+0.0000

### Hanzawa Naoki S02E05

Qwen batch 基线：

- 翻译耗时：511.120 秒
- translated_vs_zh.text_similarity：0.3098
- generated_midpoint_hit_rate：0.8481

MiniMax 分窗 bulk：

- 请求耗时：857.185 秒
- window_count：13
- translated_vs_zh.text_similarity：0.3732
- generated_midpoint_hit_rate：0.8481

相对基线增量：

- translated_vs_zh.text_similarity：+0.0634
- generated_midpoint_hit_rate：+0.0000

## 总体结论

- 在两部完整视频上，MiniMax 的翻译质量都优于当前 Qwen batch 基线。
- 两部视频的简体中文字幕 text_similarity 平均提升为 +0.0779。
- 由于复用同一份日文 SRT 时间轴，时间对齐指标没有改善，midpoint hit rate 基本不变。
- MiniMax 在 Hanzawa 上明显慢于当前 Qwen batch，但质量提升稳定存在，因此仍适合作为外部高准确度翻译模式。

## 上线建议

- 已验证可上线的实现方式是“MiniMax 外部接口 + 分窗 bulk + 80/6000 默认窗口”。
- 不建议把整集 one-shot 翻译作为真实产品路径。
- 不建议在没有整集稳定性复核之前，直接把默认窗口提升到 100/7000。
- 前端无需强制改动请求体；后端已经可以在 MiniMax 外部模式下对空请求体自动选择 bulk。

## 工程发现

- 整集 one-shot 一次性翻译在字幕对齐场景下稳定性不够。
- 分窗 bulk 方案已经能稳定跑完整两部视频。
- MiniMax 返回格式并不完全稳定，既可能返回“带编号”的格式，也可能退化为“纯逐行文本”。
- 解析器必须同时兼容这两种输出形态，否则会出现整窗误判 missing 的假失败。

## 默认参数建议

- 对外部 MiniMax 翻译，默认应使用 bulk 分窗，而不是小 batch。
- 当前生产默认值继续保持 max_items=80、max_chars=6000。
- 调参入口可以作为高级选项保留，但默认路径应优先选择稳定性。

## 窄范围调参检查

为了避免每尝试一个参数组合都重跑整集，这里用 Hanzawa 前 240 条字幕做了一次低成本的判别性验证。

切片实测结果：

- 80/6000：122.818 秒，window_count=3，text_similarity=0.1596
- 60/4500：196.070 秒，window_count=4，text_similarity=0.1713
- 40/3000：191.082 秒，window_count=6，text_similarity=0.1580
- 80/6000 重跑：156.756 秒，window_count=3，text_similarity=0.1527
- 100/7000：137.262 秒，window_count=3，text_similarity=0.1579

结果解读：

- 更小的窗口在这个切片上明显更慢，不值得为了增加请求次数而采用。
- 100/7000 在一次同轮对比里略好于 80/6000 重跑结果，但远程调用延迟波动仍然较大，还不足以直接替换当前稳定默认值。
- 因此，生产集成继续使用 80/6000；100/7000 保留为下一轮整集验证的候选参数。

## 真实集成验证

除了离线评估脚本外，本轮还对真实产品路径做了两类验证。

### 1. Web 服务 smoke 验证

执行 02-media-assistant/smoke-web.sh 后，以下检查均已通过：

- 首页可正常打开
- /api/model_options 可正常返回模型候选
- /api/check_services 可正常返回当前服务状态
- /api/runtime_log 可正常返回运行日志

本次 smoke 输出显示：

- Whisper：就绪 · MLX · 内置模型
- LLM：未启动 · Qwen2-VL-7B-Instruct-Q4_K_M.gguf
- external_api：False

这说明当前“状态检查不自动拉起本地 LLM”的控制策略工作正常。

### 2. MiniMax 真实翻译路径 smoke 验证

为了验证真实翻译流程是否会在 MiniMax 外部模式下自动走 bulk，本轮直接调用了 step_translate 的真实入口，并故意传入空请求体。

验证条件：

- llm.api_base=https://api.minimaxi.com/v1
- llm.model=MiniMax-M2.7
- 请求体为空
- 输入为 3 条日文测试字幕

实际返回结果：

- message：翻译完成: 3 段
- strategy：bulk
- window_count：1
- max_items：80
- max_chars：6000

实际译文：

- おはようございます。 -> 早上好。
- 今日は会議があります。 -> 今天有会议。
- よろしくお願いします。 -> 请多关照。

结论：真实产品路径已经验证通过。在 MiniMax 外部接口模式下，即使前端 translate 请求不显式传 strategy，后端也会默认落到 bulk，并使用当前生产默认窗口参数 80/6000。