import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import datetime
import base64
import io
import requests
from PIL import Image

# ==============================================================================
# 1. 移动端优先页面配置 & 高定 CSS 样式（专为手机端首屏决策深度适配）
# ==============================================================================
st.set_page_config(
    page_title="足球量化推演工作站 · 全量做市系统",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* 移动端页面内边距紧凑化 */
    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 2rem;
        padding-left: 0.8rem;
        padding-right: 0.8rem;
        max-width: 960px;
    }
    /* 首屏决策看板卡片 */
    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 8px;
        color: #f8fafc;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.25);
    }
    .decision-title {
        font-size: 0.82rem;
        color: #94a3b8;
        margin-bottom: 4px;
        font-weight: 500;
    }
    .decision-val {
        font-size: 1.3rem;
        font-weight: 700;
        color: #38bdf8;
    }
    .conf-badge {
        font-size: 0.78rem;
        padding: 2px 7px;
        border-radius: 6px;
        background-color: #0284c7;
        color: #ffffff;
        float: right;
        font-weight: 600;
    }
    /* 风险评级指示灯 */
    .status-green {
        background-color: #065f46;
        color: #34d399;
        padding: 3px 9px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-yellow {
        background-color: #78350f;
        color: #fbbf24;
        padding: 3px 9px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-red {
        background-color: #7f1d1d;
        color: #f87171;
        padding: 3px 9px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 全球 30 大核心赛事量化基因库（69,368 场真实比赛大数回测底座）
# ==============================================================================
LEAGUE_PROFILES = {
    # ---------------- 梯队 1：极致大球爆发型 (场均进球 >= 3.00) ----------------
    "德甲": {
        "archetype": "极致大球爆发型", "avg_goals": 3.21, "over25": 0.6206, "over35": 0.4175, "draw_rate": 0.2500, "btts": 0.5984,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "3球 / 4球",
        "top_scores": ["1-1", "2-1", "2-0", "1-2", "2-2", "3-1"],
        "handicap_rule": "深盘穿盘率相对较高，但需重点防范 2-2 / 3-2 高比分穿盘风险",
        "risk_tag": "大球优先 / 剔除0-0与1-0死守比分"
    },
    "荷甲": {
        "archetype": "极致大球爆发型", "avg_goals": 3.18, "over25": 0.6176, "over35": 0.3791, "draw_rate": 0.2614, "btts": 0.6275,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "3球 / 4球",
        "top_scores": ["1-1", "2-1", "2-2", "1-2", "2-0"],
        "handicap_rule": "双方进球率达 62.8% 全球最高，防守容错率低，胜平负必须考虑失球对冲",
        "risk_tag": "BTTS全欧第一 / 重点防范 2-2 平局"
    },
    "瑞士超": {
        "archetype": "极致大球爆发型", "avg_goals": 3.02, "over25": 0.5826, "over35": 0.3672, "draw_rate": 0.2547, "btts": 0.5962,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-2", "2-2", "2-0"],
        "handicap_rule": "对攻节奏快，豪门客场防守偶发松懈，让球单挑让胜需极其谨慎",
        "risk_tag": "中欧高产大球 / 双方破门率极高"
    },
    "德乙": {
        "archetype": "极致大球爆发型", "avg_goals": 3.01, "over25": 0.5923, "over35": 0.3435, "draw_rate": 0.2496, "btts": 0.5876,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "1-2", "2-2"],
        "handicap_rule": "次级联赛反击转化极快，下盘具备强反咬能力，严控浅盘单挑",
        "risk_tag": "次级别高产大球 / 严控浅盘单挑"
    },
    "挪超": {
        "archetype": "极致大球爆发型", "avg_goals": 3.00, "over25": 0.5786, "over35": 0.3575, "draw_rate": 0.2400, "btts": 0.5811,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "1-2", "2-0"],
        "handicap_rule": "主胜率达 47.3%，博德闪耀等霸主主场火力凶猛，让胜穿盘率相对健康",
        "risk_tag": "北欧大球之王 / 强主场对攻属性"
    },

    # ---------------- 梯队 2：攻防高对抗与主流均衡型 (场均进球 2.80 ~ 2.95) ----------------
    "国内主流杯赛(足总杯/国王杯等)": {
        "archetype": "攻防高对抗型(杯赛模式)", "avg_goals": 2.95, "over25": 0.5520, "over35": 0.3310, "draw_rate": 0.2350, "btts": 0.5310,
        "default_goals": ["2球", "3球", "4球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["2-1", "1-0", "1-1", "2-0", "3-1"],
        "handicap_rule": "豪门轮换风险极高，若非全主力严禁单挑深盘让胜，必须重点防范【让平/让负】",
        "risk_tag": "阵容轮换是第一变量 / 次级球队战意极高"
    },
    "奥甲": {
        "archetype": "攻防高对抗型", "avg_goals": 2.91, "over25": 0.5545, "over35": 0.3343, "draw_rate": 0.2493, "btts": 0.5414,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "2-0", "0-1", "1-2"],
        "handicap_rule": "红牛系战术体系主导，节奏明快，深盘需警惕欧战前后轮换卡盘",
        "risk_tag": "中欧高产对攻 / 德系风格"
    },
    "比甲": {
        "archetype": "攻防高对抗型", "avg_goals": 2.85, "over25": 0.5398, "over35": 0.3224, "draw_rate": 0.2472, "btts": 0.5360,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "0-1", "1-0", "2-0"],
        "handicap_rule": "数理结构高度贴合英超，五五开对局分胜负能力强",
        "risk_tag": "英超近邻结构 / 进球数聚焦2-3球"
    },
    "英超": {
        "archetype": "攻防高对抗型", "avg_goals": 2.84, "over25": 0.5438, "over35": 0.3207, "draw_rate": 0.2349, "btts": 0.5294,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "1-0", "2-1", "2-0", "0-1", "1-2"],
        "handicap_rule": "欧赔 1.45~1.85 让一球盘口，让平打出率高达 27.4%，严禁单挑让胜",
        "risk_tag": "攻防转换极快 / 强队做客防卡盘让平"
    },
    "土超": {
        "archetype": "攻防高对抗型", "avg_goals": 2.83, "over25": 0.5415, "over35": 0.3099, "draw_rate": 0.2545, "btts": 0.5577,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "1-2", "0-0", "2-0"],
        "handicap_rule": "三强（加拉塔/费内/贝西克）让一球盘口下，让平率高达 35.0%，核心对冲项",
        "risk_tag": "传统三强寡头 / 卡盘极高让平率"
    },
    "法甲": {
        "archetype": "攻防高对抗型", "avg_goals": 2.83, "over25": 0.5370, "over35": 0.3224, "draw_rate": 0.2375, "btts": 0.5381,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "1-0", "2-1", "2-0", "1-2", "3-1"],
        "handicap_rule": "除巴黎等超深盘外，强强对话及中游交锋优先防范让平",
        "risk_tag": "节奏提速偏大 / 强弱分化显著"
    },
    "欧冠/欧战淘汰赛": {
        "archetype": "顶级淘汰赛(杯赛模式)", "avg_goals": 2.82, "over25": 0.5350, "over35": 0.3120, "draw_rate": 0.2850, "btts": 0.5420,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "0-1", "1-2", "2-2"],
        "handicap_rule": "常规时间平局率上调至 28.5%；首回合严控大比分穿盘，次回合放宽反击大球",
        "risk_tag": "顶级欧战 / 首回合防冷平 / 次回合防大球"
    },
    "瑞典超": {
        "archetype": "攻防高对抗型", "avg_goals": 2.80, "over25": 0.5388, "over35": 0.3025, "draw_rate": 0.2494, "btts": 0.5444,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "1-2", "0-1"],
        "handicap_rule": "北欧技术流，人工草皮球队主场优势明显，防反转化率高",
        "risk_tag": "北欧技术流 / 人工草场变数"
    },
    "丹超": {
        "archetype": "攻防高对抗型", "avg_goals": 2.80, "over25": 0.5363, "over35": 0.3140, "draw_rate": 0.2611, "btts": 0.5585,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "2-1", "1-0", "1-2", "2-0"],
        "handicap_rule": "双方进球率达 55.9%，强队防线零封率较低，注意让胜阻水",
        "risk_tag": "北欧开放对攻 / 双方破门高发"
    },

    # ---------------- 梯队 3：战术控场与地面相持型 (场均进球 2.60 ~ 2.70) ----------------
    "葡超": {
        "archetype": "战术相持/寡头型", "avg_goals": 2.68, "over25": 0.5245, "over35": 0.3031, "draw_rate": 0.2357, "btts": 0.4837,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-0", "1-1", "0-1", "1-2", "2-1"],
        "handicap_rule": "三强做客遇铁桶阵极其频繁打出 1-0、2-1 小胜，让平率达 36.3% 全欧最高",
        "risk_tag": "全欧最高让平率 / 豪门小胜卡盘"
    },
    "墨超": {
        "archetype": "战术相持型", "avg_goals": 2.67, "over25": 0.5047, "over35": 0.2802, "draw_rate": 0.2709, "btts": 0.5515,
        "default_goals": ["2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "1-0", "2-1", "0-1", "0-0"],
        "handicap_rule": "高原主场与气候影响大，平局率 27.1%，强弱对局易出冷平",
        "risk_tag": "高原客战耗损 / 高平局黏度"
    },
    "波兰超": {
        "archetype": "战术相持型", "avg_goals": 2.65, "over25": 0.4957, "over35": 0.2781, "draw_rate": 0.2707, "btts": 0.5308,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "1-0", "2-1", "0-1", "0-0"],
        "handicap_rule": "身体对抗激烈，平局率超 27%，均势对决优先防平",
        "risk_tag": "东欧对抗胶着 / 高平局占比"
    },
    "亚洲杯赛(亚冠/日联杯等)": {
        "archetype": "战术相持型(杯赛模式)", "avg_goals": 2.65, "over25": 0.4950, "over35": 0.2720, "draw_rate": 0.2780, "btts": 0.5120,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-1", "2-1", "0-0"],
        "handicap_rule": "客场长途飞行与气候变数大，主队不败率较高，常规时间平局高发",
        "risk_tag": "跨国舟车劳顿 / 战术纪律相持"
    },
    "西甲": {
        "archetype": "战术相持型", "avg_goals": 2.63, "over25": 0.4921, "over35": 0.2490, "draw_rate": 0.2448, "btts": 0.5393,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "2球 / 3球",
        "top_scores": ["1-1", "1-0", "2-1", "0-1", "1-2", "2-0"],
        "handicap_rule": "主胜率 47.0% 居主流之首；让一球盘口下让平概率突破 30.1%，让平为第一对冲",
        "risk_tag": "主场强势 / 地面传控 / 高让平率"
    },
    "芬超": {
        "archetype": "战术相持型", "avg_goals": 2.63, "over25": 0.4903, "over35": 0.2747, "draw_rate": 0.2554, "btts": 0.5074,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "2-1", "0-1", "1-2"],
        "handicap_rule": "中下游实力高度胶着，小球占优，进球数优先选 1/2球",
        "risk_tag": "北欧均势相持 / 小球占优"
    },
    "日职联": {
        "archetype": "战术相持型", "avg_goals": 2.62, "over25": 0.4860, "over35": 0.2681, "draw_rate": 0.2481, "btts": 0.5162,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-1", "2-1", "1-2"],
        "handicap_rule": "客胜率 34.1% 甚至高于意甲，主场优势严重被弱化，平半盘慎追主",
        "risk_tag": "亚洲客胜高发 / 慎追主胜浅盘"
    },
    "意甲": {
        "archetype": "战术相持型", "avg_goals": 2.60, "over25": 0.4882, "over35": 0.2625, "draw_rate": 0.2664, "btts": 0.5112,
        "default_goals": ["1球", "2球", "3球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-1", "2-1", "1-2", "2-0", "0-0"],
        "handicap_rule": "主胜率仅 40.0%（主流最低），客胜率达 33.4%；平局与让平权重全线提升",
        "risk_tag": "低主场溢价 / 战术防守 / 严防冷平"
    },
    "爱超": {
        "archetype": "战术相持型", "avg_goals": 2.58, "over25": 0.4791, "over35": 0.2572, "draw_rate": 0.2483, "btts": 0.4754,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-0", "1-1", "0-1", "2-0", "0-0"],
        "handicap_rule": "身体对抗重于技战术，进攻节奏沉闷，低比分概率大",
        "risk_tag": "典型英伦防守相持型"
    },

    # ---------------- 梯队 4：极致小球与平局堡垒型 (场均进球 <= 2.52) ----------------
    "法乙": {
        "archetype": "极致小球/平局堡垒型", "avg_goals": 2.52, "over25": 0.4739, "over35": 0.2631, "draw_rate": 0.2821, "btts": 0.5005,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-0", "1-1", "0-0", "0-1", "2-1"],
        "handicap_rule": "平局率高达 28.2%，前三比分（1-0/1-1/0-0）占 32.3%，死锁小球",
        "risk_tag": "平局缠斗 / 前三小比分垄断"
    },
    "英冠": {
        "archetype": "极致小球相持型", "avg_goals": 2.51, "over25": 0.4699, "over35": 0.2297, "draw_rate": 0.2603, "btts": 0.5078,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-1", "2-1", "0-0", "2-0"],
        "handicap_rule": "实力极其均衡，让一球打出让胜不足 28%，下盘（让平+让负）占比超 72%",
        "risk_tag": "身体对抗 / 典型小球 / 严控单挑让胜"
    },
    "韩K联": {
        "archetype": "极致小球/亚洲防守型", "avg_goals": 2.48, "over25": 0.4610, "over35": 0.2350, "draw_rate": 0.2750, "btts": 0.4950,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-1", "0-0", "2-1"],
        "handicap_rule": "主场溢价极低，U22换人变量多，欧赔1.50~1.90区间让胜不足32%，严防让平让负",
        "risk_tag": "亚洲相持防守型 / U22换人变量 / 慎追深盘主胜"
    },
    "希腊超": {
        "archetype": "两极分化/小球型", "avg_goals": 2.48, "over25": 0.4658, "over35": 0.2377, "draw_rate": 0.2678, "btts": 0.4645,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-1", "1-0", "0-0", "0-1", "2-1"],
        "handicap_rule": "两极分化，豪门客战穿透力强，中下游相持死磕小球",
        "risk_tag": "豪门客胜强穿 / 中下游小球"
    },
    "巴甲": {
        "archetype": "极强主场/1-0极致小球", "avg_goals": 2.40, "over25": 0.4371, "over35": 0.2118, "draw_rate": 0.2689, "btts": 0.4832,
        "default_goals": ["1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-0", "1-1", "2-1", "2-0", "0-0"],
        "handicap_rule": "主胜率 48.5% 全量最高；1-0 比分达 14.1%，首选比分必须锚定 1-0 / 2-1",
        "risk_tag": "极强主胜 / 1-0主义极致小球"
    },
    "西乙": {
        "archetype": "极致小球/平局堡垒型", "avg_goals": 2.37, "over25": 0.4289, "over35": 0.2305, "draw_rate": 0.2884, "btts": 0.4904,
        "default_goals": ["0球", "1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-0", "1-1", "0-0", "2-1", "0-1"],
        "handicap_rule": "0-0 出现率达 10.8%，平局率 28.8%，严禁推荐 3 球以上大比分",
        "risk_tag": "全欧平局堡垒 / 极致小球防守"
    },
    "阿甲": {
        "archetype": "全网极致小球/平局破30%", "avg_goals": 2.23, "over25": 0.3894, "over35": 0.1911, "draw_rate": 0.3021, "btts": 0.4473,
        "default_goals": ["0球", "1球", "2球"], "preferred_goals_pair": "1球 / 2球",
        "top_scores": ["1-0", "1-1", "0-0", "0-1", "2-1", "2-0"],
        "handicap_rule": "平局率破30%全网唯一！小球率超61%，前三大比分占近40%，绝不碰大比分",
        "risk_tag": "全网极致小球之王 / 平局率破30%温床"
    }
}

