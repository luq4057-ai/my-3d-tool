import sqlite3
from math import comb
from collections import Counter

DB_FILE = "lottery_data.db"
TABLE_NAME = "history3d"

MULTIPLIERS = {5: 15.0, 6: 7.5, 7: 4.3}


class StrategyAnalyzer:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.records = []
        self._load_data()

    def _load_data(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT period, num1, num2, num3, pattern, draw_date "
            f"FROM {TABLE_NAME} ORDER BY period ASC"
        )
        self.records = cursor.fetchall()
        conn.close()
        print(f"已加载 {len(self.records)} 期历史数据")

    def simulate(self, digits):
        digits = set(digits)
        n = len(digits)
        if n not in MULTIPLIERS:
            raise ValueError(f"仅支持5码/6码/7码组选，当前选了{n}个数字")

        multiplier = MULTIPLIERS[n]
        zu6_bets = comb(n, 3)
        zu3_bets = n * (n - 1)
        total_bets = zu6_bets + zu3_bets
        cost_per_period = total_bets * 2

        wins = 0
        zu6_wins = 0
        zu3_wins = 0

        for _, n1, n2, n3, pattern, _ in self.records:
            if pattern == "豹子":
                continue
            winning_set = {n1, n2, n3}
            if winning_set.issubset(digits):
                wins += 1
                if pattern == "组六":
                    zu6_wins += 1
                elif pattern == "组三":
                    zu3_wins += 1

        total_periods = len(self.records)
        win_rate = wins / total_periods if total_periods > 0 else 0
        total_investment = cost_per_period * total_periods
        total_return = wins * cost_per_period * multiplier
        net_profit = total_return - total_investment

        return {
            "mode": f"{n}码组选",
            "digits": sorted(digits),
            "n": n,
            "multiplier": multiplier,
            "zu6_bets": zu6_bets,
            "zu3_bets": zu3_bets,
            "total_bets": total_bets,
            "cost_per_period": cost_per_period,
            "total_periods": total_periods,
            "wins": wins,
            "zu6_wins": zu6_wins,
            "zu3_wins": zu3_wins,
            "win_rate": win_rate,
            "total_investment": total_investment,
            "total_return": total_return,
            "net_profit": net_profit,
            "roi": (net_profit / total_investment * 100) if total_investment > 0 else 0,
        }

    def simulate_multi(self, digit_groups):
        results = []
        for digits in digit_groups:
            results.append(self.simulate(digits))
        return results

    def missing_values(self):
        result = {}
        for digit in range(10):
            count = 0
            for record in reversed(self.records):
                _, n1, n2, n3, _, _ = record
                if digit in (n1, n2, n3):
                    break
                count += 1
            result[digit] = count
        return result

    def hotness_values(self, recent_n=30):
        recent = self.records[-recent_n:] if len(self.records) >= recent_n else self.records
        result = {}
        for digit in range(10):
            count = sum(1 for _, n1, n2, n3, _, _ in recent if digit in (n1, n2, n3))
            result[digit] = count
        return result

    def print_missing(self):
        missing = self.missing_values()
        print(f"\n{'=' * 52}")
        print("  遗漏值（从最新一期起连续未出现期数）")
        print("=" * 52)
        for digit in range(10):
            v = missing[digit]
            bar = "█" * min(v, 40) + "░" * max(0, 40 - min(v, 40))
            label = "★" if v == 0 else " "
            print(f"  {label} {digit}: {v:>3}期  {bar}")

    def print_hotness(self, recent_n=30):
        hotness = self.hotness_values(recent_n)
        print(f"\n{'=' * 52}")
        print(f"  热度值（近{recent_n}期出现期数）")
        print("=" * 52)
        max_h = max(hotness.values()) if hotness else 1
        sorted_digits = sorted(range(10), key=lambda d: hotness[d], reverse=True)
        for digit in sorted_digits:
            v = hotness[digit]
            bar_len = int(v / max_h * 25) if max_h > 0 else 0
            bar = "█" * bar_len
            tag = "热" if v >= max_h * 0.7 else ("温" if v >= max_h * 0.4 else "冷")
            print(f"  {digit}: {v:>2}次 [{tag}] {bar}")

    def print_simulation(self, digits):
        result = self.simulate(digits)
        n = result["n"]
        print(f"\n  ┌{'─' * 48}┐")
        print(f"  │  {result['mode']} 模拟回测{' ' * (34 - len(result['mode']))}│")
        print(f"  ├{'─' * 48}┤")
        print(f"  │  选用数字: {result['digits']}")
        print(f"  │  赔率倍数: {result['multiplier']}倍")
        print(f"  │  每期注数: {result['total_bets']}注 (组六{result['zu6_bets']} + 组三{result['zu3_bets']})")
        print(f"  │  每期投入: {result['cost_per_period']}元")
        print(f"  ├{'─' * 48}┤")
        print(f"  │  总期数:   {result['total_periods']}期")
        print(f"  │  中奖次数: {result['wins']}次 (组六:{result['zu6_wins']} 组三:{result['zu3_wins']})")
        print(f"  │  中奖率:   {result['win_rate']:.2%}")
        print(f"  ├{'─' * 48}┤")
        print(f"  │  总投入:   {result['total_investment']:>10,}元")
        print(f"  │  总回报:   {result['total_return']:>10,.1f}元")
        profit = result["net_profit"]
        sign = "+" if profit >= 0 else ""
        print(f"  │  净盈亏:   {sign}{profit:,.1f}元")
        print(f"  │  回报率:   {result['roi']:+.2f}%")
        print(f"  └{'─' * 48}┘")

    def print_multi_simulation(self, digit_groups):
        results = self.simulate_multi(digit_groups)
        print(f"\n  {'=' * 70}")
        print(f"  多组策略对比")
        print(f"  {'=' * 70}")
        header = f"  {'模式':<8} {'数字':<22} {'每期投入':>8} {'中奖率':>8} {'中奖次数':>8} {'总投入':>10} {'总回报':>10} {'净盈亏':>10}"
        print(header)
        print(f"  {'─' * 70}")
        for r in results:
            d = "".join(str(x) for x in r["digits"])
            profit = r["net_profit"]
            sign = "+" if profit >= 0 else ""
            print(
                f"  {r['mode']:<8} {d:<22} {r['cost_per_period']:>6}元 "
                f"{r['win_rate']:>7.2%} {r['wins']:>6}次 "
                f"{r['total_investment']:>9,}元 {r['total_return']:>9,.1f}元 "
                f"{sign}{profit:,.1f}元"
            )
        print(f"  {'=' * 70}")


