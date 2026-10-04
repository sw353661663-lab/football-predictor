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

# 深度移动端竖屏优化（留足顶部安全边距，修复遮挡；战绩横向紧凑自适应）
st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .block-container {
        padding-top: 3.8rem !important; /* 预留充足顶部安全区，彻底解决标题被遮挡问题 */
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
    /* 手机端专用 4 项战绩横排胶囊看板 */
    .metric-grid {
        display: flex;
        justify-content: space-between;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 10px 8px;
        margin-bottom: 15px;
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
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 云端持久化存储中心 (JSONBin.io 架构)
# ==============================================================================
def get_secret(key, default=""):
    try:
        return st.secrets.get(key, default)
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

def load_database():
    """从云端拉取全量数据库，网络异常时回退默认骨架"""
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
        return default_db
    try:
        resp = requests.get(f"{JSONBIN_URL}/latest", headers=JSONBIN_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("record", {})
            if isinstance(data, dict):
                return {
                    "history": data.get("history", []),
                    "rules": data.get("rules", default_db["rules"]),
                    "error_bank": data.get("error_bank", []),
                    "last_evolved_count": data.get("last_evolved_count", 0)
                }
    except Exception:
        pass
    return default_db

def save_database(data):
    """双向热同步推送到云端数据库"""
    if not IS_CLOUD_READY:
        return False
    try:
        resp = requests.put(JSONBIN_URL, json=data, headers=JSONBIN_HEADERS, timeout=8)
        return resp.status_code == 200
    except Exception:
        return False

if "db" not in st.session_state:
    st.session_state.db = load_database()

# ==============================================================================
# 3. 满 5 场自动触发与黄金军规蒸馏自进化引擎
# ==============================================================================
def trigger_evolution(api_key):
    """提取实战结算对阵与错题库，反思重构 5-8 条顶级军规"""
    history = st.session_state.db.get("history", [])
    errors = st.session_state.db.get("error_bank", [])
    settled = [h for h in history if h.get("settled", False)]
    
    if len(settled) == 0 and len(errors) == 0:
        return False, "暂无足够实战结算样本或错题，无法启动进化。"
        
    evolution_prompt = f"""
你是一名掌管顶级对冲基金足球做市策略的量化总监（OmniQuant Cortex 进化中枢）。
请根据近期实战结算数据（重点审视黑单与走水）以及错题复盘记录，深入穿透失误本质，重新提炼并更新 5 至 8 条实战价值最高的【黄金量化军规】。

【待审计的近期实战结算样本】：
{json.dumps(settled[-12:], ensure_ascii=False, indent=2)}

【近期错题复盘避坑记录】：
{json.dumps(errors[-12:], ensure_ascii=False, indent=2)}

【军规提炼铁律】：
1. 聚焦做市商博弈逻辑：涵盖平博终赔锚定、Bet365诱盘诱水、皇冠/利记盘口折让、必发冷热对冲及天气场地抑制。
2. 语言简练锋利，格式严格统一为：【军规X】[触发特征/盘口形态] -> [量化决策与避坑动作]。
3. 严格输出 5 至 8 条，每行一条，严禁输出任何引言、解释或多余符号。
"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(evolution_prompt)
        lines = [r.strip() for r in res.text.strip().split("\n") if r.strip().startswith("【军规")]
        if lines:
            st.session_state.db["rules"] = lines[:8]
            st.session_state.db["last_evolved_count"] = len(settled)
            save_database(st.session_state.db)
            return True, f"自进化完成！军规库已迭代更新为 {len(lines[:8])} 条黄金风控守则。"
        return False, "大模型未输出标准格式的军规，请重试。"
    except Exception as e:
        return False, f"自进化运行异常：{str(e)}"

# 检查实战结算是否累积满 5 场并触发静默自进化
gemini_key_default = get_secret("GEMINI_API_KEY")
active_key = gemini_key_default

settled_list = [h for h in st.session_state.db.get("history", []) if h.get("settled", False)]
last_evolved = st.session_state.db.get("last_evolved_count", 0)
if len(settled_list) - last_evolved >= 5 and active_key:
    trigger_evolution(active_key)

# ==============================================================================
# 4. 侧边栏系统监视与 4 大接口全透明管控
# ==============================================================================
with st.sidebar:
    st.subheader("⚙️ 4 大核心接口监控中枢")
    
    # 1 & 2. 数据库双密钥监控
    if IS_CLOUD_READY:
        st.success("🟢 数据库 (JSONBin)：双向同步正常")
    else:
        st.error("🔴 数据库：未连接，请核对 Secrets")
        
    # 3. Gemini 接口监控
    if gemini_key_default:
        st.success("🟢 Gemini API：已加载云端密钥")
    else:
        st.warning("🟠 Gemini API：未配置")
        
    # 4. The Odds API 监控
    odds_key_default = get_secret("ODDS_API_KEY")
    if odds_key_default:
        st.success("🟢 The Odds API：已加载云端密钥")
    else:
        st.warning("🟠 The Odds API：未配置")

    st.markdown("---")
    st.markdown("**🔑 4 大密钥参数查看 / 覆写：**")
    
    gemini_input = st.text_input("1. Gemini API Key", value=gemini_key_default, type="password")
    if gemini_input:
        active_key = gemini_input
        
    odds_input = st.text_input("2. The Odds API Key", value=odds_key_default, type="password")
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
            with st.spinner("AI 正在深度反思近期战绩并蒸馏军规..."):
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
# 5. 手机端主界面：顶部标题与自适应战绩看板
# ==============================================================================
st.markdown("### ⚽ 足球微观量化做市决策系统")

# 统计战绩数据
total_m = len(st.session_state.db.get("history", []))
red_m = len([h for h in st.session_state.db.get("history", []) if h.get("result_tag") == "红"])
black_m = len([h for h in st.session_state.db.get("history", []) if h.get("result_tag") == "黑"])
void_m = len([h for h in st.session_state.db.get("history", []) if h.get("result_tag") == "走水"])
settled_total = red_m + black_m
win_rate = f"{(red_m / settled_total * 100):.1f}%" if settled_total > 0 else "0.0%"

# 手机端横向自适应单行战绩胶囊卡片（拒绝竖向挤占空间）
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

tab1, tab2, tab3 = st.tabs(["🚀 推演录入", "📊 结算审计", "🧠 错题复盘"])

# ==============================================================================
# Tab 1: 手机端推演录入与满血 OmniQuant Cortex 推理
# ==============================================================================
with tab1:
    match_title = st.text_input("⚽ 目标对阵 / 联赛", placeholder="例如：英超 曼彻斯特联 vs 切尔西")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        handicap = st.number_input("竞彩让球数（主队）", value=-1, step=1, help="主队官方让球数，如 -1、+1")
    with col_c2:
        goals_line = st.number_input("市场进球数基线参考", value=2.50, step=0.25, help="主流机构大小球基准盘")
        
    col_env1, col_env2 = st.columns(2)
    with col_env1:
        weather_opt = st.selectbox(
            "天气与场地状况",
            ["🌤️ 晴朗 / 场地优良", "🌧️ 小雨 / 场地湿滑", "⛈️ 暴雨 / 严重积水", "❄️ 严寒 / 冰冻降雪", "🌪️ 大风 / 高空球受阻"]
        )
    with col_env2:
        market_anomalies = st.multiselect(
            "做市商异动特征（多选）",
            ["平博超低水深开诱主", "Bet365逆向升水洗盘", "皇冠临场连续退盘", "必发买方巨资做热", "主流机构强阻上盘", "大小球基准异常降水"]
        )
        
    injury_note = st.text_input("🚑 核心伤停 / 轮换备注", placeholder="例如：主队主力后腰伤缺，客队当家射手复出首发")
    
    uploaded_files = st.file_uploader(
        "📷 手机多选截图（竞彩奖金 / 皇冠 / 平博 / 365 / 必发 / 首发阵容）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    
    start_analyze = st.button("⚡ 启动全维度量化做市推演", type="primary", use_container_width=True)
    
    if start_analyze:
        if not active_key:
            st.error("请先在 Secrets 或侧边栏中配置 GEMINI_API_KEY！")
        elif not match_title:
            st.warning("请输入对阵名称！")
        else:
            with st.spinner("AI 正在穿透做市商微观盘口并进行多维量化演算..."):
                try:
                    genai.configure(api_key=active_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    images_payload = [Image.open(f) for f in uploaded_files] if uploaded_files else []
                    
                    rules_str = "\n".join(st.session_state.db.get("rules", []))
                    errors_summary = "\n".join([f"- {e.get('note')}" for e in st.session_state.db.get("error_bank", [])[-8:]])
                    anomalies_str = "、".join(market_anomalies) if market_anomalies else "无显著异常"
                    
                    system_prompt = f"""
你是一名顶级国际体育对冲基金首席做市策略师、精算师兼赛事量化总监。你的唯一目标是穿透国际做市商（Bookmakers）的微观盘口意图，规避资金诱导陷阱，输出高胜率的竞彩实战赛果决策。

【目标比赛与校准参数】：
- 对阵/联赛：【{match_title}】
- 主队竞彩官方让球数：[{handicap}]
- 市场进球数基线：[{goals_line}]
- 气候与场地条件：[{weather_opt}]
- 核心伤停与轮换变量：[{injury_note if injury_note else "双方阵容基本完整"}]
- 做市商盘口异动标记：[{anomalies_str}]

【当前生效的实战黄金军规池（严格遵守）】：
{rules_str}

【历史错题复盘教训（负样本前置避坑，绝不重蹈覆辙）】：
{errors_summary if errors_summary else "暂无历史负样本，严格依据军规执行推演"}

【做市商穿透与量化分析模型要求】：
1. 机构锚定层：
   - 欧赔基准：以平博（Pinnacle）终赔风控线与 Bet365 赔付临界点为核心对照；
   - 亚盘基准：重点穿透皇冠（Crown）、平博、利记（SBOBET）的折让幅度与贴水异动；
   - 交易所资金：分析必发（Betfair）成交量权重、主力资金倾向与大额挂单冷热。
2. 微观基本面与环境变量折损：
   - 伤停折损：主力组织者、后防中坚及门将缺阵，需精确量化其对预期进球（xG）与防守漏球期望的扰动；
   - 气候场地：恶劣天气（如暴雨积水、冰冻大风）对地面渗透打法和反击球速的抑制，必须强力校准进球基线。
3. 泊松分布与比分闭环自洽铁律：
   - 比分推演必须与胜负单选、让球单选、进球数双选 100% 逻辑吻合，严禁出现矛盾冲突。

---
【输出规范（铁律级要求，必须完全按照以下模板结构输出，严禁任何模糊摇摆语言）】：

### 🏆 核心赛果量化决策看板
1. **欧盘胜负平（严格单选）**：【胜 / 平 / 负】 | 置信度：[XX%]
2. **竞彩让球胜平负（严格单选）**：【让胜 / 让平 / 让负】（基于主队让球数 {handicap}） | 置信度：[XX%]
3. **双选总进球数（精选两个）**：【X球 / Y球】 | 置信度：[XX%]
4. **首选自洽比分**：【X - Y】（必须与欧盘单选、让球单选及进球数完全闭环）
5. **次选防冷比分**：【X - Y】

### 🔍 做市商微观盘口与资金流向穿透
- **机构指数走势定性**：解析平博、Bet365、皇冠的初指与即时指数调整动向，定性其属于“诱上/诱下”还是“正向防赔”；
- **必发筹码冷热穿透**：剖析成交量集中度、主力挂单分布与做市商真实盈亏平衡点；
- **微观变量与气候修正**：结合【{weather_opt}】及伤停（{injury_note}），论证其对比赛节奏和两端攻防进球的实质压制。

### 🛡️ 竞彩让球实战风控防冷方案
- **让球方向风险定性**：明确穿盘、让平、让负的具体赔付压力；
- **最优实战投注组合**：给出兼顾胜率与盈亏比的实战投注组合及极限防冷对冲建议。
"""
                    res = model.generate_content([system_prompt] + images_payload)
                    output_text = res.text
                    
                    st.markdown("---")
                    st.markdown(output_text)
                    
                    # 全量赛前微观数据持久化写入云端
                    record = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": match_title,
                        "handicap": handicap,
                        "goals_line": goals_line,
                        "weather": weather_opt,
                        "injury": injury_note if injury_note else "阵容齐整",
                        "anomalies": anomalies_str,
                        "report": output_text,
                        "settled": False,
                        "actual_score": "",
                        "result_tag": "待结算"
                    }
                    st.session_state.db["history"].append(record)
                    save_database(st.session_state.db)
                    st.success("✅ 本次推演及全量赛前微观参数已持久化同步至云端数据库！")
                except Exception as e:
                    st.error(f"推演演算出现异常：{str(e)}")

# ==============================================================================
# Tab 2: 手机端实战结算与红黑审计中心
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
                st.caption(f"🚑 伤停：{rec.get('injury', '无')} | 📊 异动：{rec.get('anomalies', '无')}")
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
                            "note": f"【实战失误】{rec.get('match')} 完场比分 {score_val} | 伤停({rec.get('injury')}) | 异动({rec.get('anomalies')}) -> 需防范盘口深浅诱导"
                        })
                    save_database(st.session_state.db)
                    st.success("结算已持久化并核验！")
                    st.rerun()

# ==============================================================================
# Tab 3: 手机端错题进化反思避坑库
# ==============================================================================
with tab3:
    st.markdown("**🧠 错题复盘与自进化避坑库**")
    err_input = st.text_input("手动录入避坑教训", placeholder="例如：强队让步过深且受热严重，临场持续降水实为诱盘，坚决防平")
    if st.button("➕ 录入避坑经验", use_container_width=True) and err_input:
        st.session_state.db["error_bank"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": err_input
        })
        save_database(st.session_state.db)
        st.success("避坑经验已入库并持久化！")
        st.rerun()
        
    err_list = st.session_state.db.get("error_bank", [])
    if not err_list:
        st.info("错题库当前为空。")
    else:
        for i, item in enumerate(reversed(err_list)):
            st.markdown(f"**{len(err_list) - i}. [{item.get('time')}]** {item.get('note')}")