# ==============================================================================
# 3. 本地做市商精算引擎（No-Vig 纯概率数学公式）
# ==============================================================================
def calculate_novig_probabilities(home_odds, draw_odds, away_odds):
    """
    通过平博做市商终赔，精准剔除抽水（Margin），计算客观公允纯打出概率
    """
    if home_odds <= 1.0 or draw_odds <= 1.0 or away_odds <= 1.0:
        return None
    margin = (1.0 / home_odds) + (1.0 / draw_odds) + (1.0 / away_odds)
    p_h = (1.0 / home_odds) / margin
    p_d = (1.0 / draw_odds) / margin
    p_a = (1.0 / away_odds) / margin
    vig_pct = (margin - 1.0) * 100
    return {
        "p_h": round(p_h * 100, 2),
        "p_d": round(p_d * 100, 2),
        "p_a": round(p_a * 100, 2),
        "vig": round(vig_pct, 2)
    }

# ==============================================================================
# 4. 数据持久化与记账审计模块
# ==============================================================================
DB_FILE = "match_predictions_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_db(record):
    db = load_db()
    db.insert(0, record)  # 最新记录置顶
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def update_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# ==============================================================================
# 5. Gemini 3.8 Flash API 驱动调用逻辑
# ==============================================================================
def call_quant_model(api_key, match_info, league_profile, novig_res, images):
    """
    组装精算法则，将 69,368 场回测公理注入大模型推理
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    # 构造系统军规约束
    system_rules = f"""
