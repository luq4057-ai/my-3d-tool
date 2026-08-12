import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from math import comb
from datetime import datetime
import re
import sqlite3

MULTIPLIERS = {5: 15.0, 6: 7.5, 7: 4.3}

DB_FILE = "lottery_data.db"
TABLE_NAME = "history3d"

st.set_page_config(page_title="福彩3D 智能分析", layout="wide")


def determine_pattern(n1, n2, n3):
    if n1 == n2 == n3:
        return "豹子"
    if n1 == n2 or n2 == n3 or n1 == n3:
        return "组三"
    return "组六"


@st.cache_resource(ttl=1800)
def load_records():
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(
            f"SELECT period, num1, num2, num3, pattern, draw_date "
            f"FROM {TABLE_NAME} ORDER BY period ASC",
            conn,
        )
        conn.close()
        if not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


def extract_features(df):
    df = df.copy()

    df["sum_val"] = df["num1"] + df["num2"] + df["num3"]
    df["sum_tail"] = df["sum_val"] % 10
    df["sum_tail_size"] = df["sum_tail"].apply(lambda x: "大" if x >= 5 else "小")

    df["road1"] = df["num1"] % 3
    df["road2"] = df["num2"] % 3
    df["road3"] = df["num3"] % 3
    df["sum_road"] = df["sum_val"] % 3

    df["span"] = df[["num1", "num2", "num3"]].max(axis=1) - df[["num1", "num2", "num3"]].min(axis=1)

    def _classify(d, prev_set):
        if d in prev_set:
            return "传"
        for p in prev_set:
            if abs(d - p) == 1 or abs(d - p) == 9:
                return "邻"
        return "孤"

    lgc_list = []
    prev_set = None
    for _, row in df.iterrows():
        if prev_set is None:
            lgc_list.append("—")
        else:
            cur = [row["num1"], row["num2"], row["num3"]]
            tags = [_classify(d, prev_set) for d in cur]
            c, l, g = tags.count("传"), tags.count("邻"), tags.count("孤")
            lgc_list.append(f"{c}传{l}邻{g}孤")
        prev_set = {row["num1"], row["num2"], row["num3"]}
    df["lgc"] = lgc_list

    return df


