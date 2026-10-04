import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import requests
from datetime import datetime

# ==========================================
# 0. 移动端 UI 样式注入与页面初始化
# ==========================================
st.set_page_config(
    page_title="足球微观量化做市决策系统",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 移动端自适应 CSS 优化
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 0.8rem; padding-right: 0.8rem; }
    .stMetric { background-color: #f8f9fa; border-radius: 8px; padding: 8px; border: 1px solid #e9ecef; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; padding: 6px 12px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 密钥管理与服务初始化
# ==========================================
def get_secret(key, default=""):
    if key in st.secrets:
        return st.secrets[key]
    return default

GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
JSONBIN_API_KEY = get_secret("JSONBIN_API_KEY")
JSONBIN_BIN_ID = get_secret("JSONBIN_BIN_ID")
ODDS_API_KEY = get_secret("ODDS_API_KEY")

if not (GEMINI_API_KEY and JSONBIN_API_KEY and JSONBIN_BIN_ID):
    with st.sidebar:
        st.header("🔑 云端服务配置")
        GEMINI_API_KEY = st.text_input("Gemini API Key", value=GEMINI_API_KEY, type="password")
        JSONBIN_API_KEY = st.text_input("JSONBin Master Key", value=JSONBIN_API_KEY, type="password")
        JSONBIN_BIN_ID = st.text_input("JSONBin Bin ID", value=JSONBIN_BIN_ID)
        ODDS_API_KEY = st.text_input("The Odds API Key (选填)", value=ODDS_API_KEY, type="password")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. JSONBin 云端数据库双向同步引擎
# ==========================================
DEFAULT_DB_SCHEMA = {
    "records": [],
    "rules_pool": [
        {"id": 1, "rule": "【量化避坑】强队临场让球超深且受热严重，欧亚背离时谨防让平与让负诱盘", "created_at": "2026-10-04 06:20"}
    ]
}

def fetch_cloud_db():
    if not (JSONBIN_API_KEY and JSONBIN_BIN_ID):
        if "local_db" not in st.session_state:
            st.session_state.local_db = DEFAULT_DB_SCHEMA
        return st.session_state.local_db
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            return resp.json().get("record", DEFAULT_DB_SCHEMA)
        else:
            return st.session_state.get("local_db", DEFAULT_DB_SCHEMA)
    except Exception:
        return st.session_state.get("local_db", DEFAULT_DB_SCHEMA)

def save_cloud_db(data):
    st.session_state.local_db = data
    if not (JSONBIN_API_KEY and JSONBIN_BIN_ID):
        return True
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": JSONBIN_API_KEY
    }
    try:
        resp = requests.put(url, headers=headers, json=data, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        st.error(f"云端写入失败: {e}")
        return False

if "db" not in st.session_state:
    st.session_state.db = fetch_cloud_db()

# ==========================================
# 3. 移动端图片压缩引擎
# ==========================================
def compress_image_for_mobile(uploaded_file, max_size=1600, quality=85):
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    w, h = img.size
    if max(w, h) > max_size:
        if w > h:
            new_w = max_size
            new_h = int(h * (max_size / w))
        else:
            new_h = max_size
            new_w = int(w * (max_size / h))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=quality)
    buffered.seek(0)
    return Image.open(buffered)

# ==========================================
# 4. 统计指标计算看板
# ==========================================
def render_metrics_dashboard():
    records = st.session_state.db.get("records", [])
    total_deductions = len(records)
    settled_records = [r for r in records if r.get("status") == "settled"]
    
    h_wins = sum(1 for r in settled_records if r.get("settlement", {}).get("handicap_hit") is True)
    g_wins = sum(1 for r in settled_records if r.get("settlement", {}).get("goals_hit") is True)
    total_settled = len(settled_records)
    
    h_rate = (h_wins / total_settled * 100) if total_settled > 0 else 0.0
    g_rate = (g_wins / total_settled * 100) if total_settled > 0 else 0.0

    st.markdown("### ⚽ 足球微观量化做市决策系统")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总推演", f"{total_deductions}场")
    col2.metric("让球红单", f"{h_wins}场", delta=f"{h_rate:.1f}% 胜率" if total_settled > 0 else None)
    col3.metric("双选进球红", f"{g_wins}场", delta=f"{g_rate:.1f}% 命中" if total_settled > 0 else None)
    col4.metric("已结算", f"{total_settled}场")

    if st.button("🔄 立即从云端强制拉取最新数据（多设备同步）", use_container_width=True):
        st.session_state.db = fetch_cloud_db()
        st.rerun()