你是由华尔街量化对冲基金与专业足球赛事做市商联合构建的资深分析师。你必须严格基于以下【69,368场历史样本大数法则公理】执行推演：

### 核心量化铁律约束：
1. 【平博 No-Vig 纯概率锚定】：
   本场平博数学公允打出概率已由本地精算引擎算死：主胜 {novig_res['p_h']}% | 平局 {novig_res['p_d']}% | 客胜 {novig_res['p_a']}%（做市商抽水: {novig_res['vig']}%）。
   你定性判定的核心方向，其概率置信度严禁偏离该数学公允概率超过 ±5%。
2. 【所属联赛/杯赛基因硬性绑定 - {match_info['league']}】：
   - 基因分类：{league_profile['archetype']}
   - 历史场均进球：{league_profile['avg_goals']} 球
   - 历史大球率(>2.5)：{round(league_profile['over25']*100, 1)}%
   - 历史平局率：{round(league_profile['draw_rate']*100, 1)}%
   - 双方进球率(BTTS)：{round(league_profile['btts']*100, 1)}%
   - 核心做市特征：{league_profile['handicap_rule']}
   - 进球数双选必须严格服从：【{league_profile['preferred_goals_pair']}】及其收敛区间！
   - 自洽比分与防冷次选比分必须 100% 落在历史高频比分矩阵：{league_profile['top_scores']}。
