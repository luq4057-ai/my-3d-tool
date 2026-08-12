import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from math import comb
from datetime import datetime
import re
import sqlite3
import itertools

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


def expert_decision_engine(df_feat):
    recent = df_feat.tail(30).reset_index(drop=True)
    last = recent.iloc[-1]
    recommendations = []
    warnings = []

    missing = calc_missing(df_feat)
    hotness = calc_hotness(df_feat, 30)
    total = len(df_feat)
    theoretical_avg = total / 10.0

    hot_digits = []
    for d in range(10):
        if missing[d] > theoretical_avg * 3:
            hot_digits.append((d, missing[d]))

    if hot_digits:
        hot_digits.sort(key=lambda x: -x[1])
        digits_str = "、".join([f"{d}(漏{m}期)" for d, m in hot_digits[:5]])
        recommendations.append(f"🔥 回补号：{digits_str}，遗漏超3倍理论值，回补概率极高")

    zu3_miss = calc_zu3_missing(df_feat)
    zu3_avg = calc_zu3_avg_interval(df_feat)
    if zu3_avg and zu3_miss > zu3_avg * 3:
        recommendations.append(f"⚠️ 组三回补：组三已遗漏{zu3_miss}期，超平均间隔{zu3_avg:.1f}期的3倍，强烈关注组三形态")

    findings = pattern_recognition_engine(df_feat, window=20, min_streak=3)
    for f in findings:
        if f.startswith("规律：") and "建议下期关注" in f:
            recommendations.append(f"📈 惯性反转：{f}")
        elif f.startswith("关联：") and "建议本期关注" in f:
            recommendations.append(f"🔗 关联预测：{f}")

    cross_rules = [
        {"name": "上期(十位+个位)和尾→本期百位", "calc": lambda r: (r["num2"] + r["num3"]) % 10, "target": "百位"},
        {"name": "上期(百位+个位)和尾→本期十位", "calc": lambda r: (r["num1"] + r["num3"]) % 10, "target": "十位"},
        {"name": "上期(百位+十位)和尾→本期个位", "calc": lambda r: (r["num1"] + r["num2"]) % 10, "target": "个位"},
    ]
    for rule in cross_rules:
        try:
            pred_val = rule["calc"](last)
            recommendations.append(f"🎯 关联推演：{rule['name']}={pred_val}，本期{rule['target']}建议包含 {pred_val}")
        except (KeyError, TypeError):
            pass

    cold_digits = [d for d in range(10) if hotness[d] <= 5]
    if cold_digits:
        cold_str = "、".join([str(d) for d in cold_digits])
        warnings.append(f"🧊 极冷号：{cold_str}，近30期仅出现≤5次，下期出现概率低")

    extreme_sums = list(range(0, 4)) + list(range(24, 28))
    if last["sum_val"] <= 6:
        warnings.append(f"❄️ 极端和值：上期和值={last['sum_val']}，和值≤6或≥21出现概率极低，下期大概率回归10-18区间")

    if last["sum_tail_size"] == "大":
        streak = 0
        for v in recent["sum_tail_size"].iloc[::-1]:
            if v == "大":
                streak += 1
            else:
                break
        if streak >= 5:
            warnings.append(f"🚫 和尾大已连出{streak}期，继续出大的概率骤降，建议排除和尾5-9的组合")

    if last["sum_tail_size"] == "小":
        streak = 0
        for v in recent["sum_tail_size"].iloc[::-1]:
            if v == "小":
                streak += 1
            else:
                break
        if streak >= 5:
            warnings.append(f"🚫 和尾小已连出{streak}期，继续出小的概率骤降，建议排除和尾0-4的组合")

    warnings.append(f"🚫 豹子形态：出现概率仅1%，下期排除豹子(三同号)组合")

    if last["span"] >= 8:
        warnings.append(f"🚫 极端跨度：上期跨度={last['span']}，跨度≥8为小概率事件，下期大概率回落至3-7区间")

    return recommendations, warnings


def build_pattern_chain_chart(df_feat, n_periods=5):
    recent = df_feat.tail(n_periods).reset_index(drop=True)
    fig = go.Figure()

    features = [
        {"col": "num1", "name": "百位", "color": "#ff6b6b", "dash": "solid"},
        {"col": "num2", "name": "十位", "color": "#4dabf7", "dash": "solid"},
        {"col": "num3", "name": "个位", "color": "#6bcb77", "dash": "solid"},
        {"col": "sum_tail", "name": "和尾", "color": "#ffd93d", "dash": "dot"},
        {"col": "span", "name": "跨度", "color": "#cc5de8", "dash": "dash"},
    ]

    for feat in features:
        fig.add_trace(
            go.Scatter(
                x=recent["period"],
                y=recent[feat["col"]],
                mode="lines+markers+text",
                name=feat["name"],
                line=dict(color=feat["color"], width=2.5, dash=feat["dash"]),
                marker=dict(size=10, symbol="circle"),
                text=recent[feat["col"]].astype(str),
                textposition="top center",
                textfont=dict(size=12, color=feat["color"]),
            )
        )

    fig.update_layout(
        xaxis_title="期号",
        yaxis_title="数值",
        yaxis=dict(dtick=1, range=[-0.5, 10]),
        height=400,
        margin=dict(t=30, b=30),
        legend=dict(orientation="h", y=1.12, font=dict(size=11)),
        hovermode="x unified",
    )
    return fig