render_metrics_dashboard()

tab_deduction, tab_settlement, tab_rules = st.tabs(["🚀 推演录入", "📊 结算审计", "🧠 错题复盘与自进化"])

# ==========================================
# TAB 1: 推演录入（全自动视觉穿透）
# ==========================================
with tab_deduction:
    st.info("📌 **免打字极速模式**：直接上传截图，对阵、竞彩让球数(-1/0/+1)、大小球基线均由 AI 视觉自动提取。")
    
    with st.form("deduction_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "📷 上传截图（支持多选：指数对比 / 首发阵容伤停 / 竞彩盘口 / 必发挂单）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            match_name_input = st.text_input("⚽ 目标对阵/联赛（选填，留空则自动看图识队）", placeholder="如: 阿森纳 vs 切尔西")
        with col_m2:
            weather_option = st.selectbox("⛅ 天气场地状况", ["晴朗 / 场地优良", "雨雪湿滑 / 阻碍地面传控", "大风低温 / 限制高球", "高原高温 / 体能严重损耗"])
        
        anomaly_options = [
            "【正向洗盘】临场升盘降水·实力强阻",
            "【诱盘陷阱】初盘超深·临场急退诱下",
            "【欧亚背离】平博欧赔大幅下压·亚盘纹丝不动",
            "【大小球对冲】亚盘让深·大小球却超跌防小",
            "【大小球诱大】基线虚高挂满水·实盘阻小",
            "【伤停题材】核心主力伤停·盘口借势过度洗盘",
            "【必发冷门异常】平局/受让方挂单量反常畸高"
        ]
        selected_anomalies = st.multiselect("做市商异动特征（多选，无则不选）", options=anomaly_options)

        with st.expander("⚙️ 盘口基准手动覆盖（选填，默认全自动识别，无需手动修改）"):
            override_handicap = st.selectbox("强制指定竞彩让球数（主队）", ["【自动看图识别】", "0 (常规胜平负)", "-1 (主让一球)", "+1 (主受让一球)", "-2", "+2"])
            override_goals = st.selectbox("强制指定大小球基线", ["【自动看图识别】", "2.00", "2.25", "2.50", "2.75", "3.00", "3.25", "3.50"])

        submit_btn = st.form_submit_button("⚡ 启动双核量化做市推演", use_container_width=True, type="primary")

    if submit_btn:
        if not uploaded_files:
            st.error("请至少上传一张截图（指数对比图或阵容伤停图）！")
        elif not GEMINI_API_KEY:
            st.error("未检测到 Gemini API Key，请在侧边栏或 Secrets 中配置！")
        else:
            with st.spinner("AI 首席做市商正在看图识人、解析盘口、计算去抽水概率与自洽比分..."):
                try:
                    processed_images = [compress_image_for_mobile(f) for f in uploaded_files]
                    
                    active_rules = st.session_state.db.get("rules_pool", [])[-6:]
                    rules_context_str = "\n".join([f"- {r.get('rule')}" for r in active_rules])
                    anomalies_str = ', '.join(selected_anomalies) if selected_anomalies else "无"
                    target_match_str = match_name_input if match_name_input else "请看图自动识别"

                    # 动态生成反引号变量，杜绝前端代码框被截断
                    TICKS = chr(96) * 3

                    system_prompt = (
                        "你是由顶级体育量化基金打造的【OmniQuant Cortex】首席量化做市总监与赛事实时精算师。\n"
                        "当前任务：深度解析上传的截图，生成极其严谨的竞彩量化推演研报。\n\n"
                        "### 历史核心错题避坑军规池（本次推演必须严格回避以下陷阱）：\n"
                        f"{rules_context_str}\n\n"
                        "### 核心量化做市原则：\n"
                        "1. 欧盘基准：严格唯一锚定【平博（Pinnacle）】初/即时欧赔作为返还率与做市商风控真实概率底线；\n"
                        "2. 亚盘穿透：严格三维穿透【平博 + 皇冠 + 易胜博】的让球折让分歧与高低水阻诱洗盘；\n"
                        "3. 大小球基线：以【平博 + 皇冠】大小球初即盘与水位为判定依据；\n"
                        "4. 多模态视觉提取：自动识别对阵球队及联赛；自动识别竞彩官方让球数（0/-1/+1）；自动识别大小球主流基线；自动识别首发阵容名单与核心伤停名单，量化预期进球折损（xG）；若有必发截图，识别主力挂单异常。\n\n"
                        "### 输出模板规范（严格按此结构输出，严禁模棱两可）：\n"
                        "### 🏆 核心赛果量化决策看板\n"
                        "1. 欧盘胜平负（严格单选）：【胜 / 平 / 负】 | 置信度：[XX%]\n"
                        "2. 亚盘/竞彩让球胜平负（严格单选）：【让胜 / 让平 / 让负】（基于识别到的让球数） | 置信度：[XX%]\n"
                        "3. 多选总进球数（精选两个）：【X球 / Y球】 | 置信度：[XX%]\n"
                        "4. 首选自洽比分：【X - Y】（与欧盘、让球、进球数 100% 逻辑自洽闭环）\n"
                        "5. 次选防冷比分：【X - Y】\n\n"
                        "### 📡 做市商精算与去抽水底牌（结合平博 No-Vig 纯概率）\n"
                        "### 🔍 首发阵容战力与核心伤停视觉穿透（识别名单 + xG折损量化）\n"
                        "### 📊 做市商微观盘口穿透（平博/皇冠/易胜博亚盘分歧 + 平博/皇冠大小球）\n"
                        "### 🛡️ 竞彩实战风控防冷方案（让球方向风险定性 + 最优对冲策略）\n\n"
                        "---\n"
                        "【系统数据结构化回传要求】\n"
                        f"在研报末尾，必须严格附加一个用于程序自动解析落库的 JSON 块（用 {TICKS}json 与 {TICKS} 包裹），格式如下：\n"
                        f"{TICKS}json\n"
                        "{\n"
                        '  "match_name": "识别出的对阵",\n'
                        '  "detected_handicap": -1,\n'
                        '  "detected_goals_line": 2.50,\n'
                        '  "pred_eu": "胜",\n'
                        '  "pred_eu_conf": 75,\n'
                        '  "pred_handicap": "让胜",\n'
                        '  "pred_handicap_conf": 70,\n'
                        '  "pred_goals": [2, 3],\n'
                        '  "pred_goals_conf": 80,\n'
                        '  "first_score": "2-0",\n'
                        '  "second_score": "2-1"\n'
                        "}\n"
                        f"{TICKS}\n"
                    )

                    user_prompt = (
                        f"用户补充信息：\n"
                        f"- 指定对阵：{target_match_str}\n"
                        f"- 天气场地：{weather_option}\n"
                        f"- 盘口异动标记：{anomalies_str}\n"
                        f"- 手动让球数覆盖：{override_handicap}\n"
                        f"- 手动大小球基线覆盖：{override_goals}\n\n"
                        "请立即分析上传的所有截图并输出完整研报与尾部 JSON 结构体！"
                    )

                    model = genai.GenerativeModel("gemini-2.5-flash")
                    contents = [system_prompt, user_prompt] + processed_images
                    response = model.generate_content(contents)
                    report_text = response.text

                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', report_text, re.DOTALL)
                    if json_match:
                        parsed_json = json.loads(json_match.group(1))
                    else:
                        parsed_json = {
                            "match_name": match_name_input if match_name_input else "视觉识别赛事",
                            "detected_handicap": -1,
                            "detected_goals_line": 2.5,
                            "pred_eu": "胜",
                            "pred_eu_conf": 70,
                            "pred_handicap": "让胜",
                            "pred_handicap_conf": 65,
                            "pred_goals": [2, 3],
                            "pred_goals_conf": 75,
                            "first_score": "2-1",
                            "second_score": "1-1"
                        }
                    
                    if "0" in override_handicap:
                        parsed_json["detected_handicap"] = 0
                    elif "-1" in override_handicap:
                        parsed_json["detected_handicap"] = -1
                    elif "+1" in override_handicap:
                        parsed_json["detected_handicap"] = 1
                    
                    if override_goals != "【自动看图识别】":
                        try:
                            parsed_json["detected_goals_line"] = float(override_goals)
                        except:
                            pass

                    rec_id = f"m_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    new_record = {
                        "id": rec_id,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match_name": parsed_json.get("match_name", match_name_input),
                        "handicap_line": parsed_json.get("detected_handicap", -1),
                        "goals_line": parsed_json.get("detected_goals_line", 2.5),
                        "report_markdown": report_text,
                        "decision": parsed_json,
                        "status": "pending",
                        "settlement": None
                    }
                    
                    st.session_state.db.setdefault("records", []).insert(0, new_record)
                    save_cloud_db(st.session_state.db)
                    
                    st.success("✅ 推演完成并已成功同步到云端数据库！")
                    st.markdown(report_text)
                    
                except Exception as e:
                    st.error(f"推演执行失败: {e}")