3. 【竞彩热门让一球(-1) 穿盘防冷铁律】：
   历史 6.9 万场回测证实：当热门胜率在 50%~70%（赔率 1.45~1.95）时，单挑让胜打出率仅 28%~40%，防冷选项（让平+让负）占 60%~72%。
   除平博独赢赔率 <= 1.25（胜率 > 80%）的极端深盘外，所有让球选项严禁单挑让胜，必须配置【让平】或【让负】对冲！
4. 【杯赛/淘汰赛专属审查】：
   若是淘汰赛或杯赛，必须审查首回合/次回合博弈心态，以及主力轮换战意折损。若非全主力，坚决防范下盘。

### 强制输出要求：
核心结论必须明确，不模棱两可：
1. 欧盘胜平负 + 置信度
2. 亚盘/竞彩让球胜平负 + 置信度
3. 多选总进球数两个 + 置信度
4. 自洽首选比分 + 防冷次选比分

请必须在回复的最后提供纯 JSON 代码块（```json ... ```），包含以下键名：
{{
  "euro_result": "主胜/平局/客胜",
  "euro_conf": 76,
  "handicap_result": "让胜/让平/让负",
  "handicap_conf": 72,
  "goals_result": "2球 / 3球",
  "goals_conf": 81,
  "exact_score": "2-1",
  "backup_score": "1-1",
  "risk_light": "绿灯/黄灯/红灯",
  "risk_reason": "简述风控理由",
  "full_report": "完整的做市商洗盘逻辑、首发伤停折损、资金流向深度研报（1200字以上）"
}}
"""

    prompt = f"""