class LotteryPatternEngine:
    def __init__(self, df):
        self.df = extract_features(df) if "sum_val" not in df.columns else df.copy()
        self.total = len(self.df)

    def digit_hotness(self):
        result = {}
        for window in [10, 30, 50]:
            n = min(window, self.total)
            recent = self.df.tail(n)
            freq = {}
            for d in range(10):
                freq[d] = sum(
                    1 for _, r in recent.iterrows()
                    if d in (r["num1"], r["num2"], r["num3"])
                )
            result[window] = freq
        return result

    def streak_scan(self, min_len=3):
        recent = self.df.tail(30).reset_index(drop=True)
        streaks = []

        def _scan(series, name, label_fn=None):
            if len(series) == 0:
                return
            val = series.iloc[-1]
            count = 0
            for v in series.iloc[::-1]:
                if v == val:
                    count += 1
                else:
                    break
            if count >= min_len:
                display = label_fn(val) if label_fn else str(val)
                opposite = None
                if isinstance(val, str) and val in ("大", "小"):
                    opposite = "小" if val == "大" else "大"
                elif isinstance(val, str) and val in ("奇", "偶"):
                    opposite = "偶" if val == "奇" else "奇"
                streaks.append({
                    "feature": name,
                    "value": display,
                    "streak": count,
                    "opposite": opposite,
                })

        _scan(recent["sum_tail_size"], "和尾大小")
        _scan(recent["sum_road"], "和值012路", lambda v: f"{v}路")
        _scan(recent["road1"], "百位012路", lambda v: f"{v}路")
        _scan(recent["road2"], "十位012路", lambda v: f"{v}路")
        _scan(recent["road3"], "个位012路", lambda v: f"{v}路")

        recent["sum_parity"] = recent["sum_val"].apply(lambda x: "奇" if x % 2 else "偶")
        _scan(recent["sum_parity"], "和值奇偶")

        recent["odd_count"] = recent.apply(
            lambda r: sum(1 for d in [r["num1"], r["num2"], r["num3"]] if d % 2 == 1), axis=1
        )
        _scan(recent["odd_count"], "奇数个数")

        recent["big_count"] = recent.apply(
            lambda r: sum(1 for d in [r["num1"], r["num2"], r["num3"]] if d >= 5), axis=1
        )
        _scan(recent["big_count"], "大号个数")

        _scan(recent["pattern"], "形态")
        _scan(recent["span"], "跨度")

        return streaks

    def missing_recovery(self):
        result = []
        patterns = {
            "组三": lambda r: r["pattern"] == "组三",
            "组六": lambda r: r["pattern"] == "组六",
            "豹子": lambda r: r["pattern"] == "豹子",
            "全大(5-9)": lambda r: r["num1"] >= 5 and r["num2"] >= 5 and r["num3"] >= 5,
            "全小(0-4)": lambda r: r["num1"] < 5 and r["num2"] < 5 and r["num3"] < 5,
            "全偶": lambda r: r["num1"] % 2 == 0 and r["num2"] % 2 == 0 and r["num3"] % 2 == 0,
            "全奇": lambda r: r["num1"] % 2 == 1 and r["num2"] % 2 == 1 and r["num3"] % 2 == 1,
            "0路全占": lambda r: 0 in (r["road1"], r["road2"], r["road3"])
                                 and 1 in (r["road1"], r["road2"], r["road3"])
                                 and 2 in (r["road1"], r["road2"], r["road3"]),
            "和值0路": lambda r: r["sum_road"] == 0,
            "和值1路": lambda r: r["sum_road"] == 1,
            "和值2路": lambda r: r["sum_road"] == 2,
            "和尾大(5-9)": lambda r: r["sum_tail_size"] == "大",
            "和尾小(0-4)": lambda r: r["sum_tail_size"] == "小",
        }

        for name, cond in patterns.items():
            count = 0
            for _, r in self.df.iloc[::-1].iterrows():
                if cond(r):
                    break
                count += 1

            hits = sum(1 for _, r in self.df.iterrows() if cond(r))
            prob = hits / self.total if self.total > 0 else 0
            avg_miss = 1 / prob if prob > 0 else float("inf")

            is_recovery = count > avg_miss * 3 and avg_miss < float("inf")
            result.append({
                "pattern": name,
                "current_missing": count,
                "hit_count": hits,
                "probability": prob,
                "avg_missing": avg_miss,
                "is_high_recovery": is_recovery,
            })

        return result

    def generate_schemes(self, n_schemes=3):
        streaks = self.streak_scan(min_len=3)
        recoveries = [r for r in self.missing_recovery() if r["is_high_recovery"]]
        hotness = self.digit_hotness()
        missing = calc_missing(self.df)

        digit_scores = {}
        for d in range(10):
            score = 0.0
            reasons = []

            miss_val = missing.get(d, 0)
            total = self.total
            avg_miss = total / 10.0
            if miss_val > avg_miss * 2:
                score += 3.0
                reasons.append(f"{d}遗漏{miss_val}期(超2倍均值)")
            elif miss_val > avg_miss:
                score += 1.5
                reasons.append(f"{d}遗漏{miss_val}期")

            for window in [10, 30, 50]:
                freq = hotness[window].get(d, 0)
                expected = window * 3 / 10.0
                if freq < expected * 0.5:
                    score += 1.0
                    reasons.append(f"近{window}期仅{freq}次")

            for rec in recoveries:
                pname = rec["pattern"]
                if "全大" in pname and d >= 5:
                    score += 2.0
                    reasons.append(f"全大回补利好{d}")
                elif "全小" in pname and d < 5:
                    score += 2.0
                    reasons.append(f"全小回补利好{d}")
                elif "全偶" in pname and d % 2 == 0:
                    score += 2.0
                    reasons.append(f"全偶回补利好{d}")
                elif "全奇" in pname and d % 2 == 1:
                    score += 2.0
                    reasons.append(f"全奇回补利好{d}")
                elif f"和值{d % 3}路" in pname:
                    score += 1.5
                    reasons.append(f"和值{d % 3}路回补利好{d}")

            for s in streaks:
                feat = s["feature"]
                opp = s["opposite"]
                if feat == "和尾大小" and opp:
                    if opp == "小" and d < 5:
                        score += 2.0
                        reasons.append(f"和尾小反转利好{d}")
                    elif opp == "大" and d >= 5:
                        score += 2.0
                        reasons.append(f"和尾大反转利好{d}")
                elif feat == "和值奇偶" and opp:
                    if opp == "偶" and d % 2 == 0:
                        score += 1.5
                        reasons.append(f"偶数反转利好{d}")
                    elif opp == "奇" and d % 2 == 1:
                        score += 1.5
                        reasons.append(f"奇数反转利好{d}")
                elif feat in ("百位012路", "十位012路", "个位012路") and opp:
                    if isinstance(opp, list) and d % 3 in opp:
                        score += 1.0
                        reasons.append(f"{feat}反转利好{d}路")

            digit_scores[d] = {"score": score, "reasons": reasons}

        ranked = sorted(digit_scores.items(), key=lambda x: -x[1]["score"])
        all_digits = [d for d, _ in ranked]

        schemes = []
        rotation_steps = [0, 3, 6]
        for i, step in enumerate(rotation_steps[:n_schemes]):
            selected = []
            for j in range(10):
                idx = (step + j) % 10
                d = all_digits[idx]
                if d not in selected:
                    selected.append(d)
                if len(selected) == 7:
                    break
            if len(selected) < 7:
                for d in all_digits:
                    if d not in selected:
                        selected.append(d)
                    if len(selected) == 7:
                        break
            selected = sorted(selected)

            digit_reasons = []
            for d in selected:
                for reason in digit_scores[d]["reasons"][:1]:
                    if reason not in digit_reasons:
                        digit_reasons.append(reason)

            context_reasons = []
            for s in streaks[:2]:
                if s["opposite"]:
                    t = f"{s['feature']}连出{s['streak']}期，关注{s['opposite']}"
                    if t not in context_reasons:
                        context_reasons.append(t)
            for r in recoveries[:2]:
                t = f"{r['pattern']}遗漏{r['current_missing']}期(理论{r['avg_missing']:.1f}期)"
                if t not in context_reasons:
                    context_reasons.append(t)

            scheme_reasons = digit_reasons[:2] + context_reasons[:1]

            schemes.append({
                "index": i + 1,
                "digits": selected,
                "reasons": scheme_reasons[:3],
                "detail": {d: digit_scores[d] for d in selected},
            })

        return schemes


