# stock_picker.py
# 全市场A股扫描（5000+）+ 美股 | 条件：量比>1 / 资金净流入 / KD金叉 / 站上MA5

import warnings
warnings.filterwarnings("ignore")

import akshare as ak
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from notifier import push_wechat

# ============================================================
# 美股池（A股全市场自动获取，无需手动配置）
# ============================================================
US_STOCK_POOL = [
    "AAPL", "MSFT", "NVDA", "TSLA", "META",
    "GOOGL", "AMZN", "AMD", "BABA", "PDD",
]

# ============================================================
# 指标计算
# ============================================================
def calc_kdj(df, n=9, m1=3, m2=3):
    low_n  = df["Low"].rolling(n).min()
    high_n = df["High"].rolling(n).max()
    rsv    = (df["Close"] - low_n) / (high_n - low_n + 1e-9) * 100

    K = pd.Series(50.0, index=df.index, dtype=float)
    D = pd.Series(50.0, index=df.index, dtype=float)
    for i in range(1, len(df)):
        K.iloc[i] = (m1-1)/m1 * K.iloc[i-1] + 1/m1 * rsv.iloc[i]
        D.iloc[i] = (m2-1)/m2 * D.iloc[i-1] + 1/m2 * K.iloc[i]
    return K, D, 3*K - 2*D


def calc_money_flow(df):
    hl       = df["High"] - df["Low"] + 1e-9
    buy_amt  = (df["Close"] - df["Low"])   / hl * df["Close"] * df["Volume"]
    sell_amt = (df["High"]  - df["Close"]) / hl * df["Close"] * df["Volume"]
    return buy_amt - sell_amt


def calc_vol_ratio(df, window=10):
    return df["Volume"] / df["Volume"].rolling(window).mean()


# ============================================================
# 通用信号检测
# ============================================================
def check_signals(df, name, market):
    if len(df) < 25:
        return False, {}

    df = df.copy().reset_index(drop=True)
    df["MA5"]      = df["Close"].rolling(5).mean()
    df["VolRatio"] = calc_vol_ratio(df)
    df["NetFlow"]  = calc_money_flow(df)
    df["K"], df["D"], _ = calc_kdj(df)

    today = df.iloc[-1]
    prev  = df.iloc[-2]

    close     = today["Close"]
    ma5       = today["MA5"]
    vol_ratio = today["VolRatio"]
    net_flow  = today["NetFlow"]
    k_t, d_t  = today["K"], today["D"]
    k_p, d_p  = prev["K"],  prev["D"]

    cond_vol      = vol_ratio > 1
    cond_flow     = net_flow > 0
    cond_kd_cross = (k_p <= d_p) and (k_t > d_t)
    cond_ma5      = close > ma5
    passed        = cond_vol and cond_flow and cond_kd_cross and cond_ma5

    detail = {
        "市场":       market,
        "名称/代码":  name,
        "最新价":     round(close, 2),
        "MA5":       round(ma5, 2),
        "量比":      round(vol_ratio, 2),
        "净流入(万)": round(net_flow / 1e4, 1),
        "K值":       round(k_t, 2),
        "D值":       round(d_t, 2),
        "量比>1":    "✅" if cond_vol      else "❌",
        "资金流入":   "✅" if cond_flow     else "❌",
        "KD金叉":    "✅" if cond_kd_cross else "❌",
        "站上MA5":   "✅" if cond_ma5      else "❌",
    }
    return passed, detail


# ============================================================
# A股：获取全市场列表（自动过滤垃圾股）
# ============================================================
def get_all_a_stocks():
    """
    从东方财富获取全A股列表，过滤：
    - ST / *ST / 退市股
    - 北交所（8开头）、协议转让（4开头）
    - 总市值低于10亿的微盘股
    - 价格低于1元的仙股
    """
    print("📋 正在获取全市场股票列表...")
    df = ak.stock_zh_a_spot_em()

    before = len(df)

    df = df[~df["名称"].str.contains("ST|退", na=False)]
    df = df[~df["代码"].str.startswith(("8", "4"))]
    df = df[df["最新价"] >= 1]
    df = df[df["总市值"] >= 1e9]          # 市值 >= 10亿

    after = len(df)
    print(f"✅ 过滤后：{before} → {after} 只（剔除 {before - after} 只）\n")

    # 返回 {代码: 名称} 字典
    return dict(zip(df["代码"], df["名称"]))