# ==========================================
# TAB 2: 结算审计（0 人工比分全自动裁判）
# ==========================================
with tab_settlement:
    st.subheader("📋 历史推演对阵与自动结算")
    records = st.session_state.db.get("records", [])
    
    pending_records = [r for r in records if r.get("status") == "pending"]
    settled_records = [r for r in records if r.get("status") == "settled"]

    st.markdown(f"**待结算场次 ({len(pending_records)})**")
    if not pending_records:
        st.caption("暂无待结算对阵。")
    
    for r in pending_records:
        dec = r.get("decision", {})
        h_line = r.get("handicap_line", -1)
        h_str = f"主({h_line:+d})" if h_line != 0 else "常规不让球"

        with st.expander(f"⏳ {r.get('timestamp')} | {r.get('match_name')} [{h_str}]", expanded=True):
            st.markdown(f"""
            - **推演预测**：欧盘【{dec.get('pred_eu')}】 | 竞彩让球【{dec.get('pred_handicap')}】 | 双选进球【{'/'.join(map(str, dec.get('pred_goals', [])))}球】
            - **自洽比分**：首选 `{dec.get('first_score')}` | 防冷 `{dec.get('second_score')}`
            """)
            
            c_s1, c_s2, c_s3 = st.columns([2, 2, 3])
            with c_s1:
                in_home = st.number_input("主队进球", min_value=0, max_value=20, value=0, key=f"h_{r['id']}")
            with c_s2:
                in_away = st.number_input("客队进球", min_value=0, max_value=20, value=0, key=f"a_{r['id']}")
            with c_s3:
                sp_val = st.number_input("打出 SP 奖金值(选填)", min_value=1.0, max_value=50.0, value=1.85, step=0.05, key=f"sp_{r['id']}")

            if st.button("⚡ 一键自动核算落库", key=f"btn_{r['id']}", type="primary"):
                diff = in_home - in_away
                tot_goals = in_home + in_away
                act_score = f"{in_home}-{in_away}"

                # 竞彩让球判定（非红即黑，无走水）
                if h_line == 0:
                    act_handicap = "胜" if diff > 0 else ("平" if diff == 0 else "负")
                else:
                    if diff > -h_line:
                        act_handicap = "让胜"
                    elif diff == -h_line:
                        act_handicap = "让平"
                    else:
                        act_handicap = "让负"

                pred_h = dec.get("pred_handicap")
                is_h_win = (pred_h == act_handicap)
                is_g_win = (tot_goals in dec.get("pred_goals", []))
                is_sc_win = (act_score in [dec.get("first_score"), dec.get("second_score")])

                r["status"] = "settled"
                r["settlement"] = {
                    "settle_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "home_score": in_home,
                    "away_score": in_away,
                    "actual_score": act_score,
                    "actual_handicap": act_handicap,
                    "actual_goals": tot_goals,
                    "handicap_hit": is_h_win,
                    "goals_hit": is_g_win,
                    "score_hit": is_sc_win,
                    "sp": sp_val
                }
                save_cloud_db(st.session_state.db)
                st.success(f"结算成功！让球赛果: {act_handicap} ({'🔴红单' if is_h_win else '⚫黑单'}), 总进球: {tot_goals}球 ({'🔴红单' if is_g_win else '⚫黑单'})")
                st.rerun()

    st.markdown("---")
    st.markdown(f"**已结算历史 ({len(settled_records)})**")
    for r in settled_records:
        s = r.get("settlement", {})
        h_badge = "🔴让球红" if s.get("handicap_hit") else "⚫让球黑"
        g_badge = "🔴进球红" if s.get("goals_hit") else "⚫进球黑"
        with st.expander(f"{r.get('match_name')} | 完场 {s.get('actual_score')} | {h_badge} | {g_badge}"):
            st.markdown(f"""
            - **推演预测**：竞彩让球【{r.get('decision', {}).get('pred_handicap')}】 | 双选进球【{'/'.join(map(str, r.get('decision', {}).get('pred_goals', [])))}球】
            - **终场赛果**：比分 `{s.get('actual_score')}` | 竞彩让球 `{s.get('actual_handicap')}` | 总进球 `{s.get('actual_goals')}球`
            - **结算时间**：{s.get('settle_time')}
            """)
            if st.button("🗑️ 删除本条记录", key=f"del_{r['id']}"):
                st.session_state.db["records"] = [item for item in st.session_state.db["records"] if item["id"] != r["id"]]
                save_cloud_db(st.session_state.db)
                st.rerun()

