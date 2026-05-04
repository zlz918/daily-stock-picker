import os
import tushare as ts
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# 假设你已有 notifier.py 用于微信推送
try:
    from notifier import push_wechat
except ImportError:
    def push_wechat(*args): print("微信推送组件未找到，仅执行本地打印。")

# ============================================================
# 配置与初始化
# ============================================================
US_STOCK_POOL = ["AAPL", "MSFT", "NVDA", "TSLA", "META", "GOOGL", "AMZN", "AMD", "BABA", "PDD"]

def get_pro():
    token = os.getenv('TUSHARE_TOKEN')
    if not token:
        raise ValueError("请在 GitHub Secrets 中配置 TUSHARE_TOKEN")
    return ts.pro_api(token)

# ============================================================
# 核心指标计算（向量化版本，速度极快）
# ============================================================
def calc_kdj(df, n=9, m1=3, m2=3):
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    K = rsv.ewm(com=m1-1, adjust=False).mean()
    D = K.ewm(com=m2-1, adjust=False).mean()
    return K, D

def calc_money_flow(df):
    # Tushare 直接提供净流入数据，无需手动计算，但在简版接口中可用此逻辑适配
    hl = df["high"] - df["low"] + 1e-9
    buy_amt = (df["close"] - df["low"]) / hl * df["close"] * df["vol"]
    sell_amt = (df["high"] - df["close"]) / hl * df["close"] * df["vol"]
    return buy_amt - sell_amt

# ============================================================
# A股扫描：Tushare 批量模式
# ============================================================
def pick_a_stocks(pro):
    print("📋 正在通过 Tushare 获取 A 股全市场数据...")
    today_str = datetime.now().strftime('%Y%m%d')
    
    # 1. 一次性获取全市场行情和技术指标
    # 注意：Tushare 的 daily_basic 已经包含了量比、MA5、市值等
    df_daily = pro.daily(trade_date=today_str)
    df_basic = pro.daily_basic(trade_date=today_str, fields='ts_code,volume_ratio,total_mv,close')
    
    if df_daily.empty or df_basic.empty:
        print("⚠️ 今日数据尚未更新，尝试获取前一交易日...")
        # 实际生产环境建议配合 pro.trade_cal 接口获取准确日期
        return [], []

    # 合并基础数据
    df_all = pd.merge(df_daily, df_basic, on='ts_code')

    # 2. 初步筛选：量比 > 1 且 市值 > 10亿 且 股价 > 1
    mask = (df_all['volume_ratio'] > 1) & (df_all['total_mv'] > 100000) & (df_all['close_x'] > 1)
    candidates = df_all[mask].copy()
    print(f"✅ 初筛完成，共有 {len(candidates)} 只进入指标扫描...")

    selected_results = []
    # 3. 细筛：计算 KD 金叉 和 资金流 (为节省积分，此处仅对初筛后的股票进行历史回溯)
    for index, row in candidates.iterrows():
        code = row['ts_code']
        try:
            # 获取最近 30 天历史数据计算 KD 和 MA5
            hist = pro.daily(ts_code=code, start_date=(datetime.now()-timedelta(days=40)).strftime('%Y%m%d'), end_date=today_str)
            hist = hist.sort_values('trade_date')
            
            # 计算指标
            hist['MA5'] = hist['close'].rolling(5).mean()
            hist['K'], hist['D'] = calc_kdj(hist)
            hist['NetFlow'] = calc_money_flow(hist)
            
            curr = hist.iloc[-1]
            prev = hist.iloc[-2]
            
            # 条件判断
            cond_kd = (prev['K'] <= prev['D']) and (curr['K'] > curr['D'])
            cond_ma5 = curr['close'] > curr['MA5']
            cond_flow = curr['NetFlow'] > 0
            
            if cond_kd and cond_ma5 and cond_flow:
                selected_results.append({
                    "市场": "A股",
                    "名称/代码": code,
                    "最新价": round(curr['close'], 2),
                    "MA5": round(curr['MA5'], 2),
                    "量比": round(row['volume_ratio'], 2),
                    "净流入(万)": round(curr['NetFlow']/1e4, 1),
                    "K值": round(curr['K'], 2),
                    "D值": round(curr['D'], 2)
                })
        except:
            continue

    return selected_results

# ============================================================
# 美股扫描：yfinance 模式
# ============================================================
def pick_us_stocks():
    print(f"⏳ 正在扫描美股（{len(US_STOCK_POOL)} 只）...")
    selected = []
    for ticker in US_STOCK_POOL:
        try:
            df = yf.Ticker(ticker).history(period="30d")
            if len(df) < 20: continue
            
            # 适配大小写列名
            df.columns = [c.lower() for c in df.columns]
            df['MA5'] = df['close'].rolling(5).mean()
            df['K'], df['D'] = calc_kdj(df)
            df['vol_ratio'] = df['volume'] / df['volume'].rolling(10).mean()
            df['NetFlow'] = calc_money_flow(df)
            
            curr, prev = df.iloc[-1], df.iloc[-2]
            
            if (curr['vol_ratio'] > 1 and curr['NetFlow'] > 0 and 
                prev['K'] <= prev['D'] and curr['K'] > curr['D'] and 
                curr['close'] > curr['MA5']):
                selected.append({
                    "市场": "美股",
                    "名称/代码": ticker,
                    "最新价": round(curr['close'], 2),
                    "MA5": round(curr['MA5'], 2),
                    "量比": round(curr['vol_ratio'], 2),
                    "净流入(万)": round(curr['NetFlow']/1e4, 1),
                    "K值": round(curr['K'], 2),
                    "D值": round(curr['D'], 2)
                })
        except Exception as e:
            print(f"美股 {ticker} 错误: {e}")
    return selected

# ============================================================
# 主程序
# ============================================================
def main():
    pro = get_pro()
    a_res = pick_a_stocks(pro)
    us_res = pick_us_stocks()
    
    all_res = a_res + us_res
    df_res = pd.DataFrame(all_res)
    
    print("\n" + "="*50)
    print(f"选股完成！入选总数: {len(all_res)}")
    print("="*50)
    if not df_res.empty:
        print(df_res.to_string(index=False))
        df_res.to_csv(f"picks_{datetime.now().strftime('%Y%m%d')}.csv", index=False, encoding="utf-8-sig")
        push_wechat(datetime.now().strftime('%Y-%m-%d'), all_res, [])
    else:
        print("今日无符合条件股票。")

if __name__ == "__main__":
    main()