def pattern_recognition_engine(df, window=20, min_streak=4):
    df = df.copy()
    if len(df) < window:
        window = len(df)
    recent = df.tail(window).reset_index(drop=True)
    findings = []

    def _find_streak(series, name, label_fn=None):
        if len(series) == 0:
            return
        val = series.iloc[-1]
        streak = 0
        for v in series.iloc[::-1]:
            if v == val:
                streak += 1
            else:
                break
        if streak >= min_streak:
            display_val = label_fn(val) if label_fn else str(val)
            opposite = None
            if isinstance(val, str) and val in ("大", "小"):
                opposite = "小" if val == "大" else "大"
            elif isinstance(val, str) and val in ("奇", "偶"):
                opposite = "偶" if val == "奇" else "奇"
            elif isinstance(val, int) and name.endswith("012路"):
                opposite = [r for r in [0, 1, 2] if r != val]
            suggestion = f"建议下期关注：{opposite}" if opposite else ""
            findings.append(f"规律：{name}连续为【{display_val}】，已连出 {streak} 次。{suggestion}")

    if "sum_tail_size" in recent.columns:
        _find_streak(recent["sum_tail_size"], "和尾大小")

    if "sum_road" in recent.columns:
        _find_streak(recent["sum_road"], "和值012路", lambda v: f"{v}路")

    if "road1" in recent.columns:
        _find_streak(recent["road1"], "百位012路", lambda v: f"{v}路")
    if "road2" in recent.columns:
        _find_streak(recent["road2"], "十位012路", lambda v: f"{v}路")
    if "road3" in recent.columns:
        _find_streak(recent["road3"], "个位012路", lambda v: f"{v}路")

    if "pattern" in recent.columns:
        _find_streak(recent["pattern"], "形态")

    recent["sum_parity"] = recent["sum_val"].apply(lambda x: "奇" if x % 2 else "偶")
    _find_streak(recent["sum_parity"], "和值奇偶")

    recent["span_size"] = recent["span"].apply(lambda x: "大" if x >= 5 else "小")
    _find_streak(recent["span_size"], "跨度大小")

    recent["sum_range"] = recent["sum_val"].apply(
        lambda x: "0-9" if x <= 9 else "10-18" if x <= 18 else "19-27"
    )
    _find_streak(recent["sum_range"], "和值区间")

    def _find_cross_period_rules(recent, min_hits=3):
        n = len(recent)
        if n < 4:
            return

        rules = [
            {
                "name": "上期(十位+个位)和尾 → 本期百位",
                "calc_prev": lambda r: (r["num2"] + r["num3"]) % 10,
                "calc_curr": lambda r: r["num1"],
            },
            {
                "name": "上期(百位+个位)和尾 → 本期十位",
                "calc_prev": lambda r: (r["num1"] + r["num3"]) % 10,
                "calc_curr": lambda r: r["num2"],
            },
            {
                "name": "上期(百位+十位)和尾 → 本期个位",
                "calc_prev": lambda r: (r["num1"] + r["num2"]) % 10,
                "calc_curr": lambda r: r["num3"],
            },
            {
                "name": "上期和尾 → 本期百位",
                "calc_prev": lambda r: r["sum_tail"],
                "calc_curr": lambda r: r["num1"],
            },
            {
                "name": "上期个位 → 本期百位",
                "calc_prev": lambda r: r["num3"],
                "calc_curr": lambda r: r["num1"],
            },
            {
                "name": "上期跨度 → 本期和尾",
                "calc_prev": lambda r: r["span"],
                "calc_curr": lambda r: r["sum_tail"],
            },
            {
                "name": "上期百位012路 → 本期个位012路",
                "calc_prev": lambda r: r["road1"],
                "calc_curr": lambda r: r["road3"],
            },
            {
                "name": "上期和值012路 → 本期和值012路",
                "calc_prev": lambda r: r["sum_road"],
                "calc_curr": lambda r: r["sum_road"],
            },
        ]

        for rule in rules:
            hits = 0
            checked = 0
            for i in range(1, n):
                try:
                    prev_val = rule["calc_prev"](recent.iloc[i - 1])
                    curr_val = rule["calc_curr"](recent.iloc[i])
                    checked += 1
                    if prev_val == curr_val:
                        hits += 1
                except (KeyError, TypeError):
                    continue

            if checked >= 3 and hits / checked >= 0.5:
                pct = hits / checked * 100
                try:
                    last_prev = rule["calc_prev"](recent.iloc[-1])
                    findings.append(
                        f"关联：{rule['name']}，近{checked}期命中{hits}次({pct:.0f}%)，"
                        f"上期前置值={last_prev}，建议本期关注：{last_prev}"
                    )
                except (KeyError, TypeError):
                    pass

    _find_cross_period_rules(recent, min_hits=3)

    return findings


def calc_missing(df):
    result = {}
    for digit in range(10):
        count = 0
        for _, row in df.iloc[::-1].iterrows():
            if digit in (row["num1"], row["num2"], row["num3"]):
                break
            count += 1
        result[digit] = count
    return result


def calc_hotness(df, recent_n=30):
    recent = df.tail(recent_n)
    result = {}
    for digit in range(10):
        result[digit] = sum(
            1
            for _, row in recent.iterrows()
            if digit in (row["num1"], row["num2"], row["num3"])
        )
    return result


def calc_zu3_missing(df):
    count = 0
    for _, row in df.iloc[::-1].iterrows():
        if row["pattern"] == "组三":
            break
        count += 1
    return count


def calc_zu3_avg_interval(df):
    zu3_indices = df.index[df["pattern"] == "组三"].tolist()
    if len(zu3_indices) < 2:
        return None
    intervals = [zu3_indices[i] - zu3_indices[i - 1] for i in range(1, len(zu3_indices))]
    return sum(intervals) / len(intervals)


