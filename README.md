# Trading Frameworks — 多大师投资框架知识库

> **Public repository** — no holdings data, no personal information.
> Three master investor frameworks, serial pipeline, zero manual input.

[![Test](https://github.com/alex00ccc-lab/trading-frameworks/actions/workflows/test.yml/badge.svg)](https://github.com/alex00ccc-lab/trading-frameworks/actions/workflows/test.yml)
[![Pages](https://github.com/alex00ccc-lab/trading-frameworks/actions/workflows/pages.yml/badge.svg)](https://github.com/alex00ccc-lab/trading-frameworks/actions/workflows/pages.yml)

---

## 目录

- [框架概览](#框架概览)
- [串联执行流](#串联执行流)
- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [策略模式](#策略模式)
- [与下游项目集成](#与下游项目集成)
- [大股东持仓追踪](#大股东持仓追踪)
- [设计原则](#设计原则)

---

## 框架概览

| 大师 | 角色 | 维度 | 门槛 | 核心问题 |
|------|------|------|------|---------|
| **段永平** | 🚪 第一关 | 4 维 / 100 分 | ≥ 60 | 能不能买？ |
| **霍华德·马克斯** | 🔄 第二关 | 3 维 / 100 分 | ≥ 50 | 什么时候买？ |
| **董艺婷** | ⚙️ 第三关 | 10 维 + 8 红线 | ≥ 60/50 | 买多少？怎么管？ |

---

## 串联执行流

```
买入决策流程:

  ┌─────────────┐    段永平得分 ≥ 60？
  │ 段永平门槛   │──▶ NO  → 🚫 一票否决（不在能力圈/没安全边际）
  │ (能不能买)  │    YES → 继续
  └──────┬──────┘
         ▼
  ┌─────────────┐    马克斯周期分 ≥ 50？
  │ 马克斯时机   │──▶ NO  → 🟡 暂缓（周期不对，等信号）
  │ (什么时候买)│    YES → 继续
  └──────┬──────┘
         ▼
  ┌─────────────┐    董艺婷综合评分 →
  │ 董艺婷执行   │    仓位上限 / 止损位 / 加仓节奏 / 行业约束
  │ (买多少/管) │
  └─────────────┘
```

⚠️ **三框架是串联关系，不是加权平均。** 段永平关不通过 = 直接否决，不继续。

---

## 仓库结构

```
trading-frameworks/
├── README.md
├── .gitignore
├── config/
│   ├── frame_const.yaml           # 统一阈值配置
│   ├── strategy_weight.yaml       # 策略启用/禁用开关
│   └── tracked_holders.yaml       # 大股东追踪配置
├── master_router.py               # 三框架串联调度入口
├── shareholder_tracker.py         # 大股东申报分类 + 噪音过滤
├── data_fetch_base.py             # 统一抓取基类（限速/缓存/退避）
│
├── duan_yongping/
│   ├── framework.md               # 段永平方法论
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── duan_score.py          # 四维纯函数
│   └── dsa-strategies/
│       └── duan-yongping.yml
│
├── howard_marks/
│   ├── framework.md               # 马克斯方法论
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── marks_score.py         # 三维纯函数
│   └── dsa-strategies/
│       └── howard-marks.yml
│
├── dong_yiting/
│   ├── framework.md               # 董艺婷方法论
│   ├── backtest-validation.md     # 216笔回溯验证
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── dual_track.py          # 双轨10维纯函数
│   └── dsa-strategies/
│       ├── dong-yiting-defensive.yml
│       ├── dong-yiting-cyclical.yml
│       ├── dong-yiting-industry.yml
│       └── master-combined.yml
│
├── tests/
│   ├── test_scoring.py
│   └── test_shareholder.py
│
├── cache/                         # CI 预计算缓存（gitignored）
│   ├── shareholder/.gitkeep
│   └── frame_score/.gitkeep
│
└── .github/workflows/
    ├── test.yml                   # 每次 commit 跑 unit test
    └── pages.yml                  # GitHub Pages 发布
```

---

## 快速开始

```bash
# Clone
git clone https://github.com/alex00ccc-lab/trading-frameworks.git
cd trading-frameworks

# Run tests
python -m pytest tests/ -v

# Score a stock through all three frameworks
python -c "
from master_router import run_master_pipeline
result = run_master_pipeline('AAPL', mode='all',
    duan_params={'competence_level': 'GREEN', 'pe': 28, 'roe': 0.45, 'roic': 0.30},
    marks_params={'vix': 18, 'sector_momentum_30d': 5},
    dong_params={'business_moat': 22, 'cashflow_stability': 25},
    thesis_provided=True, in_circle_of_competence=True,
    has_margin_of_safety=True, position_within_limits=True, stop_loss_set=True,
)
print(result)
"
```

---

## 策略模式

| 模式 | CLI 参数 | 说明 |
|------|---------|------|
| 全部三关 | `--mode all` | 段永平 → 马克斯 → 董艺婷（默认） |
| 仅段永平 | `--mode duan` | 只看能力圈+安全边际 |
| 仅马克斯 | `--mode marks` | 只看周期+逆向 |
| 仅董艺婷 | `--mode dong` | 只看仓位管理 |
| 段+董 | `--mode duan+dong` | 跳过马克斯（确认可买后直接管仓位） |
| 极简 | `--mode common` | 仅 5 条通用铁律 |

---

## 与下游项目集成

### holdings-briefing (private)

```
holdings-briefing/
├── knowledge/
│   └── frameworks/          ← git submodule (this repo, locked to main)
├── scripts/
│   └── fund_risk_calc.py    ← imports from knowledge/frameworks
├── src/
│   ├── pre_trade_check.py   ← --mode duan|marks|dong|all|common
│   ├── rebalance_engine.py  ← uses dong-yiting scoring
│   └── trade_dashboard.py   ← Streamlit 6-tab console
```

### daily_stock_analysis (private)

DSA Agent loads YAML strategies from this repo's `dsa-strategies/` directories.
Natural language: "用段永平+董艺婷分析 AAPL"

---

## 大股东持仓追踪

自动追踪关键股东（如段永平在 9992.HK/AAPL）的持股变动：

| 功能 | 说明 |
|------|------|
| **真假甄别** | SEC Form 4 Table I/II 分类 / HKEX SFC DI 事件码 |
| **噪音过滤** | 三层过滤（单笔→30日滚动→行业叠加） |
| **大师联动** | 真实增持/减持自动修正框架打分 |
| **合规抓取** | 五层保障（硬约束→退避→缓存→切换→自愈） |

示例输出：
```
9992.HK 泡泡马特: 段永平 1203 期權行权交付
→ ⚠️ 非主动减持。市场恐慌下跌为误读。
→ 段永平未主动卖出任何持股，下跌可能是买入机会。
```

---

## 设计原则

1. **仅量化维度编码** — "企业文化""第二层思维"等不可量化维度不纳入代码，仅保留在框架文档中
2. **纯函数无状态** — 所有 `scoring/*.py` 无 IO、无全局变量、无 CLI、无 logger
3. **统一配置** — 所有阈值从 `config/frame_const.yaml` 读取
4. **零手动录入** — 所有框架维度使用 market_data 的自动指标替代
5. **降级兜底** — 任何数据缺失 → 返回中性分 + 警告标注，不崩溃、不空白、不阻断流程
6. **Public 仓库** — 不含任何持仓数据、交易记录、账户金额

---

*本仓库由 holdings-briefing v14 创建，作为多大师框架的单一事实来源。*
