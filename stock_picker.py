import os
import tushare as ts
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================
US_STOCK_POOL = ["AAPL", "MSFT", "NVDA", "TSLA", "META", "GOOGL", "AMZN", "AMD", "BABA", "PDD"]

def get_pro():
    token = os.getenv('TUSHARE_TOKEN')
    if not token:
        raise ValueError("请在 GitHub Secrets 中配置 TUSHARE_TOKEN")
    return ts.pro_api(token)

# ============================================================
# 指标计算
# ============================================================
def calc_kdj(df, n=9, m1=3, m2=3):
    # 统一使用小写列名进行计算
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    K = rsv.ewm(com=m1-1, adjust=False).mean()
    D = K.ewm(com=m2-1, adjust=False).mean()
    return K, D

def calc_money_flow(df):
    # 统一列名引用：high, low, close, vol
    hl = df["high"] - df["low"] + 1e-9
    buy_amt = (df["close"] - df["low"]) / hl * df["close"] * df["vol"]
    sell_amt = (df["high"] - df["close"]) / hl * df["close"] * df["vol"]
    return buy_amt - sell_amt

# ============================================================
# A股扫描
# ============================================================
def pick_a_stocks(pro):
    print("📋 正在获取 A 股全市场数据...")
    
    # 自动寻找最近的交易日逻辑
    today = datetime.now()
    target_date = today.strftime('%Y%m%d')
    
    df_daily = pro.daily(trade_date=target_date)
    # 如果当天没数据（如周末），往前推 3 天试探
    attempt = 1
    while df_daily.empty and attempt <= 3:
        target_date = (today - timedelta(days=attempt)).strftime('%Y%m%d')
        df_daily = pro.daily(trade_date=target_date)
        attempt += 1

    if df_daily.empty:
        print("⚠️ 无法获取近期 A 股行情。")
        return []

    print(f"📊 使用交易日数据: {target_date}")
    df_basic = pro.daily_basic(trade_date=target_date, fields='ts_code,volume_ratio,total_mv,close')
    df_all = pd.merge(df_daily, df_basic, on='ts_code')

    # 初步筛选
    mask = (df_all['volume_ratio'] > 1) & (df_all['total_mv'] > 100000) & (df_all['close_x'] > 1)
    candidates = df_all[mask].copy()
    
    selected_results = []
    # 限制扫描前 150 只，避免 GitHub Actions 超时或积分消耗过快
    for _, row in candidates.head(150).iterrows():
        code = row['ts_code']
        try:
            hist = pro.daily(ts_code=code, start_date=(datetime.now()-timedelta(days=40)).strftime('%Y%m%d'), end_date=target_date)
            if len(hist) < 20: continue
            hist = hist.sort_values('trade_date').rename(columns={'vol': 'vol'}) # 确保列名一致
            
            hist['MA5'] = hist['close'].rolling(5).mean()
            hist['K'], hist['D'] = calc_kdj(hist)
            hist['NetFlow'] = calc_money_flow(hist)
            
            curr, prev = hist.iloc[-1], hist.iloc[-2]
            if (prev['K'] <= prev['D']) and (curr['K'] > curr['D']) and (curr['close'] > curr['MA5']) and (curr['NetFlow'] > 0):
                selected_results.append({
                    "市场": "A股", "名称/代码": code, "最新价": round(curr['close'], 2),
                    "MA5": round(curr['MA5'], 2), "量比": round(row['volume_ratio'], 2),
                    "净流入(万)": round(curr['NetFlow']/1e4, 1), "K值": round(curr['K'], 2), "D值": round(curr['D'], 2)
                })
        except: continue
    return selected_results

# ============================================================
# 美股扫描
# ============================================================
def pick_us_stocks():
    print(f"⏳ 正在扫描美股（{len(US_STOCK_POOL)} 只）...")
    selected = []
    for ticker in US_STOCK_POOL:
        try:
            df = yf.Ticker(ticker).history(period="40d")
            if len(df) < 20: continue
            
            # 关键修复：统一列名为小写，并将 volume 映射为 vol 适配计算函数
            df.columns = [c.lower() for c in df.columns]
            if 'volume' in df.columns:
                df = df.rename(columns={'volume': 'vol'})
            
            df['MA5'] = df['close'].rolling(5).mean()
            df['K'], df['D'] = calc_kdj(df)
            df['vol_ratio'] = df['vol'] / df['vol'].rolling(10).mean()
            df['NetFlow'] = calc_money_flow(df)
            
            curr, prev = df.iloc[-1], df.iloc[-2]
            if (curr['vol_ratio'] > 1 and curr['NetFlow'] > 0 and 
                prev['K'] <= prev['D'] and curr['K'] > curr['D'] and 
                curr['close'] > curr['MA5']):
                selected.append({
                    "市场": "美股", "名称/代码": ticker, "最新价": round(curr['close'], 2),
                    "MA5": round(curr['MA5'], 2), "量比": round(curr['vol_ratio'], 2),
                    "净流入(万)": round(curr['NetFlow']/1e4, 1), "K值": round(curr['K'], 2), "D值": round(curr['D'], 2)
                })
        except Exception as e:
            print(f"美股 {ticker} 错误: {e}")
    return selected

# ============================================================
# 主程序
# ============================================================
def main():
    try:
        pro = get_pro()
        a_res = pick_a_stocks(pro)
        us_res = pick_us_stocks()
        
        # 确保 a_res 和 us_res 都是 list 
        all_res = list(a_res) + list(us_res)
        
        print("\n" + "="*50)
        print(f"选股完成！总入选: {len(all_res)}")
        print("="*50)
        
        if all_res:
            df_res = pd.DataFrame(all_res)
            print(df_res.to_string(index=False))
            # 存为 CSV
            filename = f"picks_{datetime.now().strftime('%Y%m%d')}.csv"
            df_res.to_csv(filename, index=False, encoding="utf-8-sig")
        else:
            print("今日未发现符合信号的个股。")
            
    except Exception as e:
        print(f"程序运行崩溃: {e}")

if __name__ == "__main__":
    main()