def simulate_group(df, digits):
    digits = set(digits)
    n = len(digits)
    if n not in MULTIPLIERS:
        return None

    multiplier = MULTIPLIERS[n]
    zu6_bets = comb(n, 3)
    zu3_bets = n * (n - 1)
    total_bets = zu6_bets + zu3_bets
    cost_per_period = total_bets * 2

    wins = 0
    zu6_wins = 0
    zu3_wins = 0
    cumulative = []
    running = 0

    for _, row in df.iterrows():
        running -= cost_per_period
        if row["pattern"] != "豹子":
            winning_set = {row["num1"], row["num2"], row["num3"]}
            if winning_set.issubset(digits):
                wins += 1
                running += cost_per_period * multiplier
                if row["pattern"] == "组六":
                    zu6_wins += 1
                else:
                    zu3_wins += 1
        cumulative.append(running)

    total_periods = len(df)
    total_investment = cost_per_period * total_periods
    total_return = wins * cost_per_period * multiplier
    net_profit = total_return - total_investment

    return {
        "mode": f"{n}码组选",
        "digits": sorted(digits),
        "n": n,
        "multiplier": multiplier,
        "total_bets": total_bets,
        "zu6_bets": zu6_bets,
        "zu3_bets": zu3_bets,
        "cost_per_period": cost_per_period,
        "total_periods": total_periods,
        "wins": wins,
        "zu6_wins": zu6_wins,
        "zu3_wins": zu3_wins,
        "win_rate": wins / total_periods if total_periods > 0 else 0,
        "total_investment": total_investment,
        "total_return": total_return,
        "net_profit": net_profit,
        "roi": (net_profit / total_investment * 100) if total_investment > 0 else 0,
        "cumulative": cumulative,
    }


df = load_records()

if df.empty:
    st.error("❌ 无法加载数据")
    st.warning("""
    **数据库中暂无数据。**
    
    数据由 GitHub Actions 每天自动更新。如果刚部署，请手动触发一次更新：
    
    1. 进入仓库 → **Actions** → **Daily 3D Lottery Data Update**
    2. 点击 **Run workflow** 按钮
    3. 等待运行完成后刷新本页面
    """)
    st.stop()

latest_date = df["draw_date"].max()
st.caption(f"📅 数据更新至: {latest_date}  |  共 {len(df)} 期  |  由 GitHub Actions 自动更新")

zu3_missing = calc_zu3_missing(df)
zu3_avg = calc_zu3_avg_interval(df)

if zu3_missing is not None and zu3_avg is not None and zu3_missing > zu3_avg:
    st.markdown(
        f'<div style="background-color:#ff4444;color:white;padding:16px 24px;'
        f'border-radius:10px;font-size:22px;font-weight:bold;text-align:center;'
        f'animation:pulse 1.5s infinite">'
        f"⚠️ 组三警报：当前组三已遗漏 {zu3_missing} 期，"
        f"超过平均间隔 {zu3_avg:.1f} 期，请关注！"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<style>@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.6}}</style>",
        unsafe_allow_html=True,
    )

st.title("🎲 福彩3D 智能分析平台")

tab1, tab2, tab3 = st.tabs(["📊 数据总览", "📈 走势统计", "🎯 策略回测"])

df_feat = extract_features(df)

with tab1:
    st.subheader("最近 10 期开奖数据")
    recent = df_feat.tail(10).iloc[::-1].reset_index(drop=True)
    display_df = recent.copy()
    display_df["中奖号码"] = display_df.apply(
        lambda r: f"{r['num1']} {r['num2']} {r['num3']}", axis=1
    )
    display_df["形态"] = display_df["pattern"].map(
        {"组六": "🔵 组六", "组三": "🟡 组三", "豹子": "🔴 豹子"}
    )
    display_df["和值/和尾"] = display_df.apply(
        lambda r: f"{r['sum_val']}/{r['sum_tail']}", axis=1
    )
    display_df["和尾大小"] = display_df["sum_tail_size"]
    display_df["012路"] = display_df.apply(
        lambda r: f"{r['road1']}{r['road2']}{r['road3']}(和{r['sum_road']})", axis=1
    )
    display_df["跨度"] = display_df["span"]
    display_df["邻孤传"] = display_df["lgc"]
    show_cols = ["period", "draw_date", "中奖号码", "形态", "和值/和尾", "和尾大小", "012路", "跨度", "邻孤传"]
    show_cols_renamed = ["期号", "开奖日期", "中奖号码", "形态", "和值/和尾", "和尾大小", "012路", "跨度", "邻孤传"]
    show_df = display_df[show_cols].rename(
        columns=dict(zip(show_cols, show_cols_renamed))
    )

    st.dataframe(
        show_df,
        use_container_width=True,
        hide_index=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    total = len(df)
    zu3_count = len(df[df["pattern"] == "组三"])
    zu6_count = len(df[df["pattern"] == "组六"])
    bao_count = len(df[df["pattern"] == "豹子"])
    col1.metric("总期数", f"{total} 期")
    col2.metric("组六", f"{zu6_count} 期 ({zu6_count / total:.1%})")
    col3.metric("组三", f"{zu3_count} 期 ({zu3_count / total:.1%})")
    col4.metric("豹子", f"{bao_count} 期 ({bao_count / total:.1%})")

    st.divider()
    st.subheader("🧠 智能规律扫描")
    scan_window = st.slider("扫描期数", min_value=10, max_value=50, value=20, step=5, key="scan_window")
    scan_streak = st.slider("最短连出次数", min_value=2, max_value=6, value=4, step=1, key="scan_streak")

    findings = pattern_recognition_engine(df_feat, window=scan_window, min_streak=scan_streak)

    if findings:
        for f in findings:
            if f.startswith("规律："):
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);'
                    f'border-left:4px solid #ffd93d;padding:12px 16px;border-radius:8px;'
                    f'margin:6px 0;font-size:15px;color:#e0e0e0">'
                    f'📊 {f}</div>',
                    unsafe_allow_html=True,
                )
            elif f.startswith("关联："):
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);'
                    f'border-left:4px solid #4dabf7;padding:12px 16px;border-radius:8px;'
                    f'margin:6px 0;font-size:15px;color:#e0e0e0">'
                    f'🔗 {f}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info(f"近 {scan_window} 期未检测到连续 {scan_streak} 次以上的规律，数据较为随机。")

