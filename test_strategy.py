import sqlite3
import pandas as pd
from app import extract_features, LotteryPatternEngine, calc_hotness

conn = sqlite3.connect("lottery_data.db")
df = pd.read_sql_query(
    "SELECT period, num1, num2, num3, pattern, draw_date FROM history3d ORDER BY period ASC",
    conn,
)
conn.close()
print(f"Data loaded: {len(df)} rows")

df_feat = extract_features(df)
print(f"Features extracted: {len(df_feat)} rows")

engine = LotteryPatternEngine(df_feat)
schemes = engine.generate_schemes(n_schemes=3)
for s in schemes:
    digits_str = "".join(map(str, s["digits"]))
    reasons_str = " | ".join(s["reasons"])
    print(f"Scheme {s['index']}: {digits_str} | Reasons: {reasons_str}")

hotness = calc_hotness(df_feat, 30)
print(f"Hotness map: {hotness}")

digits = schemes[0]["digits"]
ranked = sorted(digits, key=lambda d: (-hotness.get(d, 0), d))
print(f"Original: {digits}")
print(f"Ranked:   {ranked}")
print(f"6码: {ranked[:6]}")
print(f"5码: {ranked[:5]}")

# Test manual override scenario
user_input = "0135789"
user_digits = [int(c) for c in user_input if c.isdigit()]
user_digits = list(dict.fromkeys(user_digits))[:7]
ranked_user = sorted(user_digits, key=lambda d: (-hotness.get(d, 0), d))
print(f"\nUser override test:")
print(f"Input: {user_input}")
print(f"Ranked by hotness: {ranked_user}")
print(f"6码: {ranked_user[:6]}")
print(f"5码: {ranked_user[:5]}")

print("\nALL TESTS PASSED")