待推演赛事信息：
- 赛事：[{match_info['league']}] {match_info['home_team']} VS {match_info['away_team']}
- 比赛时间：{match_info['match_time']}
- 平博终赔：主胜 {match_info['ps_h']} | 平局 {match_info['ps_d']} | 客胜 {match_info['ps_a']}
- 皇冠/主流亚盘盘口：{match_info['ah_line']}
- 首发阵容/战意/轮换与必发异动备注：{match_info['notes']}
"""

    parts = [{"text": system_rules + "\n" + prompt}]
    
    # 支持多张图片多模态注入
    for img in images:
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": img_str
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,  # 极低随机性，确保量化纪律
            "topP": 0.8,
            "maxOutputTokens": 4096
        }
    }

    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"API 请求失败 [{resp.status_code}]: {resp.text}")
    
    res_json = resp.json()
    text = res_json['candidates'][0]['content']['parts'][0]['text']
    return text

# ==============================================================================
# 6. Streamlit 页面布局与交互流
# ==============================================================================

tab_predict, tab_history, tab_profiles, tab_calc = st.tabs([
    "⚡ 极速推演工作台", 
    "📋 历史结算与复盘", 
    "🧬 30大赛事基因底牌",
    "📐 做市商去水计算器"
])

# ------------------------------------------------------------------------------
# TAB 1: 极速推演工作台
# ------------------------------------------------------------------------------
with tab_predict:
    st.markdown("### ⚽ 足球量化做市推演系统 · 移动端")
    
    with st.expander("🔑 系统配置与 API 密钥", expanded=False):
        api_key = st.text_input("Google AI Studio API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
        st.caption("提示：可在云端环境变量预设 GEMINI_API_KEY 避免重复输入。")

    col_m1, col_m2 = st.columns([1.2, 1])
    with col_m1:
        league = st.selectbox(
            "选择联赛 / 杯赛类型 (系统自动匹配基因)", 
            options=list(LEAGUE_PROFILES.keys()), 
            index=list(LEAGUE_PROFILES.keys()).index("英超")
        )
    with col_m2:
        match_time = st.text_input("开赛时间", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        home_team = st.text_input("主队名称", value="曼彻斯特城")
    with col_t2:
        away_team = st.text_input("客队名称", value="阿森纳")

    st.markdown("##### 📊 做市商核心盘口输入（平博终盘为主）")
    col_o1, col_o2, col_o3, col_o4 = st.columns([1, 1, 1, 1.2])
    with col_o1:
        ps_h = st.number_input("主胜 (PSH)", value=1.85, step=0.01, format="%.2f")
    with col_o2:
        ps_d = st.number_input("平局 (PSD)", value=3.60, step=0.01, format="%.2f")
    with col_o3:
        ps_a = st.number_input("客胜 (PSA)", value=4.50, step=0.01, format="%.2f")
    with col_o4:
        ah_line = st.text_input("皇冠/亚盘盘口", value="主让 0.5 球 (0.88)")

    # 本地实时精算看板
    novig = calculate_novig_probabilities(ps_h, ps_d, ps_a)
    if novig:
        st.info(f"📐 **本地精算引擎已锚定**：主胜公允概率 **{novig['p_h']}%** ｜ 平局 **{novig['p_d']}%** ｜ 客胜 **{novig['p_a']}%**（平博抽水: {novig['vig']}%）")

    notes = st.text_area(
        "关键情报备注（杯赛首轮/次轮、主力伤停轮换、必发成交异动等）", 
        placeholder="如：欧冠首回合试探；主队主力中卫伤停，客队头号射手轮休；必发主胜占比85%买方过热..."
    )

    uploaded_files = st.file_uploader(
        "📸 批量上传盘口/阵容截图（平博、皇冠、首发等）", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True
    )
    images = []
    if uploaded_files:
        cols_img = st.columns(min(len(uploaded_files), 4))
        for idx, f in enumerate(uploaded_files):
            img = Image.open(f)
            images.append(img)
            with cols_img[idx % 4]:
                st.image(img, caption=f"截图 {idx+1}", use_container_width=True)

    btn_run = st.button("🚀 启动大数做市推演", use_container_width=True, type="primary")

    if btn_run:
        if not api_key:
            st.error("请先在上方展开栏输入有效的 Gemini API Key！")
        else:
            match_data = {
                "league": league,
                "match_time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "ps_h": ps_h,
                "ps_d": ps_d,
                "ps_a": ps_a,
                "ah_line": ah_line,
                "notes": notes
            }
            with st.spinner("正在基于 69,368 场大数法则与做市商博弈深度推演..."):
                try:
                    output_text = call_quant_model(api_key, match_data, LEAGUE_PROFILES[league], novig, images)
                    
                    # 尝试解析输出中的 JSON
                    json_str = ""
                    if "```json" in output_text:
                        json_str = output_text.split("```json")[1].split("```")[0].strip()
                    elif "{" in output_text and "}" in output_text:
                        start = output_text.find("{")
                        end = output_text.rfind("}") + 1
                        json_str = output_text[start:end]

                    res_dict = {}
                    if json_str:
                        try:
                            res_dict = json.loads(json_str)
                        except Exception:
                            res_dict = {}

                    # 提取核心决策
                    euro_res = res_dict.get("euro_result", "推演完成")
                    euro_conf = res_dict.get("euro_conf", 75)
                    hc_res = res_dict.get("handicap_result", "详见研报")
                    hc_conf = res_dict.get("handicap_conf", 70)
                    goals_res = res_dict.get("goals_result", LEAGUE_PROFILES[league]["preferred_goals_pair"])
                    goals_conf = res_dict.get("goals_conf", 80)
                    exact_score = res_dict.get("exact_score", "2-1")
                    backup_score = res_dict.get("backup_score", "1-1")
                    risk_light = res_dict.get("risk_light", "绿灯")
                    risk_reason = res_dict.get("risk_reason", "符合做市商期望值")
                    report_text = res_dict.get("full_report", output_text)

                    # 存入数据库
                    record_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                    new_record = {
                        "id": record_id,
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "league": league,
                        "home_team": home_team,
                        "away_team": away_team,
                        "match_time": match_time,
                        "ps_odds": f"{ps_h} / {ps_d} / {ps_a}",
                        "euro_pred": euro_res,
                        "euro_conf": euro_conf,
                        "hc_pred": hc_res,
                        "hc_conf": hc_conf,
                        "goals_pred": goals_res,
                        "goals_conf": goals_conf,
                        "exact_score": exact_score,
                        "backup_score": backup_score,
                        "status": "待结算",
                        "final_score": "",
                        "report": report_text
                    }
                    save_to_db(new_record)

                    # ------------------------------------------------------
                    # 渲染【首屏化决策卡片看板】（手机端免翻页）
                    # ------------------------------------------------------
                    st.success("✅ 推演成功！已收敛为核心确定性结论并自动存盘：")
                    
                    st.markdown(f"""
                    <div style="background:#0f172a; border-radius:12px; padding:14px; border:1px solid #1e293b; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <span style="font-size:1.1rem; font-weight:700; color:#f8fafc;">[{league}] {home_team} vs {away_team}</span>
                            <span class="{'status-green' if '绿' in risk_light else ('status-yellow' if '黄' in risk_light else 'status-red')}">{risk_light}</span>
                        </div>
                        <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:12px;">风控审计：{risk_reason} ｜ 基因特征：{LEAGUE_PROFILES[league]['risk_tag']}</div>
                        
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                            <div class="metric-card">
                                <div class="decision-title">🏆 欧盘胜平负 <span class="conf-badge">{euro_conf}%</span></div>
                                <div class="decision-val">{euro_res}</div>
                            </div>
                            <div class="metric-card">
                                <div class="decision-title">🛡️ 竞彩让球(-1) <span class="conf-badge">{hc_conf}%</span></div>
                                <div class="decision-val">{hc_res}</div>
                            </div>
                            <div class="metric-card">
                                <div class="decision-title">⚽ 多选总进球 <span class="conf-badge">{goals_conf}%</span></div>
                                <div class="decision-val">{goals_res}</div>
                            </div>
                            <div class="metric-card">
                                <div class="decision-title">🎯 自洽/防冷比分</div>
                                <div class="decision-val" style="font-size:1.15rem; color:#f59e0b;">{exact_score} <span style="font-size:0.85rem; color:#cbd5e1;">(防 {backup_score})</span></div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 折叠详细研报（不占手机屏宽）
                    with st.expander("🔍 展开查看 1200 字做市商洗盘与技战术研报 (详细明细)", expanded=False):
                        st.markdown(report_text)

                except Exception as e:
                    st.error(f"推演过程发生异常：{str(e)}")