with tab2:
    freq_col1, freq_col2 = st.columns(2)

    with freq_col1:
        st.subheader("近 100 期数字出现频率")
        recent100 = df.tail(100)
        freq = {}
        for digit in range(10):
            freq[digit] = sum(
                1
                for _, row in recent100.iterrows()
                if digit in (row["num1"], row["num2"], row["num3"])
            )
        fig_freq = go.Figure(
            go.Bar(
                x=[str(d) for d in range(10)],
                y=[freq[d] for d in range(10)],
                marker_color=[
                    "#ff6b6b" if freq[d] >= max(freq.values()) * 0.7
                    else "#ffd93d" if freq[d] >= max(freq.values()) * 0.4
                    else "#6bcb77"
                    for d in range(10)
                ],
                text=[freq[d] for d in range(10)],
                textposition="outside",
            )
        )
        fig_freq.update_layout(
            xaxis_title="数字",
            yaxis_title="出现期数",
            height=400,
            margin=dict(t=30, b=30),
        )
        st.plotly_chart(fig_freq, use_container_width=True)

    with freq_col2:
        st.subheader("遗漏值 & 热度值")
        missing = calc_missing(df)
        hotness = calc_hotness(df, 30)

        bar_df = pd.DataFrame(
            {
                "数字": list(range(10)),
                "遗漏值": [missing[d] for d in range(10)],
                "热度值(近30期)": [hotness[d] for d in range(10)],
            }
        )
        fig_mh = go.Figure()
        fig_mh.add_trace(
            go.Bar(
                x=bar_df["数字"].astype(str),
                y=bar_df["遗漏值"],
                name="遗漏值(期)",
                marker_color="#ff6b6b",
                yaxis="y",
            )
        )
        fig_mh.add_trace(
            go.Bar(
                x=bar_df["数字"].astype(str),
                y=bar_df["热度值(近30期)"],
                name="热度值(次)",
                marker_color="#4dabf7",
                yaxis="y2",
            )
        )
        fig_mh.update_layout(
            yaxis=dict(title="遗漏值(期)", side="left"),
            yaxis2=dict(title="热度值(次)", overlaying="y", side="right"),
            barmode="group",
            height=400,
            margin=dict(t=30, b=30),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig_mh, use_container_width=True)

    st.subheader("组三/组六走势（近 100 期）")
    recent100_reset = df.tail(100).reset_index(drop=True)
    pattern_map = {"组六": 0, "组三": 1, "豹子": 2}
    pattern_series = recent100_reset["pattern"].map(pattern_map)

    color_map = {"组六": "#4dabf7", "组三": "#ffd93d", "豹子": "#ff6b6b"}
    colors = recent100_reset["pattern"].map(color_map)

    fig_pattern = go.Figure()
    fig_pattern.add_trace(
        go.Bar(
            x=recent100_reset["period"],
            y=pattern_series,
            marker_color=colors,
            showlegend=False,
        )
    )
    fig_pattern.update_layout(
        yaxis=dict(
            tickvals=[0, 1, 2],
            ticktext=["组六", "组三", "豹子"],
        ),
        xaxis_title="期号",
        height=300,
        margin=dict(t=30, b=30),
    )
    for name, color in color_map.items():
        fig_pattern.add_trace(
            go.Bar(x=[None], y=[None], marker_color=color, name=name)
        )
    st.plotly_chart(fig_pattern, use_container_width=True)