def evaluate_user_numbers(input_nums, df_feat):
    n1, n2, n3 = sorted(input_nums)
    total = len(df_feat)
    recent = df_feat.tail(30)
    last = df_feat.iloc[-1]
    prev_nums = {last["num1"], last["num2"], last["num3"]}

    sum_val = n1 + n2 + n3
    sum_tail = sum_val % 10
    roads = [n1 % 3, n2 % 3, n3 % 3]
    road_set = set(roads)
    span = n3 - n1

    score = 0
    details = []

    # 1) sum distribution (0-20 points)
    sum_freq = sum(1 for _, r in df_feat.iterrows() if r["sum_val"] == sum_val)
    sum_prob = sum_freq / total if total > 0 else 0
    if 7 <= sum_val <= 20:
        score += 20
        details.append(f"和值{sum_val}处于高频区(7-20)")
    elif 4 <= sum_val <= 6 or 21 <= sum_val <= 23:
        score += 12
        details.append(f"和值{sum_val}处于中频区")
    else:
        score += 4
        details.append(f"和值{sum_val}处于极低频区(0-3或24-27)")

    # 2) 012 road balance (0-20 points)
    if len(road_set) == 3:
        score += 20
        details.append("012路全占(0/1/2路各一)，平衡度极佳")
    elif len(road_set) == 2:
        score += 14
        missing_road = [r for r in [0, 1, 2] if r not in road_set][0]
        details.append(f"012路缺{missing_road}路，平衡度中等")
    else:
        score += 6
        details.append(f"012路全为{roads[0]}路，严重偏态")

    # 3) digit hotness (0-20 points)
    hotness = calc_hotness(df_feat, 30)
    missing = calc_missing(df_feat)
    hot_score = 0
    hot_details = []
    for d in [n1, n2, n3]:
        freq = hotness.get(d, 0)
        miss = missing.get(d, 0)
        avg_miss = total / 10.0
        if freq >= 12:
            hot_score += 7
            hot_details.append(f"{d}为热号(近30期{freq}次)")
        elif miss > avg_miss * 2:
            hot_score += 6
            hot_details.append(f"{d}为回补号(遗漏{miss}期)")
        elif freq >= 8:
            hot_score += 5
            hot_details.append(f"{d}为温号(近30期{freq}次)")
        elif freq <= 5:
            hot_score += 1
            hot_details.append(f"{d}为冷号(近30期仅{freq}次)")
        else:
            hot_score += 3
            hot_details.append(f"{d}为一般号(近30期{freq}次)")
    hot_score = min(hot_score, 20)
    score += hot_score
    details.extend(hot_details)

    # 4) span distribution (0-20 points)
    span_freq = sum(1 for _, r in df_feat.iterrows() if r["span"] == span)
    span_prob = span_freq / total if total > 0 else 0
    if 3 <= span <= 7:
        score += 20
        details.append(f"跨度{span}处于高频区(3-7)")
    elif span in [2, 8]:
        score += 12
        details.append(f"跨度{span}处于中频区")
    else:
        score += 4
        details.append(f"跨度{span}处于极低频区(0-1或9)")

    # 5) neighbor/isolated/transmit (0-20 points)
    tags = []
    for d in [n1, n2, n3]:
        if d in prev_nums:
            tags.append("传")
        elif any(abs(d - p) == 1 or abs(d - p) == 9 for p in prev_nums):
            tags.append("邻")
        else:
            tags.append("孤")
    c, l, g = tags.count("传"), tags.count("邻"), tags.count("孤")

    if c == 1 and l >= 1:
        score += 18
        details.append(f"邻孤传{c}传{l}邻{g}孤，传邻结合较佳")
    elif c >= 2:
        score += 14
        details.append(f"邻孤传{c}传{l}邻{g}孤，传号偏多")
    elif l >= 2:
        score += 16
        details.append(f"邻孤传{c}传{l}邻{g}孤，邻号活跃")
    elif g >= 2:
        score += 8
        details.append(f"邻孤传{c}传{l}邻{g}孤，孤号偏多(与上期关联弱)")
    else:
        score += 12
        details.append(f"邻孤传{c}传{l}邻{g}孤")

    # kill numbers & core numbers
    engine = LotteryPatternEngine(df_feat)
    streaks = engine.streak_scan(min_len=3)
    recoveries = engine.missing_recovery()

    digit_kill_score = {}
    for d in range(10):
        ks = 0.0
        freq = hotness.get(d, 0)
        if freq <= 5:
            ks += 3.0
        miss = missing.get(d, 0)
        if miss == 0:
            ks += 1.0
        for s in streaks:
            if s["feature"] == "和尾大小" and s["opposite"]:
                if s["opposite"] == "小" and d >= 5:
                    ks += 2.0
                elif s["opposite"] == "大" and d < 5:
                    ks += 2.0
            if s["feature"] == "和值奇偶" and s["opposite"]:
                if s["opposite"] == "偶" and d % 2 == 1:
                    ks += 1.5
                elif s["opposite"] == "奇" and d % 2 == 0:
                    ks += 1.5
        digit_kill_score[d] = ks

    kill_numbers = sorted(range(10), key=lambda d: -digit_kill_score[d])[:2]
    core_numbers = sorted(range(10), key=lambda d: digit_kill_score[d])[:2]

    # generate explanation
    if score >= 80:
        verdict = "⭐ 强力推荐"
    elif score >= 65:
        verdict = "✅ 值得关注"
    elif score >= 50:
        verdict = "⚠️ 一般偏弱"
    else:
        verdict = "❌ 不建议选择"

    explanation = f"此码和值{sum_val}"
    if 7 <= sum_val <= 20:
        explanation += "，处于高频区"
    else:
        explanation += "，处于低频区"
    explanation += "；"
    explanation += "；".join(hot_details[:2]) + "；"
    if any(d in kill_numbers for d in [n1, n2, n3]):
        hit_kills = [d for d in [n1, n2, n3] if d in kill_numbers]
        explanation += f"包含杀号{''.join(map(str, hit_kills))}，需警惕"
    else:
        explanation += "避开了当前杀号，较为安全"

    return {
        "score": score,
        "verdict": verdict,
        "details": details,
        "kill_numbers": kill_numbers,
        "core_numbers": core_numbers,
        "explanation": explanation,
        "sum_val": sum_val,
        "sum_tail": sum_tail,
        "roads": roads,
        "span": span,
        "lgc": f"{c}传{l}邻{g}孤",
    }


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

