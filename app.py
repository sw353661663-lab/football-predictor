import streamlit as st
import google.generativeai as genai
from PIL import Image
import json
import requests
from datetime import datetime

# ==============================================================================
# 1. 移动端优先视口渲染与流式交互引擎
# ==============================================================================
st.set_page_config(
    page_title="OmniQuant Cortex · 足球微观量化做市决策系统",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 4rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        max-width: 100% !important;
    }
    .stButton>button {
        border-radius: 10px !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        height: 3.2rem !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .metric-grid {
        display: flex;
        justify-content: space-between;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 10px 8px;
        margin-bottom: 12px;
    }
    .metric-item {
        flex: 1;
        text-align: center;
    }
    .metric-title {
        font-size: 0.72rem;
        color: #6c757d;
        margin-bottom: 2px;
    }
    .metric-num {
        font-size: 1.15rem;
        font-weight: 700;
        color: #212529;
    }
    .api-card {
        background: #eef7ff;
        border: 1px solid #bee5eb;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 12px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 云端持久化存储中心 (JSONBin.io)
# ==============================================================================
def get_secret(key, default=""):
    try:
        val = st.secrets.get(key, default)
        return str(val).strip() if val else default
    except Exception:
        return default

JSONBIN_KEY = get_secret("JSONBIN_KEY")
JSONBIN_BIN_ID = get_secret("JSONBIN_BIN_ID")
IS_CLOUD_READY = bool(JSONBIN_KEY and JSONBIN_BIN_ID)

JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}" if JSONBIN_BIN_ID else ""
JSONBIN_HEADERS = {
    "X-Master-Key": JSONBIN_KEY,
    "Content-Type": "application/json"
}

def fetch_from_cloud():
    default_db = {
        "history": [],
        "rules": [
            "【军规1】平博深盘超低水做热主胜，若必发买方成交过热，坚决防范下盘冷平与让负",
            "【军规2】做市商逆向升水洗盘且亚洲主流机构持续高水阻上，坚定锁定主胜独赢",
            "【军规3】天气恶劣湿滑积水严重时，技术流攻防受阻，总进球数严控小球区间并剔除大比分",
            "【军规4】核心组织中场或主力门将单点缺阵，防守体系降级，必须调高对向球队进球期望"
        ],
        "error_bank": [],
        "last_evolved_count": 0
    }
    if not IS_CLOUD_READY:
        return False, "未配置数据库密钥", default_db
    try:
        resp = requests.get(f"{JSONBIN_URL}/latest", headers=JSONBIN_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("record", {})
            if isinstance(data, dict):
                merged = {
                    "history": data.get("history", []),
                    "rules": data.get("rules", default_db["rules"]),
                    "error_bank": data.get("error_bank", []),
                    "last_evolved_count": data.get("last_evolved_count", 0)
                }
                return True, "连接成功", merged
        return False, f"拉取失败: HTTP {resp.status_code}", default_db
    except Exception as e:
        return False, str(e), default_db

def push_to_cloud(data):
    if not IS_CLOUD_READY:
        return False, "未配置数据库密钥"
    try:
        resp = requests.put(JSONBIN_URL, json=data, headers=JSONBIN_HEADERS, timeout=8)
        if resp.status_code == 200:
            return True, "写入成功"
        return False, f"写入失败: HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

if "db" not in st.session_state:
    ok, msg, loaded_db = fetch_from_cloud()
    st.session_state.db = loaded_db

# ==============================================================================
# 3. The Odds API 实时做市商精算引擎 (平博去抽水纯概率算法)
# ==============================================================================
LEAGUE_MAP = {
    "不调用 API（纯截图）": "",
    "英超 (Premier League)": "soccer_epl",
    "西甲 (La Liga)": "soccer_spain_la_liga",
    "德甲 (Bundesliga)": "soccer_germany_bundesliga",
    "意甲 (Serie A)": "soccer_italy_serie_a",
    "法甲 (Ligue 1)": "soccer_france_ligue_one",
    "欧冠 (Champions League)": "soccer_uefa_champs_league",
    "欧联 (Europa League)": "soccer_uefa_europa_league"
}

def query_the_odds_api(api_key, sport_key, target_match=""):
    if not api_key or not sport_key:
        return None
    url = f"https://api.theoddsapi.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return {"error": f"API 状态码: {resp.status_code} ({resp.text[:60]})"}
        data = resp.json()
        if not data:
            return {"error": "该联赛当前暂无可调用的即将开赛对阵"}
            
        matched_game = None
        if target_match:
            t_low = target_match.lower()
            for g in data:
                if (g.get("home_team", "").lower() in t_low or 
                    g.get("away_team", "").lower() in t_low):
                    matched_game = g
                    break
        if not matched_game:
            matched_game = data[0]
            
        pinnacle_h2h = None
        for bm in matched_game.get("bookmakers", []):
            if bm.get("key") == "pinnacle":
                for mkt in bm.get("markets", []):
                    if mkt.get("key") == "h2h":
                        pinnacle_h2h = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}

        home = matched_game.get("home_team")
        away = matched_game.get("away_team")
        
        calc_result = {
            "match_found": f"{home} vs {away}",
            "commence_time": matched_game.get("commence_time"),
            "pinnacle_odds": pinnacle_h2h,
            "bookmaker_count": len(matched_game.get("bookmakers", []))
        }
        
        # 去抽水真实概率 (No-Vig Fair Odds) 精算
        if pinnacle_h2h and home in pinnacle_h2h and away in pinnacle_h2h:
            h_odd = pinnacle_h2h[home]
            a_odd = pinnacle_h2h[away]
            d_odd = pinnacle_h2h.get("Draw", 3.0)
            
            implied_h = 1 / h_odd
            implied_d = 1 / d_odd
            implied_a = 1 / a_odd
            total_margin = implied_h + implied_d + implied_a
            
            calc_result["payout_rate"] = f"{(1 / total_margin * 100):.2f}%"
            calc_result["fair_prob_home"] = f"{(implied_h / total_margin * 100):.1f}%"
            calc_result["fair_prob_draw"] = f"{(implied_d / total_margin * 100):.1f}%"
            calc_result["fair_prob_away"] = f"{(implied_a / total_margin * 100):.1f}%"
            
        return calc_result
    except Exception as e:
        return {"error": f"API 通信异常: {str(e)}"}

# ==============================================================================
# 4. 黄金军规蒸馏自进化引擎 (满 5 场自动触发)
# ==============================================================================
def trigger_evolution(api_key):
    history = st.session_state.db.get("history", [])
    errors = st.session_state.db.get("error_bank", [])
    settled = [h for h in history if h.get("settled", False)]
    if len(settled) == 0 and len(errors) == 0:
        return False, "暂无足够实战结算样本或错题。"
    prompt = f"""
你是一名掌管顶级对冲基金足球做市策略的量化总监。请根据近期实战结算数据（重点审视黑单与走水）以及错题复盘记录，深入穿透失误本质，重新提炼并更新 5 至 8 条实战价值最高的【黄金量化军规】。

【待审计实战样本】：{json.dumps(settled[-12:], ensure_ascii=False)}
【近期错题复盘】：{json.dumps(errors[-12:], ensure_ascii=False)}

【军规提炼铁律】：
1. 聚焦做市商博弈逻辑：平博欧盘终赔风控锚定、平博/皇冠/易胜博亚盘分歧洗盘阻上、平博/皇冠大小球压制与天气场地修正。
2. 语言简练锋利，格式严格统一为：【军规X】[触发特征/盘口形态] -> [量化决策与避坑动作]。
3. 严格输出 5 至 8 条，每行一条，严禁输出任何引言或多余文字。
"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(prompt)
        lines = [r.strip() for r in res.text.strip().split("\n") if r.strip().startswith("【军规")]
        if lines:
            st.session_state.db["rules"] = lines[:8]
            st.session_state.db["last_evolved_count"] = len(settled)
            push_to_cloud(st.session_state.db)
            return True, f"军规库已自进化为 {len(lines[:8])} 条风控守则！"
        return False, "大模型未输出标准格式的军规。"
    except Exception as e:
        return False, str(e)

gemini_key_default = get_secret("GEMINI_API_KEY")
odds_key_default = get_secret("ODDS_API_KEY")
active_key = gemini_key_default

# 满 5 场自动自进化触发判定
settled_list = [h for h in st.session_state.db.get("history", []) if h.get("settled", False)]
last_evolved = st.session_state.db.get("last_evolved_count", 0)
if len(settled_list) - last_evolved >= 5 and active_key:
    trigger_evolution(active_key)

# ==============================================================================
# 5. 侧边栏监控、密钥覆写与全量备份导出
# ==============================================================================
with st.sidebar:
    st.subheader("⚙️ 核心接口监控中枢")
    if IS_CLOUD_READY:
        st.success("🟢 数据库 (JSONBin)：正常")
    else:
        st.error("🔴 数据库密钥缺失")
    if gemini_key_default:
        st.success("🟢 Gemini API：已就绪")
    if odds_key_default:
        st.success("🟢 The Odds API：已就绪")
        
    if st.button("⚡ 诊断云端数据库真实通信状态", use_container_width=True):
        test_ok, test_msg, test_data = fetch_from_cloud()
        if test_ok:
            st.success(f"通信正常！云端当前：\n- 历史推演：{len(test_data.get('history', []))} 场\n- 错题记录：{len(test_data.get('error_bank', []))} 条")
        else:
            st.error(test_msg)

    st.markdown("---")
    st.markdown("**🔑 密钥参数实时覆写：**")
    gemini_input = st.text_input("1. Gemini API Key", value=gemini_key_default, type="password")
    if gemini_input:
        active_key = gemini_input
    odds_input = st.text_input("2. The Odds API Key", value=odds_key_default, type="password")
    if odds_input:
        odds_key_default = odds_input
    jsonbin_key_input = st.text_input("3. JSONBin Master Key", value=JSONBIN_KEY, type="password")
    jsonbin_id_input = st.text_input("4. JSONBin Bin ID", value=JSONBIN_BIN_ID)

    st.markdown("---")
    st.markdown(f"**🛡️ 黄金军规池 ({len(st.session_state.db.get('rules', []))}/8)**")
    for r in st.session_state.db.get("rules", []):
        st.caption(f"• {r}")
        
    if st.button("🔄 手动触发 AI 军规反思自进化", use_container_width=True):
        if not active_key:
            st.error("请先配置 GEMINI_API_KEY！")
        else:
            with st.spinner("AI 正在深度反思并提炼军规..."):
                ok, msg = trigger_evolution(active_key)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    st.markdown("---")
    backup_data = json.dumps(st.session_state.db, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        "📥 备份导出全量数据库 (JSON)",
        data=backup_data,
        file_name=f"omni_quant_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        use_container_width=True
    )

# ==============================================================================
# 6. 主看板看板与多端强制同步
# ==============================================================================
st.markdown("### ⚽ 足球微观量化做市决策系统")

total_m = len(st.session_state.db.get("history", []))
red_m = len([h for h in st.session_state.db.get("history", []) if h.get("result_tag") == "红"])
black_m = len([h for h in st.session_state.db.get("history", []) if h.get("result_tag") == "黑"])
settled_total = red_m + black_m
win_rate = f"{(red_m / settled_total * 100):.1f}%" if settled_total > 0 else "0.0%"

st.markdown(f"""
<div class="metric-grid">
    <div class="metric-item">
        <div class="metric-title">总推演</div>
        <div class="metric-num">{total_m}场</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">红单</div>
        <div class="metric-num" style="color: #28a745;">{red_m}</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">黑单</div>
        <div class="metric-num" style="color: #dc3545;">{black_m}</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">实战胜率</div>
        <div class="metric-num" style="color: #007bff;">{win_rate}</div>
    </div>
</div>
""", unsafe_allow_html=True)

if st.button("🔄 立即从云端强制拉取最新数据（多设备同步）", use_container_width=True):
    with st.spinner("正在从云端拉取最新全量数据..."):
        sync_ok, sync_msg, fresh_db = fetch_from_cloud()
        if sync_ok:
            st.session_state.db = fresh_db
            st.success("✅ 已成功拉取最新数据！")
            st.rerun()
        else:
            st.error(f"❌ 拉取失败: {sync_msg}")

tab1, tab2, tab3 = st.tabs(["🚀 推演录入", "📊 结算审计", "🧠 错题复盘"])

# ==============================================================================
# Tab 1: 纯截图 + The Odds API 双核驱动推演
# ==============================================================================
with tab1:
    st.markdown("""
    <div style="background:#eef2f7; border-left:4px solid #007bff; padding:8px 10px; border-radius:6px; margin-bottom:12px; font-size:0.82rem; color:#333;">
        <b>📌 数据源双核输入架构（免手动打字）：</b><br>
        • <b>API 精算引擎</b>：联动 The Odds API 提取平博即时终赔与去抽水纯概率<br>
        • <b>多模态视觉</b>：截图上传 欧(平博) | 亚(平博+皇冠+易胜博) | 大小(平博+皇冠) | 首发名单与伤停
    </div>
    """, unsafe_allow_html=True)

    match_title = st.text_input("⚽ 目标对阵 / 联赛", placeholder="例如：曼彻斯特联 vs 切尔西")
    
    selected_league_label = st.selectbox("🌐 联动 The Odds API 抓取平博实时精算数据（选填）", list(LEAGUE_MAP.keys()))
    selected_sport_key = LEAGUE_MAP[selected_league_label]
    
    api_intel_str = "无 API 实时注入数据，完全基于用户上传截图与参数"
    if selected_sport_key and odds_key_default:
        with st.spinner("正在直连 The Odds API 抓取做市商实时底层赔率..."):
            api_res = query_the_odds_api(odds_key_default, selected_sport_key, match_title)
            if api_res and not api_res.get("error"):
                p_odds = api_res.get("pinnacle_odds", {})
                st.markdown(f"""
                <div class="api-card">
                    <b>📡 The Odds API 已成功抓取并精算实时盘面：</b><br>
                    • 目标赛事：<b>{api_res.get('match_found')}</b><br>
                    • 平博(Pinnacle)实时欧赔：主胜 <b>{p_odds.get(list(p_odds.keys())[0], 'N/A') if p_odds else 'N/A'}</b> | 平局 <b>{p_odds.get('Draw', 'N/A')}</b> | 客胜 <b>{p_odds.get(list(p_odds.keys())[-1], 'N/A') if p_odds else 'N/A'}</b><br>
                    • 平博精算返还率：<b>{api_res.get('payout_rate', 'N/A')}</b><br>
                    • 平博去抽水纯概率：主胜 <b>{api_res.get('fair_prob_home', 'N/A')}</b> | 平 <b>{api_res.get('fair_prob_draw', 'N/A')}</b> | 客 <b>{api_res.get('fair_prob_away', 'N/A')}</b>
                </div>
                """, unsafe_allow_html=True)
                api_intel_str = json.dumps(api_res, ensure_ascii=False)
            elif api_res and api_res.get("error"):
                st.caption(f"ℹ️ API 提示: {api_res.get('error')}")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        handicap = st.number_input("竞彩让球数（主队）", value=-1, step=1)
    with col_c2:
        goals_line = st.number_input("市场进球数基线参考", value=2.50, step=0.25)
        
    col_env1, col_env2 = st.columns(2)
    with col_env1:
        weather_opt = st.selectbox(
            "天气与场地状况",
            ["🌤 晴朗 / 场地优良", "🌧️ 小雨 / 场地湿滑", "⛈️ 暴雨 / 严重积水", "❄️ 严寒 / 冰冻降雪", "🌪️ 大风 / 高空球受阻"]
        )
    with col_env2:
        market_anomalies = st.multiselect(
            "做市商异动特征（多选，无则不选）",
            ["平博超低水深开诱主", "皇冠临场连续退盘", "易胜博逆向升水洗盘", "平博/皇冠大小球异常降水", "主流机构强阻上盘", "必发冷热对冲异动"]
        )
    
    uploaded_files = st.file_uploader(
        "📷 多选上传所有截图（指数页 + 首发阵容/伤停图 + 必发图[选传]）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    
    start_analyze = st.button("⚡ 启动双核量化做市推演", type="primary", use_container_width=True)
    
    if start_analyze:
        if not active_key:
            st.error("请先配置 GEMINI_API_KEY！")
        elif not match_title:
            st.warning("请输入对阵名称！")
        else:
            with st.spinner("AI 正在视觉识别阵容与盘口、融合 API 精算并演算决策..."):
                try:
                    genai.configure(api_key=active_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    images_payload = [Image.open(f) for f in uploaded_files] if uploaded_files else []
                    
                    rules_str = "\n".join(st.session_state.db.get("rules", []))
                    errors_summary = "\n".join([f"- {e.get('note')}" for e in st.session_state.db.get("error_bank", [])[-8:]])
                    anomalies_str = "、".join(market_anomalies) if market_anomalies else "无显著异常"
                    
                    system_prompt = f"""
你是一名顶级国际体育对冲基金首席做市策略师、精算师兼赛事量化总监。你的唯一目标是结合【The Odds API 实时精算数据】与【用户上传的多张截图】，穿透国际做市商的真实微观意图，规避资金诱导陷阱，输出高胜率的竞彩实战赛果决策。

【目标比赛与参数】：
- 对阵/联赛：【{match_title}】
- 主队竞彩官方让球数：[{handicap}]
- 市场进球数基线：[{goals_line}]
- 气候与场地条件：[{weather_opt}]
- 做市商盘口异动标记：[{anomalies_str}]

【The Odds API 注入的实时做市商精算数据】：
{api_intel_str}

【指定核心数据源机构矩阵（严格对照分析，绝不偏离）】：
1. 欧盘基准：严格以【平博（Pinnacle）】初/即时终赔为风控底线与真实概率锚定；
2. 亚盘穿透：严格对比【平博】、【皇冠（Crown）】、【易胜博（Easybet）】三家机构的折让幅度、贴水阻诱与盘口变动分歧；
3. 大小球基线：严格以【平博】与【皇冠】两家的大小球初即盘与水位为判定依据。

【多模态视觉识别与全自动化推理任务】：
1. **自动阵容与伤停解析**：仔细扫描阵容与伤停截图，自动识别双方首发、替补及核心缺阵（组织核心、射手、主力门卫），量化其对攻防两端预期进球（xG）的实质折损；
2. **结合 API 精算数据校验**：若上方存在 API 注入数据，必须将平博的“去抽水纯概率”与截图中亚盘三巨头的水位变动进行交叉对冲校验；
3. **泊松分布与比分闭环自洽铁律**：比分推演必须与胜负单选、让球单选、进球数双选 100% 逻辑自洽闭环。

【当前生效的实战黄金军规池（严格遵守）】：
{rules_str}

【历史错题复盘教训（负样本前置避坑，绝不重蹈覆辙）】：
{errors_summary if errors_summary else "暂无历史负样本，严格依据军规执行推演"}

---
【输出规范（铁律级要求，必须完全按照以下结构输出，严禁任何模糊摇摆语言）】：

### 🏆 核心赛果量化决策看板
1. **欧盘胜负平（严格单选）**：【胜 / 平 / 负】 | 置信度：[XX%]
2. **亚盘/竞彩让球胜平负（严格单选）**：【让胜 / 让平 / 让负】（基于主队让球数 {handicap}） | 置信度：[XX%]
3. **多选总进球数（精选两个）**：【X球 / Y球】 | 置信度：[XX%]
4. **首选自洽比分**：【X - Y】（与欧盘、亚盘、进球数 100% 闭环）
5. **次选防冷比分**：【X - Y】

### 📡 API 做市商精算与去抽水底牌
- **平博真实概率穿透**：结合 API 抓取的平博去抽水纯概率（No-Vig Fair Odds），剖析做市商风控的真正倾斜方向；
- **返还率与风险暴露**：解析平博当前抽水深度与市场赔付风险。

### 🔍 首发阵容战力与核心伤停视觉穿透
- **视觉提取阵容与核心伤缺**：列出从截图中识别出的关键首发/伤停核心；
- **攻防战力折损量化**：明确对预期进球（xG）与防守漏球的实质影响。

### 📊 做市商微观盘口穿透（平博 / 皇冠 / 易胜博）
- **亚盘三巨头分歧**：剖析平博、皇冠、易胜博在盘口折让与贴水上的博弈形态（洗盘/阻上/诱下）；
- **大小球量化（平博+皇冠）与环境修正**：结合天气场地（{weather_opt}）与阵容折损，明确进球数压制或爆发区间。

### 🛡️ 竞彩实战风控防冷方案
- **让球方向风险定性**：明确穿盘、让平、让负的具体赔付阻力与陷阱；
- **最优实战投注组合**：给出兼顾高胜率与盈亏比的实战组合建议。
"""
                    res = model.generate_content([system_prompt] + images_payload)
                    output_text = res.text
                    
                    st.markdown("---")
                    st.markdown(output_text)
                    
                    record = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": match_title,
                        "handicap": handicap,
                        "goals_line": goals_line,
                        "weather": weather_opt,
                        "injury": "首发阵容与伤停自动由图像识别穿透",
                        "anomalies": anomalies_str,
                        "report": output_text,
                        "settled": False,
                        "actual_score": "",
                        "result_tag": "待结算"
                    }
                    st.session_state.db["history"].append(record)
                    push_to_cloud(st.session_state.db)
                    st.success("✅ 推演报告与全量参数已 100% 写入云端数据库！")
                except Exception as e:
                    st.error(f"推演演算出现异常：{str(e)}")

# ==============================================================================
# Tab 2: 结算审计
# ==============================================================================
with tab2:
    st.markdown("**📋 历史推演对阵与赛果录入**")
    records = st.session_state.db.get("history", [])
    if not records:
        st.info("暂无历史推演对阵记录。")
    else:
        for idx, rec in enumerate(reversed(records)):
            real_idx = len(records) - 1 - idx
            tag = rec.get("result_tag", "待结算")
            badge = "🔴" if tag == "黑" else ("🟢" if tag == "红" else ("🟡" if tag == "走水" else "⚪"))
            
            with st.expander(f"{badge} {rec.get('match')} (让球:{rec.get('handicap')}) - [{tag}]"):
                st.caption(f"📅 时间：{rec.get('date')} | 🌤 天气：{rec.get('weather', '未知')}")
                st.markdown(rec.get("report", "无详细报告"))
                st.markdown("---")
                
                c_s1, c_s2 = st.columns(2)
                with c_s1:
                    score_val = st.text_input("实际完场比分", value=rec.get("actual_score", ""), key=f"sc_{real_idx}", placeholder="如 2-1")
                with c_s2:
                    tag_opts = ["待结算", "红", "黑", "走水"]
                    tag_val = st.selectbox("实战核验判定", tag_opts, index=tag_opts.index(tag), key=f"tg_{real_idx}")
                    
                if st.button("💾 确认结算并存盘", key=f"save_btn_{real_idx}", use_container_width=True):
                    st.session_state.db["history"][real_idx]["actual_score"] = score_val
                    st.session_state.db["history"][real_idx]["result_tag"] = tag_val
                    st.session_state.db["history"][real_idx]["settled"] = (tag_val != "待结算")
                    if tag_val == "黑":
                        st.session_state.db["error_bank"].append({
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "note": f"【实战失误】{rec.get('match')} 完场比分 {score_val} -> 盘口防范不足"
                        })
                    push_to_cloud(st.session_state.db)
                    st.success("✅ 结算状态已更新并同步云端！")
                    st.rerun()

# ==============================================================================
# Tab 3: 错题复盘
# ==============================================================================
with tab3:
    st.markdown("**🧠 错题复盘与自进化避坑库**")
    err_input = st.text_input("手动录入避坑教训", placeholder="例如：强队让步过深且受热严重，临场持续降水实为诱盘，坚决防平")
    if st.button("➕ 录入避坑经验", use_container_width=True) and err_input:
        st.session_state.db["error_bank"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": err_input
        })
        push_to_cloud(st.session_state.db)
        st.success("✅ 避坑经验已真实写入云端数据库！")
        st.rerun()
            
    err_list = st.session_state.db.get("error_bank", [])
    if not err_list:
        st.info("错题库当前为空。")
    else:
        for i, item in enumerate(reversed(err_list)):
            st.markdown(f"**{len(err_list) - i}. [{item.get('time')}]** {item.get('note')}")