# ============================================================
# A股：获取单只历史数据
# ============================================================
def fetch_a_stock(code, days=60):
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start, end_date=end,
        adjust="qfq"
    )
    df = df.rename(columns={
        "开盘": "Open", "收盘": "Close",
        "最高": "High", "最低": "Low",
        "成交量": "Volume",
    })
    return df[["Open", "High", "Low", "Close", "Volume"]].tail(days)


# ============================================================
# A股全市场扫描
# ============================================================
def pick_a_stocks():
    selected, detail_log = [], []

    stock_map = get_all_a_stocks()
    total     = len(stock_map)
    codes     = list(stock_map.keys())

    print(f"⏳ 开始全市场扫描，共 {total} 只...\n")
    start_time = datetime.now()

    for i, code in enumerate(codes, 1):
        name  = stock_map[code]
        label = f"{name}({code})"
        try:
            df = fetch_a_stock(code)
            passed, detail = check_signals(df, label, "A股")

            if detail:
                detail_log.append(detail)
            if passed:
                selected.append(detail)
                print(f"  ✅ [{i:>4}/{total}] {label} 四条件全中！")

        except Exception:
            pass    # 静默跳过，避免单只异常中断整体

        # 每200只打印一次进度 + 预估剩余时间
        if i % 200 == 0:
            elapsed = (datetime.now() - start_time).seconds
            eta     = int(elapsed / i * (total - i) / 60)
            print(f"  ➖ 已扫描 {i}/{total}，耗时 {elapsed//60}分{elapsed%60}秒，"
                  f"预计还需 {eta} 分钟...")

    elapsed_total = (datetime.now() - start_time).seconds
    print(f"\n✅ 全市场扫描完毕！共 {total} 只，"
          f"耗时 {elapsed_total//60} 分 {elapsed_total%60} 秒，"
          f"入选 {len(selected)} 只\n")

    return selected, detail_log


# ============================================================
# 美股数据获取
# ============================================================
def fetch_us_stock(ticker):
    df = yf.Ticker(ticker).history(period="90d")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def pick_us_stocks():
    selected, detail_log = [], []
    total = len(US_STOCK_POOL)

    print(f"⏳ 正在扫描美股（{total} 只）...")
    for ticker in US_STOCK_POOL:
        try:
            df = fetch_us_stock(ticker)
            passed, detail = check_signals(df, ticker, "美股")
            if detail:
                detail_log.append(detail)
            if passed:
                selected.append(detail)
                print(f"  ✅ {ticker} 四条件全中！")
            else:
                print(f"  ➖ {ticker}")
        except Exception as e:
            print(f"  ⚠️  {ticker} 获取失败: {e}")

    return selected, detail_log


# ============================================================
# 主程序
# ============================================================
def main():
    date_str   = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.now()

    print(f"\n{'='*62}")
    print(f"  📅  {date_str}  每日选股启动")
    print(f"{'='*62}\n")

    a_selected,  a_detail  = pick_a_stocks()
    us_selected, us_detail = pick_us_stocks()

    all_selected = a_selected  + us_selected
    all_detail   = a_detail    + us_detail

    # ── 打印报告 ──────────────────────────────────────────
    print(f"\n{'='*62}")
    print(f"  📊  {date_str}  选股结果汇总")
    print(f"{'='*62}")

    if not all_selected:
        print("  ❌ 今日无符合全部条件的股票\n")
    else:
        cnt_a  = len(a_selected)
        cnt_us = len(us_selected)
        print(f"\n  🎯 共 {len(all_selected)} 只入选 "
              f"（A股 {cnt_a} / 美股 {cnt_us}）\n")
        print(pd.DataFrame(all_selected)[[
            "市场", "名称/代码", "最新价", "MA5",
            "量比", "净流入(万)", "K值", "D值"
        ]].to_string(index=False))

    elapsed = (datetime.now() - start_time).seconds
    print(f"\n⏱  总耗时：{elapsed//60} 分 {elapsed%60} 秒")
    print(f"{'─'*62}\n")

    # ── 保存 CSV ─────────────────────────────────────────
    pd.DataFrame(all_selected).to_csv(
        f"picks_{date_str}.csv",  index=False, encoding="utf-8-sig")
    pd.DataFrame(all_detail).to_csv(
        f"detail_{date_str}.csv", index=False, encoding="utf-8-sig")
    print(f"✅ 已保存：picks_{date_str}.csv / detail_{date_str}.csv")

    # ── 微信推送 ─────────────────────────────────────────
    push_wechat(date_str, all_selected, all_detail)


if __name__ == "__main__":
    main()
