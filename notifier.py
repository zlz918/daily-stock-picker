import os, json, urllib.parse
from urllib import request as url_request

SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY", "")


def build_message(date_str, selected, detail):
    cnt_a  = sum(1 for r in selected if r.get("市场") == "A股")
    cnt_us = sum(1 for r in selected if r.get("市场") == "美股")

    title = (
        f"📈 {date_str} 每日选股：{len(selected)} 只入选（A股 {cnt_a} / 美股 {cnt_us}）"
        if selected else
        f"📭 {date_str} 每日选股：今日无入选股票"
    )

    if selected:
        rows = [
            "| 市场 | 股票 | 最新价 | MA5 | 量比 | 净流入(万) | K | D |",
            "| :--: | :--: | -----: | --: | ---: | ---------: |--:|--:|",
        ]
        for r in selected:
            rows.append(
                f"| {r['市场']} | {r['名称/代码']} "
                f"| {r['最新价']} | {r['MA5']} "
                f"| {r['量比']} | {r['净流入(万)']} "
                f"| {r['K值']} | {r['D值']} |"
            )
        table = "\n".join(rows)
    else:
        table = "> 今日无符合全部条件的股票，耐心等待机会 🕐"

    detail_rows = [
        "| 市场 | 股票 | 量比>1 | 资金流入 | KD金叉 | 站上MA5 |",
        "| :--: | :--: | :----: | :------: | :----: | :-----: |",
    ]
    for r in detail:
        detail_rows.append(
            f"| {r['市场']} | {r['名称/代码']} "
            f"| {r['量比>1']} | {r['资金流入']} "
            f"| {r['KD金叉']} | {r['站上MA5']} |"
        )
    detail_table = "\n".join(detail_rows)

    content = f"""
## 🎯 入选股票

{table}

---

## 📋 全部候选信号明细

{detail_table}

---
> 选股条件：量比 > 1 ｜ 资金净流入 ｜ KD 金叉 ｜ 股价站上 MA5
> 本报告由 GitHub Actions 自动生成，仅供参考，不构成投资建议。
"""
    return {"title": title, "content": content.strip()}


def push_wechat(date_str, selected, detail):
    if not SERVERCHAN_KEY:
        print("  [微信] ⚠️  未配置 SERVERCHAN_KEY，跳过推送")
        return

    msg  = build_message(date_str, selected, detail)
    url  = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
    data = urllib.parse.urlencode({
        "title": msg["title"],
        "desp":  msg["content"],
    }).encode("utf-8")

    req = url_request.Request(url, data=data)
    try:
        with url_request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            errno  = result.get("data", {}).get("errno", -1)
            if errno == 0:
                print("  [微信] ✅ 推送成功，请查收微信通知")
            else:
                print(f"  [微信] ❌ 推送失败：{result}")
    except Exception as e:
        print(f"  [微信] ❌ 请求异常：{e}")