def main():
    analyzer = StrategyAnalyzer()

    analyzer.print_missing()
    analyzer.print_hotness()

    print(f"\n  {'=' * 52}")
    print("  策略模拟器")
    print("  输入数字(空格分隔)，如: 0 1 3 5 7 8 9")
    print("  支持5码/6码/7码组选")
    print("  输入 m 进行多组对比(如: m 0135789 0245689 1356789)")
    print("  输入 q 退出")
    print(f"  {'=' * 52}")

    while True:
        user_input = input("\n请输入: ").strip()
        if user_input.lower() == "q":
            print("退出")
            break

        if user_input.lower().startswith("m "):
            parts = user_input[2:].split()
            groups = []
            valid = True
            for p in parts:
                try:
                    digits = [int(c) for c in p if c.isdigit()]
                    if len(digits) not in MULTIPLIERS or len(digits) != len(set(digits)):
                        print(f"  无效组合 '{p}'，需要5/6/7个不重复数字")
                        valid = False
                        break
                    groups.append(digits)
                except ValueError:
                    print(f"  无效输入 '{p}'")
                    valid = False
                    break
            if valid and groups:
                analyzer.print_multi_simulation(groups)
            continue

        try:
            digits = [int(x) for x in user_input.split()]
            if len(digits) != len(set(digits)):
                print("  错误: 数字不能重复")
                continue
            if any(d < 0 or d > 9 for d in digits):
                print("  错误: 数字必须在0-9之间")
                continue
            if len(digits) not in MULTIPLIERS:
                print(f"  错误: 仅支持5码/6码/7码，当前选了{len(digits)}个数字")
                continue
            analyzer.print_simulation(digits)
        except ValueError:
            print("  错误: 请输入0-9的数字，空格分隔")


if __name__ == "__main__":
    main()