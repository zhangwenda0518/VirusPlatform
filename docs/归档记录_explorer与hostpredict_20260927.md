# 归档：病毒浏览器（Explorer）+ /hostpredict 孤儿页（2026-09-27）

本次归档把两套已下线入口的代码**彻底移出活动代码库**（此前 2026-09-17 只摘除了
蓝图挂载、代码留在盘上）。归档后 `/explorer`、`/api/explorer/*`、`/hostpredict`
均 404，属预期行为（`tests/_it_platform.py` 已有反向断言守护）。

## explorer/（病毒浏览器，7 页签）

| 归档内容 | 原位置 |
|---|---|
| `core/` | `Virus_Platform_Core/explorer/`（engine.py / shim.py / paths.py / virphykit_export.py / _smoke_test.py 等） |
| `web_explorer.py` | `Virus_Platform_Core/web/explorer.py`（蓝图：/explorer 页 + 14 个 /api/explorer/*；`_nan_to_null` 已先内联进 app.py 再归档） |
| `explorer.html` | `webapp/templates/explorer.html` |
| `app-explorer.js` | `webapp/static/app-explorer.js` |
| `tests/` | `tests/_check_explorer.py`、`_check_explorer_links.py`、`_check_virphykit_export.py`、`_check_decimal_year_conventions.py`（后两个原为未纳管文件） |
| `run_data/` | `run/explorer_exports/`、`run/explorer_variation/`（浏览器导出的运行期数据） |

时间线：2026-09-15 随「植物病毒进化分析平台」分蘖迁出导航；2026-09-17 摘除
app.py 蓝图注册（数据移 archive/_rmex_20260917/explorer）；2026-09-27 彻底归档。

## hostpredict/host_predict.html（/hostpredict 孤儿页）

宿主预测的**功能并未删除**，只删了无导航入口的孤儿页：

- 自动运行保留：contigs 分类完成后前端 `autoHostIfMissing()` 经
  `POST /api/tool/hostpredict_run`（`web/tool_results.py`）后台补跑 ICTV 宿主
  级联，结果并入该 contigs 运行目录（virus_contigs.tsv 增宿主列 + 分类报告）；
- 样品管道 ④（hostana）照旧，产物落 `08_host_analysis/`；
- 同步撤除：`/hostpredict` 页面路由（web/pages.py）、`TOOL_REGISTRY['hostpredict']`
  + `_tool_job_hostpredict`（tools_api.py / tool_jobs.py）、示例按钮与运行历史
  深链（examples.js / app-runhistory.js）、独立示例生成项
  （tests/make_example_results.py）。`examples/results/hostpredict/` 快照保留。

## 复用说明

如需找回其中代码，直接从本目录拷回即可；`_check_explorer.py` 等测试需临时把
explorer 蓝图挂回 app.py 并设 `VP_EXPLORER_DATA` 指向数据目录才能跑通。