with tab3:
    st.subheader("策略配置")
    st.markdown(
        "输入 3 组 **7码** 数字（0-9，不重复），系统自动生成嵌套的 6码和5码组合。"
    )

    groups = []
    default_sevens = ["0135789", "0245689", "1356789"]
    for i in range(3):
        with st.container():
            cols = st.columns([2, 2, 2])
            with cols[0]:
                raw = st.text_input(
                    f"第 {i + 1} 组 · 7码",
                    value=default_sevens[i],
                    key=f"seven_{i}",
                    max_chars=7,
                )
            seven_digits = [int(c) for c in raw if c.isdigit()]
            seven_digits = list(dict.fromkeys(seven_digits))[:7]

            six_digits = seven_digits[:6] if len(seven_digits) >= 6 else []
            five_digits = seven_digits[:5] if len(seven_digits) >= 5 else []

            with cols[1]:
                st.markdown(
                    f'<div style="padding:8px;background:#1a1a2e;border-radius:6px;'
                    f'font-size:14px;color:#4dabf7">'
                    f"6码: {''.join(map(str, six_digits)) if six_digits else '—'}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with cols[2]:
                st.markdown(
                    f'<div style="padding:8px;background:#1a1a2e;border-radius:6px;'
                    f'font-size:14px;color:#6bcb77">'
                    f"5码: {''.join(map(str, five_digits)) if five_digits else '—'}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            group = {}
            if len(seven_digits) == 7:
                group[7] = seven_digits
            if len(six_digits) == 6:
                group[6] = six_digits
            if len(five_digits) == 5:
                group[5] = five_digits
            groups.append(group)

    analyze = st.button("🚀 开始分析", type="primary", use_container_width=True)

    if analyze:
        all_results = []
        for i, group in enumerate(groups):
            for n, digits in sorted(group.items(), reverse=True):
                result = simulate_group(df, digits)
                if result:
                    result["group_idx"] = i + 1
                    all_results.append(result)

        if not all_results:
            st.warning("请确保每组输入 7 个不重复的数字（0-9）")
        else:
            st.subheader("回测结果汇总")

            summary_data = []
            for r in all_results:
                summary_data.append(
                    {
                        "组别": f"第{r['group_idx']}组",
                        "模式": r["mode"],
                        "数字": "".join(map(str, r["digits"])),
                        "每期投入": f"{r['cost_per_period']}元",
                        "中奖次数": r["wins"],
                        "组六/组三": f"{r['zu6_wins']}/{r['zu3_wins']}",
                        "中奖率": f"{r['win_rate']:.2%}",
                        "总投入": f"{r['total_investment']:,}元",
                        "总回报": f"{r['total_return']:,.1f}元",
                        "净盈亏": f"{r['net_profit']:+,.1f}元",
                        "回报率": f"{r['roi']:+.2f}%",
                    }
                )
            st.dataframe(
                pd.DataFrame(summary_data),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("收益曲线")
            fig_profit = go.Figure()
            colors_line = ["#4dabf7", "#ffd93d", "#ff6b6b"]
            color_idx = 0

            for r in all_results:
                label = f"第{r['group_idx']}组·{r['mode']}({''.join(map(str, r['digits']))})"
                fig_profit.add_trace(
                    go.Scatter(
                        x=df["period"].values,
                        y=r["cumulative"],
                        mode="lines",
                        name=label,
                        line=dict(width=2, color=colors_line[color_idx % 3]),
                    )
                )
                color_idx += 1

            fig_profit.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            fig_profit.update_layout(
                xaxis_title="期号",
                yaxis_title="累计盈亏(元)",
                height=450,
                margin=dict(t=30, b=30),
                legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
            )
            st.plotly_chart(fig_profit, use_container_width=True)

            best = max(all_results, key=lambda r: r["roi"])
            st.success(
                f"🏆 最优策略：第{best['group_idx']}组 {best['mode']} "
                f"({''.join(map(str, best['digits']))})  |  "
                f"中奖率 {best['win_rate']:.2%}  |  "
                f"回报率 {best['roi']:+.2f}%  |  "
                f"净盈亏 {best['net_profit']:+,.1f}元"
            )