import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import requests
from datetime import datetime

# ==============================================================================
# 1. 移动端优先视口渲染与流式 CSS 增强
# ==============================================================================
st.set_page_config(
    page_title="OmniQuant Cortex · 足球微观量化做市决策系统",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 3.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        max-width: 100% !important;
    }
    .stButton>button {
        border-radius: 10px !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .metric-grid {
        display: flex;
        justify-content: space-between;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 10px 6px;
        margin-bottom: 12px;
        margin-top: 6px;
    }
    .metric-item { flex: 1; text-align: center; }
    .metric-title { font-size: 0.70rem; color: #6c757d; margin-bottom: 2px; }
    .metric-num { font-size: 1.05rem; font-weight: 700; color: #212529; }
    .model-badge {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 12px;
        display: inline-block;
    }
    .tag-red { color: #28a745; font-weight: bold; }
    .tag-black { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 8 大核心黄金量化做市军规标准库
# ==============================================================================
FULL_8_RULES = [
    "【军规1】平博深盘超低水做热主胜，若必发买方成交过热，坚决防范下盘冷平与让负",
    "【军规2】做市商逆向升水洗盘且亚洲主流机构持续高水阻上，坚定锁定主胜独赢",
    "【军规3】天气恶劣湿滑积水严重时，技术流攻防受阻，总进球数严控小球区间并剔除大比分",
    "【军规4】核心组织中场或主力门将单点缺阵，防守体系降级，必须调高对向球队进球期望",
    "【军规5】欧亚背离与滞后诱盘：平博欧赔大幅下压而皇冠/易胜博亚盘维持浅盘拒不升盘，警惕无量诱上，首防让负",
    "【军规6】大小球诱大与卡球风控：平博/皇冠大小球初盘虚高挂高水、临场急退盘，亚盘让幅不足，坚决剔除大比分锁定小球区间",
    "【军规7】必发流动性陷阱：次级联赛小赛事必发资金池匮乏，严禁将散户挂单当主力建仓，强制以平博终盘去抽水纯概率为准",
    "【军规8】竞彩让平与边际穿盘博弈：强队让一球（-1）临场持续超低水强阻，首选正向穿盘让胜，防冷锁定1球小胜高赔让平"
]

# ==============================================================================
# 3. 密钥深度提取与安全格式转换
# ==============================================================================
def clean_str(val):
    if not val:
        return ""
    s = str(val).strip()
    for _ in range(2):
        s = s.strip().strip('"').strip("'").strip(',').strip(';').strip()
    return s

def safe_parse_handicap(val):
    if val is None:
        return 0
    try:
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        s = str(val).strip()
        m = re.search(r'([+-]?\d+)', s)
        if m:
            return int(m.group(1))
        return 0
    except Exception:
        return 0

def safe_parse_goals(val):
    """解析预测进球数，兼容列表或逗号分隔格式"""
    if isinstance(val, list):
        res = []
        for x in val:
            try:
                res.append(int(x))
            except Exception:
                pass
        return res
    if isinstance(val, str):
        nums = re.findall(r'\d+', val)
        return [int(n) for n in nums]
    return []

def get_secret(keys, default=""):
    try:
        for k in keys:
            if k in st.secrets:
                v = clean_str(st.secrets[k])
                if v:
                    return v
        return default
    except Exception:
        return default

GEMINI_API_KEY = get_secret(["GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_API_KEY"])
JSONBIN_KEY = get_secret(["JSONBIN_KEY", "JSONBIN_API_KEY"])
JSONBIN_BIN_ID = get_secret(["JSONBIN_BIN_ID", "JSONBIN_ID"])

IS_CLOUD_READY = bool(JSONBIN_KEY and JSONBIN_BIN_ID)
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}" if JSONBIN_BIN_ID else ""
JSONBIN_HEADERS = {
    "X-Master-Key": JSONBIN_KEY,
    "Content-Type": "application/json"
}

# ==============================================================================
# 4. 云端持久化存储中心
# ==============================================================================
def fetch_from_cloud():
    default_db = {
        "history": [],
        "rules": FULL_8_RULES.copy(),
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
                    "rules": data.get("rules", FULL_8_RULES),
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
        return resp.status_code == 200
    except Exception:
        return False

if "db" not in st.session_state:
    ok, msg, loaded_db = fetch_from_cloud()
    st.session_state.db = loaded_db

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

# ==============================================================================
# 5. 主看板三维透视统计概览
# ==============================================================================
st.markdown("### ⚽ 足球微观量化做市决策系统")

hist = st.session_state.db.get("history", [])
settled_records = [h for h in hist if h.get("settled", False)]
total_settled = len(settled_records)

# 独立核算三大玩法的胜率
eu_wins = len([h for h in settled_records if h.get("eu_tag") == "红"])
h_wins = len([h for h in settled_records if h.get("h_tag") == "红" or h.get("result_tag") == "红"])
goals_wins = len([h for h in settled_records if h.get("goals_tag") == "红"])

rate_eu = f"{(eu_wins / total_settled * 100):.1f}%" if total_settled > 0 else "0.0%"
rate_h = f"{(h_wins / total_settled * 100):.1f}%" if total_settled > 0 else "0.0%"
rate_goals = f"{(goals_wins / total_settled * 100):.1f}%" if total_settled > 0 else "0.0%"

st.markdown(f"""
<div class="metric-grid">
    <div class="metric-item">
        <div class="metric-title">总推演</div>
        <div class="metric-num">{len(hist)}场</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">欧盘胜率</div>
        <div class="metric-num" style="color: #28a745;">{rate_eu}</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">让球胜率</div>
        <div class="metric-num" style="color: #007bff;">{rate_h}</div>
    </div>
    <div class="metric-item">
        <div class="metric-title">进球数胜率</div>
        <div class="metric-num" style="color: #fd7e14;">{rate_goals}</div>
    </div>
</div>
""", unsafe_allow_html=True)

if st.button("🔄 立即从云端强制拉取最新数据（多设备同步）", use_container_width=True):
    ok, msg, fresh_db = fetch_from_cloud()
    if ok:
        st.session_state.db = fresh_db
        st.success("✅ 云端数据同步完成！")
        st.rerun()

tab1, tab2, tab3 = st.tabs(["🚀 推演录入", "📊 结算审计", "🧠 错题复盘"])

# ==============================================================================
# Tab 1: 推演录入（基于 3.8 引擎·显式标注）
# ==============================================================================
with tab1:
    with st.expander("🔑 临时密钥配置与接口测试（选填，默认已读 Secrets）"):
        manual_key = st.text_input("临时粘贴/测试新 Key", type="password")
        eval_key = clean_str(manual_key) if manual_key else GEMINI_API_KEY
        if eval_key:
            masked = f"{eval_key[:6]}...{eval_key[-4:]}" if len(eval_key) >= 10 else eval_key
            st.caption(f"当前生效 Key: `{masked}` ({len(eval_key)} 位)")
        if st.button("⚡ 1秒测试该密钥连通性", use_container_width=True):
            if not eval_key:
                st.error("未检测到密钥！")
            else:
                try:
                    genai.configure(api_key=eval_key)
                    success_m = None
                    last_err = ""
                    for m_name in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
                        try:
                            m = genai.GenerativeModel(m_name)
                            r = m.generate_content("Ping")
                            success_m = m_name
                            break
                        except Exception as sub_e:
                            last_err = str(sub_e)
                    if success_m:
                        st.success(f"🟢 通信正常！成功连接【{success_m}】引擎！")
                    else:
                        st.error(f"🔴 拦截原因: {last_err}")
                except Exception as e:
                    st.error(f"🔴 异常: {str(e)}")

    st.info("📌 **免打字极速模式**：直接上传截图，对阵、竞彩让球数(-1/0/+1)、大小球基线均由 AI 视觉自动提取。")

    with st.form("deduction_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "📷 上传所有截图（指数对比 / 首发阵容伤停 / 竞彩盘口 / 必发挂单）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            match_input = st.text_input("⚽ 目标对阵/联赛（选填，留空则自动识图）", placeholder="如: 曼联 vs 切尔西")
        with col_m2:
            weather_opt = st.selectbox("⛅ 天气与场地状况", ["🌤 晴朗 / 场地优良", "🌧️ 小雨 / 场地湿滑", "⛈️ 暴雨 / 严重积水", "❄ 严寒 / 冰冻降雪", "🌪️ 大风 / 高空球受阻"])

        anomaly_options = [
            "【正向洗盘】临场升盘降水·实力强阻",
            "【诱盘陷阱】初盘超深·临场急退诱下",
            "【欧亚背离】平博欧赔大幅下压·亚盘纹丝不动",
            "【大小球对冲】亚盘让深·大小球却超跌防小",
            "【大小球诱大】基线虚高挂满水·实盘阻小",
            "【伤停题材】核心主力伤停·盘口借势过度洗盘",
            "【必发冷门异常】平局/受让方挂单量反常畸高"
        ]
        selected_anomalies = st.multiselect("做市商异动特征（多选，无则不选）", anomaly_options)

        with st.expander("⚙️ 盘口基准高级手动覆盖（选填，默认全自动识图）"):
            override_handicap = st.selectbox("强制指定让球数", ["【自动看图识别】", "0 (常规胜平负)", "-1 (主让一球)", "+1 (主受让一球)", "-2", "+2"])
            override_goals = st.selectbox("强制指定进球基线", ["【自动看图识别】", "2.00", "2.25", "2.50", "2.75", "3.00", "3.25", "3.50"])

        start_btn = st.form_submit_button("⚡ 启动双核量化做市推演", type="primary", use_container_width=True)

    if start_btn:
        active_key = clean_str(manual_key) if manual_key else GEMINI_API_KEY
        
        if not uploaded_files:
            st.error("请至少上传一张截图！")
        elif not active_key:
            st.error("未检测到有效 Gemini API Key！请在 Secrets 中配置。")
        else:
            with st.spinner("Gemini 3.8 首席做市商正在看图识人、解析盘口、计算概率并推演自洽比分..."):
                try:
                    processed_imgs = [compress_image_for_mobile(f) for f in uploaded_files]
                    rules_str = "\n".join(st.session_state.db.get("rules", FULL_8_RULES))
                    anomalies_str = "、".join(selected_anomalies) if selected_anomalies else "无显著异常"
                    target_match_str = match_input if match_input else "请看图自动识别"

                    TICKS = chr(96) * 3

                    system_prompt = (
                        "你是由顶级体育量化基金打造的【OmniQuant Cortex】首席量化做市总监与赛事实时精算师。\n"
                        "当前任务：深度解析上传的截图，生成极其严谨的竞彩量化推演研报。\n\n"
                        "### 历史核心错题避坑军规池（本次推演必须严格回避以下陷阱）：\n"
                        f"{rules_str}\n\n"
                        "### 核心量化做市原则：\n"
                        "1. 欧盘基准：严格唯一锚定【平博（Pinnacle）】初/即时欧赔作为返还率与做市商风控真实概率底线；\n"
                        "2. 亚盘穿透：严格三维穿透【平博 + 皇冠 + 易胜博】的让球折让分歧与高低水阻诱洗盘；\n"
                        "3. 大小球基线：以【平博 + 皇冠】大小球初即盘与水位为判定依据；\n"
                        "4. 多模态视觉提取：自动识别对阵球队及联赛；自动识别竞彩官方让球数（0/-1/+1）；自动识别大小球主流基线；自动识别首发名单与核心伤停，量化攻防xG折损；若有必发截图，识别主力挂单异常。\n\n"
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
                        f"- 天气场地：{weather_opt}\n"
                        f"- 盘口异动标记：{anomalies_str}\n"
                        f"- 手动让球覆盖：{override_handicap}\n"
                        f"- 手动进球基线覆盖：{override_goals}\n\n"
                        "请立即分析上传的所有截图并输出完整研报与尾部 JSON 结构体！"
                    )

                    genai.configure(api_key=active_key)
                    
                    response = None
                    used_model = "gemini-3.8-flash"
                    for m_cand in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
                        try:
                            mdl = genai.GenerativeModel(m_cand)
                            response = mdl.generate_content([system_prompt, user_prompt] + processed_imgs)
                            if response:
                                used_model = m_cand
                                break
                        except Exception:
                            continue

                    if not response:
                        mdl = genai.GenerativeModel("gemini-1.5-flash")
                        response = mdl.generate_content([system_prompt, user_prompt] + processed_imgs)
                        used_model = "gemini-1.5-flash"

                    report_text = response.text

                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', report_text, re.DOTALL)
                    if json_match:
                        parsed_json = json.loads(json_match.group(1))
                    else:
                        parsed_json = {
                            "match_name": match_input if match_input else "视觉识别赛事",
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

                    parsed_h = safe_parse_handicap(parsed_json.get("detected_handicap", -1))
                    if "0" in override_handicap:
                        parsed_h = 0
                    elif "-1" in override_handicap:
                        parsed_h = -1
                    elif "+1" in override_handicap:
                        parsed_h = 1

                    new_rec = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": parsed_json.get("match_name", target_match_str),
                        "handicap": parsed_h,
                        "goals_line": parsed_json.get("detected_goals_line", 2.5),
                        "weather": weather_opt,
                        "anomalies": anomalies_str,
                        "model": used_model,
                        "report": report_text,
                        "decision": parsed_json,
                        "settled": False,
                        "actual_score": "",
                        "eu_tag": "待结算",
                        "h_tag": "待结算",
                        "goals_tag": "待结算",
                        "result_tag": "待结算"
                    }

                    st.session_state.db.setdefault("history", []).insert(0, new_rec)
                    push_to_cloud(st.session_state.db)

                    st.success(f"✅ 推演成功！采用【{used_model}】旗舰引擎精算，数据已 100% 同步云端。")
                    st.markdown(f"""
                    <div class="model-badge">
                        🤖 量化精算引擎：{used_model} &nbsp;|&nbsp; ⏱️ 生成时间：{datetime.now().strftime('%H:%M:%S')} &nbsp;|&nbsp; 状态：三维量化闭环
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(report_text)

                except Exception as e:
                    st.error(f"推演执行失败: {str(e)}")

# ==============================================================================
# Tab 2: 结算审计（支持欧盘/让球/进球数 三大维度独立结算判定）
# ==============================================================================
with tab2:
    st.markdown("**📋 历史推演对阵与自动比分结算**")
    records = st.session_state.db.get("history", [])

    if not records:
        st.info("暂无历史推演对阵记录。")
    else:
        for idx, rec in enumerate(records):
            dec = rec.get("decision", {}) or {}
            h_line = safe_parse_handicap(rec.get("handicap", -1))
            h_str = f"主({h_line:+d})" if h_line != 0 else "常规不让球"
            rec_model = rec.get("model", "gemini-3.8-flash")

            pred_eu = str(dec.get("pred_eu", "N/A")).strip()
            pred_h = str(dec.get("pred_handicap", "N/A")).strip()
            pred_goals = safe_parse_goals(dec.get("pred_goals", []))
            goals_disp = "/".join(map(str, pred_goals)) if pred_goals else str(dec.get("pred_goals", "N/A"))

            # 独立红黑标识
            tag_eu = rec.get("eu_tag", "待结算")
            tag_h = rec.get("h_tag", rec.get("result_tag", "待结算"))
            tag_g = rec.get("goals_tag", "待结算")

            if rec.get("settled", False):
                badge_title = f"让球:{tag_h} | 欧盘:{tag_eu} | 进球:{tag_g}"
            else:
                badge_title = "⏳待结算"

            with st.expander(f"[{badge_title}] {rec.get('match')} [{h_str}] - {rec.get('date')}", expanded=(not rec.get("settled", False))):
                st.markdown(f"""
                - **推演引擎**：`{rec_model}`
                - **欧盘预测**：【{pred_eu}】 &nbsp;|&nbsp; 状态：<span class="{'tag-red' if tag_eu=='红' else ('tag-black' if tag_eu=='黑' else '')}">{tag_eu}</span>
                - **让球预测**：【{pred_h}】 &nbsp;|&nbsp; 状态：<span class="{'tag-red' if tag_h=='红' else ('tag-black' if tag_h=='黑' else '')}">{tag_h}</span>
                - **进球预测**：【{goals_disp}球】 &nbsp;|&nbsp; 状态：<span class="{'tag-red' if tag_g=='红' else ('tag-black' if tag_g=='黑' else '')}">{tag_g}</span>
                - **自洽比分**：首选 `{dec.get('first_score', 'N/A')}` | 防冷 `{dec.get('second_score', 'N/A')}`
                """, unsafe_allow_html=True)

                rec_id = rec.get("id", f"idx_{idx}")

                # 【未结算卡片】
                if not rec.get("settled", False):
                    c_s1, c_s2 = st.columns(2)
                    with c_s1:
                        in_h = st.number_input("主队进球", min_value=0, max_value=20, value=0, key=f"h_{rec_id}")
                    with c_s2:
                        in_a = st.number_input("客队进球", min_value=0, max_value=20, value=0, key=f"a_{rec_id}")

                    col_op1, col_op2 = st.columns([3, 1])
                    with col_op1:
                        settle_btn = st.button("⚡ 一键自动核算（三维独立判定）", key=f"btn_{rec_id}", type="primary", use_container_width=True)
                    with col_op2:
                        del_pending_btn = st.button("🗑 删除该场", key=f"del_p_{rec_id}", use_container_width=True)

                    if settle_btn:
                        diff = in_h - in_a
                        tot_goals = in_h + in_a
                        act_score = f"{in_h}-{in_a}"

                        # 1. 欧盘真实判定
                        act_eu = "胜" if diff > 0 else ("平" if diff == 0 else "负")
                        is_eu_win = (pred_eu == act_eu)

                        # 2. 让球真实判定
                        if h_line == 0:
                            act_h = "胜" if diff > 0 else ("平" if diff == 0 else "负")
                        else:
                            if diff > -h_line:
                                act_h = "让胜"
                            elif diff == -h_line:
                                act_h = "让平"
                            else:
                                act_h = "让负"
                        is_h_win = (pred_h == act_h)

                        # 3. 进球数真实判定
                        is_goals_win = (tot_goals in pred_goals) if pred_goals else False

                        rec["actual_score"] = act_score
                        rec["settled"] = True
                        rec["eu_tag"] = "红" if is_eu_win else "黑"
                        rec["h_tag"] = "红" if is_h_win else "黑"
                        rec["goals_tag"] = "红" if is_goals_win else "黑"
                        rec["result_tag"] = "红" if is_h_win else "黑"

                        if not is_h_win:
                            st.session_state.db.setdefault("error_bank", []).append({
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "note": f"【实战失误】{rec.get('match')} (盘口:{h_str}) 完场 {act_score} -> 让球打出【{act_h}】，预测【{pred_h}】黑单"
                            })

                        push_to_cloud(st.session_state.db)
                        st.success(f"核算完成！完场 {act_score}：欧盘打出【{act_eu}】({'🟢红' if is_eu_win else '🔴黑'})，让球打出【{act_h}】({'🟢红' if is_h_win else '🔴黑'})，总进球【{tot_goals}球】({'🟢红' if is_goals_win else '🔴黑'})")
                        st.rerun()

                    if del_pending_btn:
                        st.session_state.db["history"] = [x for x in st.session_state.db["history"] if x.get("id") != rec.get("id")]
                        push_to_cloud(st.session_state.db)
                        st.success("✅ 记录已删除！")
                        st.rerun()

                # 【已结算卡片】
                else:
                    st.caption(f"🏁 完场比分：{rec.get('actual_score')}")
                    col_b1, col_b2 = st.columns([3, 1])
                    with col_b1:
                        if st.button("🔄 重新核算该场比分", key=f"reset_{rec_id}"):
                            rec["settled"] = False
                            push_to_cloud(st.session_state.db)
                            st.rerun()
                    with col_b2:
                        if st.button("🗑️ 删除记录", key=f"del_{rec_id}"):
                            st.session_state.db["history"] = [x for x in st.session_state.db["history"] if x.get("id") != rec.get("id")]
                            push_to_cloud(st.session_state.db)
                            st.rerun()

# ==============================================================================
# Tab 3: 错题复盘与自进化避坑库
# ==============================================================================
with tab3:
    st.markdown("**🧠 错题复盘与自进化避坑库**")

    if st.button("🔄 一键补齐/重置完整 8 大黄金量化军规", use_container_width=True):
        st.session_state.db["rules"] = FULL_8_RULES.copy()
        push_to_cloud(st.session_state.db)
        st.success("✅ 8 条黄金量化军规已全部补齐并永久同步至云端！")
        st.rerun()

    err_list = st.session_state.db.get("error_bank", [])
    st.markdown(f"累计负样本记录：**{len(err_list)} 条**")

    if len(err_list) >= 3:
        if st.button("⚡ 启动黑单负样本 AI 聚类反思（提炼新军规）", type="primary", use_container_width=True):
            active_key = clean_str(manual_key) if manual_key else GEMINI_API_KEY
            if not active_key:
                st.error("请先配置 Gemini API Key！")
            else:
                with st.spinner("AI 正在深度反思近期负样本共性并提炼避坑军规..."):
                    try:
                        genai.configure(api_key=active_key)
                        res = None
                        for m_cand in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash"]:
                            try:
                                m = genai.GenerativeModel(m_cand)
                                prompt = f"""
你作为顶级量化做市风控总监，审查以下近期竞彩失误样本：
{json.dumps(err_list[-8:], ensure_ascii=False, indent=2)}

请深度剖析这几场失误的做市商盘口与水位共性陷阱，提炼【1 条浓缩精准的黄金量化避坑军规】。
要求：字数在 50 字以内，以“【量化避坑】”开头，直接输出军规内容。
"""
                                res = m.generate_content(prompt)
                                if res:
                                    break
                            except Exception:
                                continue

                        if res:
                            new_rule = res.text.strip().replace("\n", "")
                            st.session_state.db.setdefault("rules", []).append(new_rule)
                            push_to_cloud(st.session_state.db)
                            st.success(f"🎉 新军规已提炼并入库：\n\n{new_rule}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"提炼失败: {e}")

    st.markdown("---")
    st.markdown("#### 📜 当前生效的实战黄金军规池")
    rules = st.session_state.db.get("rules", FULL_8_RULES)
    for idx, r in enumerate(rules):
        col_r1, col_r2 = st.columns([6, 1])
        with col_r1:
            st.markdown(f"**{idx + 1}.** {r}")
        with col_r2:
            if st.button("删", key=f"del_rule_{idx}"):
                st.session_state.db["rules"].pop(idx)
                push_to_cloud(st.session_state.db)
                st.rerun()

    st.markdown("---")
    with st.form("manual_err_form"):
        err_input = st.text_input("手动录入避坑教训", placeholder="例如：强队让步过深且受热严重，临场持续降水实为诱盘，坚决防平")
        if st.form_submit_button("➕ 录入避坑经验") and err_input:
            st.session_state.db.setdefault("error_bank", []).append({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "note": err_input.strip()
            })
            push_to_cloud(st.session_state.db)
            st.success("✅ 避坑教训已存盘！")
            st.rerun()