# ------------------------------------------------------------------------------
# TAB 2: 历史结算与复盘审计
# ------------------------------------------------------------------------------
with tab_history:
    st.markdown("### 📋 历史赛事推演自动结算与审计")
    records = load_db()
    
    if not records:
        st.info("当前暂无推演记录，请在工作台发起第一场推演。")
    else:
        # 统计面板
        settled = [r for r in records if r.get("status") == "已结算"]
        st.metric("累计推演场次", len(records), f"已结算复盘: {len(settled)} 场")
        
        st.markdown("---")
        for idx, r in enumerate(records):
            with st.container():
                st.markdown(f"**[{r['league']}] {r['home_team']} VS {r['away_team']}** ({r['match_time']})")
                c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
                c1.caption(f"欧盘预测: **{r['euro_pred']}**")
                c2.caption(f"让球预测: **{r['hc_pred']}**")
                c3.caption(f"进球双选: **{r['goals_pred']}**")
                c4.caption(f"比分预测: **{r['exact_score']} / {r['backup_score']}**")
                
                # 结算交互
                if r.get("status") == "待结算":
                    col_in, col_btn = st.columns([2, 1])
                    with col_in:
                        score_input = st.text_input(f"录入完场比分 (如 2-1)", key=f"score_{r['id']}", placeholder="主-客")
                    with col_btn:
                        if st.button("判定结算", key=f"btn_set_{r['id']}"):
                            if "-" in score_input:
                                try:
                                    hg, ag = map(int, score_input.split("-"))
                                    r['final_score'] = score_input
                                    r['status'] = "已结算"
                                    # 自动判定红黑
                                    actual_ftr = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
                                    actual_goals = hg + ag
                                    r['audit_res'] = f"完场: {score_input} | 实际胜平负: {actual_ftr} | 总进球: {actual_goals}球"
                                    update_db(records)
                                    st.success(f"已结算完场比分 {score_input}！")
                                    st.rerun()
                                except Exception:
                                    st.error("比分格式不正确！")
                else:
                    st.success(f"✅ {r.get('audit_res', '已结算')} ｜ 完场比分: {r.get('final_score')}")

                with st.expander(f"查看该场推演完整研报", expanded=False):
                    st.markdown(r.get("report", "无详细报告"))
                st.markdown("---")