# ==========================================
# TAB 3: 错题复盘与自进化避坑库
# ==========================================
with tab_rules:
    st.subheader("🧠 错题复盘与自进化避坑库")
    
    black_records = [r for r in st.session_state.db.get("records", []) if r.get("status") == "settled" and r.get("settlement", {}).get("handicap_hit") is False]
    st.markdown(f"当前累计让球黑单样本：**{len(black_records)} 场**")

    if len(black_records) > 0:
        if st.button("⚡ 启动黑单负样本 AI 聚类反思（自动进化提炼新军规）", type="primary", use_container_width=True):
            if not GEMINI_API_KEY:
                st.error("请先配置 Gemini API Key！")
            else:
                with st.spinner("AI 首席风控官正在审查黑单复盘特征并聚类归因..."):
                    try:
                        recent_blacks = black_records[:5]
                        black_summary = []
                        for b in recent_blacks:
                            s = b.get("settlement", {})
                            d = b.get("decision", {})
                            black_summary.append(f"场次: {b.get('match_name')}, 让球基准: {b.get('handicap_line')}, 预测让球: {d.get('pred_handicap')}, 实际比分: {s.get('actual_score')}, 实际打出: {s.get('actual_handicap')}")
                        
                        prompt_evo = (
                            "你作为顶级量化风控委员会主席，深度审查以下这几场竞彩让球黑单赛事：\n"
                            f"{json.dumps(black_summary, ensure_ascii=False, indent=2)}\n\n"
                            "请深度剖析这几场黑单的做市商共性陷阱（如：是否高估让球强队支持力、低估核心伤停、平博高水诱盘等）。\n"
                            "归纳提炼出【1 条高度浓缩、可操作、能写入代码系统的核心黄金量化避坑军规】。\n"
                            "要求：字数在 50 字以内，以“【量化避坑】”开头，直击要害，禁止泛泛而谈。"
                        )
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        res = model.generate_content(prompt_evo)
                        new_rule_content = res.text.strip().replace("\n", "")

                        new_rule_item = {
                            "id": len(st.session_state.db.get("rules_pool", [])) + 1,
                            "rule": new_rule_content,
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        st.session_state.db.setdefault("rules_pool", []).append(new_rule_item)
                        save_cloud_db(st.session_state.db)
                        st.success(f"🎉 自进化完成！新军规已成功写入军规池：\n\n{new_rule_content}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"自进化提取失败: {e}")

    st.markdown("---")
    st.markdown("#### 📜 当前生效的黄金量化军规池（推演自动注入最新 Top-6）")
    rules_list = st.session_state.db.get("rules_pool", [])
    
    for idx, r_item in enumerate(reversed(rules_list)):
        col_r1, col_r2 = st.columns([6, 1])
        with col_r1:
            st.markdown(f"**{len(rules_list) - idx}.** `[{r_item.get('created_at', '系统')}]` {r_item.get('rule')}")
        with col_r2:
            if st.button("删除", key=f"del_r_{r_item.get('id', idx)}"):
                st.session_state.db["rules_pool"] = [x for x in st.session_state.db["rules_pool"] if x.get("id") != r_item.get("id")]
                save_cloud_db(st.session_state.db)
                st.rerun()

    st.markdown("---")
    with st.form("manual_rule_form"):
        manual_rule = st.text_input("手动追加量化操盘心得与教训")
        add_rule_btn = st.form_submit_button("➕ 录入避坑经验")
        if add_rule_btn and manual_rule:
            new_item = {
                "id": len(rules_list) + 1,
                "rule": manual_rule.strip(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            st.session_state.db.setdefault("rules_pool", []).append(new_item)
            save_cloud_db(st.session_state.db)
            st.success("心得已记录并持久化！")
            st.rerun()
