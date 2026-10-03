# VendFill 售货机补货

按货道容量、库存与在途量计算缺口，生成不超缺口、非负的补货单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4800 |
| API | http://localhost:9800 |
| API 文档 | http://localhost:9800/docs |
| Postgres | localhost:5449 |

健康检查：`GET http://localhost:9800/api/health`

## 使用说明

1. 在「点位」「货道」查看售货机布局与库存。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量；未核销单可「核销」或「作废」。
4. 在「满仓」「汇总」查看已满货道与补货合计——均以最新一张**未作废**单为依据。

## 单据状态

- 补货单生成即为「未核销」；可**核销**（已装机器确认）或**作废**（开错/弃用）。
- 只有未核销单允许作废；已核销单禁止作废，作废请求返回 409 且单据、汇总、库存均不变。
- 作废只翻转单据状态：货道库存与在途保持不变，不会清零或改写。
- 作废后满仓与汇总回退到上一张未作废单；若不存在则显示「无有效单」。
- 核销与作废互斥：已核销单不能作废，已作废单不能核销。

## 开发与测试

```bash
docker compose exec api pytest -q
```