df_feat = extract_features(df)

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

with st.sidebar:
    st.header("🤖 我的决策助手")

    engine_sb = LotteryPatternEngine(df)
    hotness_sb = engine_sb.digit_hotness()
    missing_sb = calc_missing(df)
    streaks_sb = engine_sb.streak_scan(min_len=3)

    digit_kill_score_sb = {}
    for d in range(10):
        ks = 0.0
        freq = hotness_sb[30].get(d, 0)
        if freq <= 5:
            ks += 3.0
        miss = missing_sb.get(d, 0)
        if miss == 0:
            ks += 1.0
        for s in streaks_sb:
            if s["feature"] == "和尾大小" and s["opposite"]:
                if s["opposite"] == "小" and d >= 5:
                    ks += 2.0
                elif s["opposite"] == "大" and d < 5:
                    ks += 2.0
            if s["feature"] == "和值奇偶" and s["opposite"]:
                if s["opposite"] == "偶" and d % 2 == 1:
                    ks += 1.5
                elif s["opposite"] == "奇" and d % 2 == 0:
                    ks += 1.5
        digit_kill_score_sb[d] = ks

    kill_sb = sorted(range(10), key=lambda d: -digit_kill_score_sb[d])[:2]
    core_sb = sorted(range(10), key=lambda d: digit_kill_score_sb[d])[:2]

    st.subheader("🎯 今日推荐胆码")
    core_c1, core_c2 = st.columns(2)
    core_c1.markdown(
        f'<div style="text-align:center;padding:14px;background:linear-gradient(135deg,#1a2e1a,#0f4f0f);'
        f'border-radius:10px;border:2px solid #6bcb77">'
        f'<div style="color:#6bcb77;font-size:11px">胆码1</div>'
        f'<div style="font-size:36px;font-weight:bold;color:#6bcb77">{core_sb[0]}</div></div>',
        unsafe_allow_html=True,
    )
    core_c2.markdown(
        f'<div style="text-align:center;padding:14px;background:linear-gradient(135deg,#1a2e1a,#0f4f0f);'
        f'border-radius:10px;border:2px solid #6bcb77">'
        f'<div style="color:#6bcb77;font-size:11px">胆码2</div>'
        f'<div style="font-size:36px;font-weight:bold;color:#6bcb77">{core_sb[1]}</div></div>',
        unsafe_allow_html=True,
    )

    st.subheader("🚫 参考杀号")
    kill_c1, kill_c2 = st.columns(2)
    kill_c1.markdown(
        f'<div style="text-align:center;padding:14px;background:linear-gradient(135deg,#2e1a1a,#4f0f0f);'
        f'border-radius:10px;border:2px solid #ff6b6b">'
        f'<div style="color:#ff6b6b;font-size:11px">杀号1</div>'
        f'<div style="font-size:36px;font-weight:bold;color:#ff6b6b">{kill_sb[0]}</div></div>',
        unsafe_allow_html=True,
    )
    kill_c2.markdown(
        f'<div style="text-align:center;padding:14px;background:linear-gradient(135deg,#2e1a1a,#4f0f0f);'
        f'border-radius:10px;border:2px solid #ff6b6b">'
        f'<div style="color:#ff6b6b;font-size:11px">杀号2</div>'
        f'<div style="font-size:36px;font-weight:bold;color:#ff6b6b">{kill_sb[1]}</div></div>',
        unsafe_allow_html=True,
    )

    backtest_n = min(50, len(df))
    backtest_df = df.tail(backtest_n)
    core_hits = 0
    kill_success = 0
    for _, r in backtest_df.iterrows():
        draw_set = {r["num1"], r["num2"], r["num3"]}
        if any(d in draw_set for d in core_sb):
            core_hits += 1
        if not any(d in draw_set for d in kill_sb):
            kill_success += 1
    st.caption(
        f"📊 历史统计：近{backtest_n}期胆码命中{core_hits}次({core_hits / backtest_n:.0%})，"
        f"杀号成功排除{kill_success}次({kill_success / backtest_n:.0%})"
    )

    st.divider()
    st.subheader("📝 意向码输入")
    input_c1, input_c2, input_c3 = st.columns(3)
    with input_c1:
        sb_n1 = st.selectbox("百位", list(range(10)), key="sb_n1")
    with input_c2:
        sb_n2 = st.selectbox("十位", list(range(10)), key="sb_n2")
    with input_c3:
        sb_n3 = st.selectbox("个位", list(range(10)), key="sb_n3")

    eval_clicked = st.button("🚀 立即测评", use_container_width=True, type="primary", key="sb_eval")

    if eval_clicked:
        result_sb = evaluate_user_numbers([sb_n1, sb_n2, sb_n3], df_feat)
        score_sb = result_sb["score"]
        score_color_sb = "#6bcb77" if score_sb >= 65 else "#ffd93d" if score_sb >= 50 else "#ff6b6b"

        st.markdown(
            f'<div style="text-align:center;padding:16px;background:linear-gradient(135deg,#1a1a2e,#0f3460);'
            f'border-radius:12px;border:2px solid {score_color_sb};margin:8px 0">'
            f'<div style="font-size:12px;color:#aaa">推荐指数</div>'
            f'<div style="font-size:48px;font-weight:bold;color:{score_color_sb}">{score_sb}<span style="font-size:16px;color:#aaa">/100</span></div>'
            f'<div style="font-size:16px;color:{score_color_sb}">{result_sb["verdict"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.progress(score_sb / 100.0)

        with st.expander("📋 专家测评解释", expanded=True):
            st.markdown(f"**💬 {result_sb['explanation']}**")
            st.divider()
            for detail in result_sb["details"]:
                icon = "✅" if any(kw in detail for kw in ["高频", "全占", "热号", "回补", "较佳", "活跃"]) else "⚠️" if any(kw in detail for kw in ["中频", "缺", "温号", "一般", "偏多"]) else "❌"
                st.markdown(f"{icon} {detail}")

        if any(d in kill_sb for d in [sb_n1, sb_n2, sb_n3]):
            hit_k = [d for d in [sb_n1, sb_n2, sb_n3] if d in kill_sb]
            st.warning(f"⚠️ 您的意向码包含当前杀号 {hit_k}，建议替换！")
        if any(d in core_sb for d in [sb_n1, sb_n2, sb_n3]):
            hit_c = [d for d in [sb_n1, sb_n2, sb_n3] if d in core_sb]
            st.success(f"✅ 您的意向码包含推荐胆码 {hit_c}，选择合理！")

    st.divider()
    st.caption("⚠️ 仅供参考，不构成投注建议")

tab1, tab2, tab3, tab4 = st.tabs(["📊 数据总览", "📈 走势统计", "🎯 策略回测", "🧭 专家决策看板"])

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

    _engine = LotteryPatternEngine(df_feat)
    _schemes = _engine.generate_schemes(n_schemes=3)
    default_sevens = [''.join(map(str, s['digits'])) for s in _schemes]
    scheme_reasons = [s.get('reasons', []) for s in _schemes]

    _hotness_map = calc_hotness(df_feat, 30)

    def _rank_by_hotness(digits, hotness):
        return sorted(digits, key=lambda d: (-hotness.get(d, 0), d))

    def _dedup_subset(ranked, size, prev_keys, hotness):
        candidate = ranked[:size]
        key = tuple(sorted(candidate))
        if key not in prev_keys or len(ranked) <= size:
            return candidate
        for swap_pos in range(size - 1, -1, -1):
            for replacement in ranked[size:]:
                trial = candidate[:swap_pos] + [replacement] + candidate[swap_pos + 1:]
                trial_key = tuple(sorted(trial))
                if trial_key not in prev_keys:
                    return sorted(trial, key=lambda d: (-hotness.get(d, 0), d))
        return candidate

    prev_five_keys = []
    prev_six_keys = []

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
                if scheme_reasons[i]:
                    st.caption(" · ".join(scheme_reasons[i][:3]))

            seven_digits = [int(c) for c in raw if c.isdigit()]
            seven_digits = list(dict.fromkeys(seven_digits))[:7]

            ranked = _rank_by_hotness(seven_digits, _hotness_map)

            if len(ranked) >= 6:
                six_digits = _dedup_subset(ranked, 6, prev_six_keys, _hotness_map)
            else:
                six_digits = ranked[:6] if len(ranked) >= 6 else []
            prev_six_keys.append(tuple(sorted(six_digits)))

            six_ranked = _rank_by_hotness(six_digits, _hotness_map)
            if len(six_ranked) >= 5:
                five_digits = _dedup_subset(six_ranked, 5, prev_five_keys, _hotness_map)
            else:
                five_digits = six_ranked[:5] if len(six_ranked) >= 5 else []
            prev_five_keys.append(tuple(sorted(five_digits)))

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

            with st.expander(f"📋 第 {i + 1} 组 · 组六组合注数明细"):
                combo_rows = []
                for n_digits, label, multiplier in [(7, "7码", 4.3), (6, "6码", 7.5), (5, "5码", 15.0)]:
                    digits_set = group.get(n_digits)
                    if not digits_set:
                        continue
                    combos = list(itertools.combinations(sorted(digits_set), 3))
                    zu6_count = 0
                    zu3_count = 0
                    combo_strs = []
                    for c in combos:
                        if c[0] == c[1] or c[1] == c[2] or c[0] == c[2]:
                            continue
                        combo_strs.append("".join(map(str, c)))
                        if len(set(c)) == 3:
                            zu6_count += 1
                        else:
                            zu3_count += 1
                    total_bets = comb(len(digits_set), 3)
                    cost = total_bets * 2
                    st.markdown(f"**{label} ({''.join(map(str, sorted(digits_set)))})**")
                    st.markdown(
                        f"组六 {zu6_count} 注 + 组三 {zu3_count} 注 = **{total_bets} 注** · 每期 **{cost} 元**"
                    )
                    cols_combo = st.columns(min(len(combo_strs), 10))
                    for ci, cs in enumerate(combo_strs):
                        with cols_combo[ci % len(cols_combo)]:
                            st.code(cs, language=None)
                    st.markdown("---")

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

with tab4:
    engine = LotteryPatternEngine(df_feat)

    st.subheader("🔢 号码热度统计")
    hotness = engine.digit_hotness()
    hot_df_data = []
    for d in range(10):
        hot_df_data.append({
            "号码": d,
            "近10期": hotness[10][d],
            "近30期": hotness[30][d],
            "近50期": hotness[50][d],
        })
    hot_df = pd.DataFrame(hot_df_data)
    hc1, hc2 = st.columns([2, 3])
    with hc1:
        st.dataframe(hot_df, use_container_width=True, hide_index=True)
    with hc2:
        fig_hot = go.Figure()
        for window, color in [(10, "#ff6b6b"), (30, "#4dabf7"), (50, "#6bcb77")]:
            fig_hot.add_trace(go.Bar(
                x=list(range(10)),
                y=[hotness[window][d] for d in range(10)],
                name=f"近{window}期",
                marker_color=color,
                opacity=0.8,
            ))
        fig_hot.update_layout(
            barmode="group",
            xaxis=dict(dtick=1, title="号码"),
            yaxis_title="出现次数",
            height=280,
            margin=dict(t=20, b=30),
            legend=dict(orientation="h", y=1.15),
        )
        st.plotly_chart(fig_hot, use_container_width=True)

    st.divider()
    st.subheader("🔥 连出扫描")
    streaks = engine.streak_scan(min_len=3)
    if streaks:
        for s in streaks:
            opp_text = f"，反转关注【{s['opposite']}】" if s["opposite"] else ""
            st.markdown(
                f'<div style="background:linear-gradient(135deg,#2e2e1a,#2e2a16);'
                f'border-left:4px solid #ffd93d;padding:10px 14px;border-radius:8px;'
                f'margin:6px 0;font-size:14px;color:#e0e0e0">'
                f'📊 <b>{s["feature"]}</b> 连续为【{s["value"]}】，已连出 <b>{s["streak"]}</b> 期{opp_text}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("近30期未检测到连续3期以上的特征连出。")

    st.divider()
    st.subheader("♻️ 遗漏回补分析")
    recoveries = engine.missing_recovery()
    rec_df = pd.DataFrame(recoveries)
    rec_df_display = rec_df[["pattern", "current_missing", "avg_missing", "probability", "is_high_recovery"]].copy()
    rec_df_display.columns = ["形态", "当前遗漏", "理论遗漏", "理论概率", "高概率回补"]
    rec_df_display["理论遗漏"] = rec_df_display["理论遗漏"].round(1)
    rec_df_display["理论概率"] = rec_df_display["理论概率"].apply(lambda x: f"{x:.1%}")
    rec_df_display["高概率回补"] = rec_df_display["高概率回补"].map({True: "✅ 是", False: ""})

    def _highlight_recovery(val):
        if val == "✅ 是":
            return "background-color: #2e4a2e; color: #6bcb77; font-weight: bold"
        return ""

    styled = rec_df_display.style.map(_highlight_recovery, subset=["高概率回补"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    high_rec = [r for r in recoveries if r["is_high_recovery"]]
    if high_rec:
        st.markdown("**🚨 高概率回补形态：**")
        for r in high_rec:
            st.markdown(
                f'<div style="background:linear-gradient(135deg,#1a2e1a,#162e16);'
                f'border-left:4px solid #6bcb77;padding:10px 14px;border-radius:8px;'
                f'margin:6px 0;font-size:14px;color:#e0e0e0">'
                f'♻️ <b>{r["pattern"]}</b>：当前遗漏 <b>{r["current_missing"]}</b> 期，'
                f'理论遗漏 {r["avg_missing"]:.1f} 期（{r["current_missing"] / r["avg_missing"]:.1f}倍），'
                f'回补概率极高</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("🎯 7码推荐方案")
    schemes = engine.generate_schemes(n_schemes=3)
    scheme_cols = st.columns(3)
    for i, scheme in enumerate(schemes):
        with scheme_cols[i]:
            digits_str = " ".join(map(str, scheme["digits"]))
            st.markdown(
                f'<div style="text-align:center;padding:20px;background:linear-gradient(135deg,#1a1a2e,#0f3460);'
                f'border-radius:12px;border:1px solid #4dabf7">'
                f'<div style="color:#4dabf7;font-size:13px;margin-bottom:10px">方案 {scheme["index"]}</div>'
                f'<div style="font-size:36px;font-weight:bold;color:#fff;letter-spacing:8px">'
                f'{digits_str}</div></div>',
                unsafe_allow_html=True,
            )
            if scheme["reasons"]:
                st.markdown(
                    f'<div style="font-size:12px;color:#aaa;margin-top:8px;padding:0 4px">'
                    f'{"<br/>".join(scheme["reasons"])}</div>',
                    unsafe_allow_html=True,
                )
            with st.expander("详细依据"):
                for detail in scheme["detail"]:
                    st.markdown(f"- {detail}")

    st.divider()
    recs, warns = expert_decision_engine(df_feat)

    col_rec, col_warn = st.columns(2)

    with col_rec:
        st.subheader("🎯 高胜率推荐")
        if recs:
            for i, r in enumerate(recs, 1):
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#1a2e1a,#162e16);'
                    f'border-left:4px solid #6bcb77;padding:12px 16px;border-radius:8px;'
                    f'margin:8px 0;font-size:14px;color:#e0e0e0">'
                    f'<b style="color:#6bcb77">推荐{i}</b><br/>{r}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("暂无高置信度推荐，数据较为随机。")

        st.divider()
        st.subheader("📊 号码推荐汇总")
        last_row = df_feat.iloc[-1]
        pred_bai = (last_row["num2"] + last_row["num3"]) % 10
        pred_shi = (last_row["num1"] + last_row["num3"]) % 10
        pred_ge = (last_row["num1"] + last_row["num2"]) % 10

        miss_sorted = sorted(range(10), key=lambda d: -calc_missing(df_feat)[d])
        top_miss = miss_sorted[:5]

        rec_bai = sorted(set([pred_bai] + [d for d in top_miss[:3]]))
        rec_shi = sorted(set([pred_shi] + [d for d in top_miss[2:5]]))
        rec_ge = sorted(set([pred_ge] + [d for d in top_miss[1:4]]))

        c1, c2, c3 = st.columns(3)
        c1.markdown(
            f'<div style="text-align:center;padding:16px;background:#1a1a2e;border-radius:10px">'
            f'<div style="color:#ff6b6b;font-size:13px;margin-bottom:8px">百位推荐</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#ff6b6b;letter-spacing:6px">'
            f'{" ".join(map(str, rec_bai))}</div></div>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f'<div style="text-align:center;padding:16px;background:#1a1a2e;border-radius:10px">'
            f'<div style="color:#4dabf7;font-size:13px;margin-bottom:8px">十位推荐</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#4dabf7;letter-spacing:6px">'
            f'{" ".join(map(str, rec_shi))}</div></div>',
            unsafe_allow_html=True,
        )
        c3.markdown(
            f'<div style="text-align:center;padding:16px;background:#1a1a2e;border-radius:10px">'
            f'<div style="color:#6bcb77;font-size:13px;margin-bottom:8px">个位推荐</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#6bcb77;letter-spacing:6px">'
            f'{" ".join(map(str, rec_ge))}</div></div>',
            unsafe_allow_html=True,
        )

    with col_warn:
        st.subheader("⚡ 避雷针 · 垃圾组合剔除")
        if warns:
            for i, w in enumerate(warns, 1):
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#2e1a1a,#2e1616);'
                    f'border-left:4px solid #ff6b6b;padding:12px 16px;border-radius:8px;'
                    f'margin:8px 0;font-size:14px;color:#e0e0e0">'
                    f'<b style="color:#ff6b6b">避雷{i}</b><br/>{w}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("暂无明确避雷信号。")

        st.divider()
        st.subheader("🚫 排除号码汇总")
        hotness = calc_hotness(df_feat, 30)
        cold_digits = sorted([d for d in range(10) if hotness[d] <= 5])
        exclude_str = "、".join(map(str, cold_digits)) if cold_digits else "无"
        st.markdown(
            f'<div style="text-align:center;padding:16px;background:#2e1a1a;border-radius:10px">'
            f'<div style="color:#ff6b6b;font-size:13px;margin-bottom:8px">极冷号（近30期≤5次）</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#ff6b6b;letter-spacing:6px">'
            f'{exclude_str}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("🔗 近5期规律链路图")
    fig_chain = build_pattern_chain_chart(df_feat, n_periods=5)
    st.plotly_chart(fig_chain, use_container_width=True)

    last5 = df_feat.tail(5).iloc[::-1]
    chain_data = []
    for _, r in last5.iterrows():
        chain_data.append({
            "期号": r["period"],
            "日期": r["draw_date"],
            "号码": f'{r["num1"]}{r["num2"]}{r["num3"]}',
            "和尾": r["sum_tail"],
            "和尾大小": r["sum_tail_size"],
            "012路": f'{r["road1"]}{r["road2"]}{r["road3"]}',
            "跨度": r["span"],
            "邻孤传": r["lgc"],
        })
    st.dataframe(pd.DataFrame(chain_data), use_container_width=True, hide_index=True)

    st.caption("⚠️ 以上分析基于历史数据统计规律，仅供参考，不构成投注建议。彩票开奖为随机事件。")

    st.divider()
    st.subheader("🔍 号码评价器")
    st.markdown("选择 3 个数字，系统将基于五维模型计算推荐指数")

    eval_cols = st.columns(3)
    with eval_cols[0]:
        sel_1 = st.selectbox("第一位", list(range(10)), key="eval_n1")
    with eval_cols[1]:
        sel_2 = st.selectbox("第二位", list(range(10)), key="eval_n2")
    with eval_cols[2]:
        sel_3 = st.selectbox("第三位", list(range(10)), key="eval_n3")

    if st.button("📊 开始评价", use_container_width=True, key="eval_btn"):
        result = evaluate_user_numbers([sel_1, sel_2, sel_3], df_feat)

        score_color = "#6bcb77" if result["score"] >= 65 else "#ffd93d" if result["score"] >= 50 else "#ff6b6b"
        st.markdown(
            f'<div style="text-align:center;padding:24px;background:linear-gradient(135deg,#1a1a2e,#0f3460);'
            f'border-radius:16px;border:2px solid {score_color}">'
            f'<div style="font-size:14px;color:#aaa;margin-bottom:8px">推荐指数</div>'
            f'<div style="font-size:64px;font-weight:bold;color:{score_color}">{result["score"]}</div>'
            f'<div style="font-size:20px;color:{score_color};margin-top:4px">{result["verdict"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        dim_cols = st.columns(5)
        dim_names = ["和值分布", "012路平衡", "数字热度", "跨度分布", "邻孤传"]
        dim_scores = []
        s = result["score"]
        for detail in result["details"][:5]:
            dim_scores.append(min(20, max(0, s // 5)))
        dim_actual = [0] * 5
        for detail in result["details"]:
            if "和值" in detail:
                dim_actual[0] = 20 if "高频" in detail else 12 if "中频" in detail else 4
            elif "012路" in detail:
                dim_actual[1] = 20 if "全占" in detail else 14 if "缺" in detail else 6
            elif "热号" in detail or "回补" in detail or "温号" in detail or "冷号" in detail or "一般号" in detail:
                if dim_actual[2] == 0:
                    dim_actual[2] = min(20, result["score"] - sum(dim_actual) + dim_actual[2])
            elif "跨度" in detail:
                dim_actual[3] = 20 if "高频" in detail else 12 if "中频" in detail else 4
            elif "邻孤传" in detail:
                dim_actual[4] = 18 if "较佳" in detail else 16 if "活跃" in detail else 14 if "偏多" in detail else 12

        for i, (name, sc) in enumerate(zip(dim_names, dim_actual)):
            bar_color = "#6bcb77" if sc >= 16 else "#ffd93d" if sc >= 10 else "#ff6b6b"
            with dim_cols[i]:
                st.markdown(
                    f'<div style="text-align:center">'
                    f'<div style="font-size:11px;color:#aaa;margin-bottom:4px">{name}</div>'
                    f'<div style="font-size:24px;font-weight:bold;color:{bar_color}">{sc}</div>'
                    f'<div style="background:#333;height:4px;border-radius:2px;margin-top:4px">'
                    f'<div style="background:{bar_color};height:4px;border-radius:2px;width:{sc * 5}%"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("#### 📝 评价详情")
        for detail in result["details"]:
            icon = "✅" if any(kw in detail for kw in ["高频", "全占", "热号", "回补", "较佳", "活跃"]) else "⚠️" if any(kw in detail for kw in ["中频", "缺", "温号", "一般", "偏多"]) else "❌"
            st.markdown(f"- {icon} {detail}")

        st.markdown("#### 🎯 杀码与胆码")
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.markdown(
            f'<div style="text-align:center;padding:12px;background:#2e1a1a;border-radius:8px">'
            f'<div style="color:#ff6b6b;font-size:12px">杀号1</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#ff6b6b">{result["kill_numbers"][0]}</div></div>',
            unsafe_allow_html=True,
        )
        kc2.markdown(
            f'<div style="text-align:center;padding:12px;background:#2e1a1a;border-radius:8px">'
            f'<div style="color:#ff6b6b;font-size:12px">杀号2</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#ff6b6b">{result["kill_numbers"][1]}</div></div>',
            unsafe_allow_html=True,
        )
        kc3.markdown(
            f'<div style="text-align:center;padding:12px;background:#1a2e1a;border-radius:8px">'
            f'<div style="color:#6bcb77;font-size:12px">胆码1</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#6bcb77">{result["core_numbers"][0]}</div></div>',
            unsafe_allow_html=True,
        )
        kc4.markdown(
            f'<div style="text-align:center;padding:12px;background:#1a2e1a;border-radius:8px">'
            f'<div style="color:#6bcb77;font-size:12px">胆码2</div>'
            f'<div style="font-size:28px;font-weight:bold;color:#6bcb77">{result["core_numbers"][1]}</div></div>',
            unsafe_allow_html=True,
        )

        st.markdown("#### 💬 综合评语")
        st.info(result["explanation"])