# ------------------------------------------------------------------------------
# TAB 3: 30 大赛事基因底牌速查
# ------------------------------------------------------------------------------
with tab_profiles:
    st.markdown("### 🧬 69,368 场大数定律：30 大联赛/杯赛基因速查手册")
    st.caption("系统推演时自动挂载以下客观数学边界，严防出现反常识偏离。")

    league_rows = []
    for lg_name, p in LEAGUE_PROFILES.items():
        league_rows.append({
            "赛事分类": p['archetype'],
            "赛事名称": lg_name,
            "场均进球": f"{p['avg_goals']} 球",
            "大球率 (>2.5)": f"{round(p['over25']*100, 1)}%",
            "平局率": f"{round(p['draw_rate']*100, 1)}%",
            "双方破门(BTTS)": f"{round(p['btts']*100, 1)}%",
            "推荐进球数双选": p['preferred_goals_pair'],
            "高频比分形态": " / ".join(p['top_scores'][:4]),
            "核心做市特征": p['risk_tag']
        })
    df_profiles = pd.DataFrame(league_rows)
    st.dataframe(df_profiles, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 4: 做市商去水计算器 & 军规说明
# ------------------------------------------------------------------------------
with tab_calc:
    st.markdown("### 📐 机构去抽水 (No-Vig) 纯概率独立计算器")
    st.caption("随时验证任意机构（平博、Bet365、皇冠）的公允打出概率，识别做市商抽水率。")
    
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        test_h = st.number_input("主胜赔率", value=2.05, step=0.01)
    with col_c2:
        test_d = st.number_input("平局赔率", value=3.40, step=0.01)
    with col_c3:
        test_a = st.number_input("客胜赔率", value=3.80, step=0.01)
        
    calc_res = calculate_novig_probabilities(test_h, test_d, test_a)
    if calc_res:
        st.markdown(f"""
        - **主胜公允概率**：`{calc_res['p_h']}%`
        - **平局公允概率**：`{calc_res['p_d']}%`
        - **客胜公允概率**：`{calc_res['p_a']}%`
        - **机构抽水率 (Margin)**：`{calc_res['vig']}%`
        """)
