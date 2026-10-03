import streamlit as st
import requests
import json
import time
import os
import base64
import math
import re
from datetime import datetime

# ================= 页面配置 =================
st.set_page_config(
    page_title="OmniQuant Cortex 机构级量化自进化对冲中枢",
    page_icon="⚽",
    layout="wide"
)

DATA_FILE = "prediction_history.json"
RULES_FILE = "rules_vault.json"

# ================= 数据与军规持久化层 =================
def load_history():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(records):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"对账存档异常: {str(e)}")

def load_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_rules(rules):
    try:
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"军规存档异常: {str(e)}")

if "records" not in st.session_state:
    st.session_state.records = load_history()

if "rules" not in st.session_state:
    st.session_state.rules = load_rules()

# ================= 确定性数学层：Shin 去抽水与动态泊松 =================
def shin_devigging(odds):
    """Shin 严格无偏去抽水算法"""
    try:
        valid_odds = [float(o) for o in odds if float(o) > 1.0]
        if len(valid_odds) != 3:
            return None
        
        inv_sum = sum(1.0 / o for o in valid_odds)
        if inv_sum <= 1.0:
            return [round((1.0 / o) / inv_sum, 4) for o in valid_odds]
        
        low, high = 0.0, 0.40
        z = 0.0
        for _ in range(35):
            mid = (low + high) / 2.0
            p_sum = sum(
                (math.sqrt(mid**2 + 4 * (1 - mid) * ((1.0 / o) / inv_sum)) - mid) / (2 * (1 - mid))
                for o in valid_odds
            )
            if p_sum > 1.0:
                low = mid
            else:
                high = mid
            z = mid
            
        true_probs = [
            (math.sqrt(z**2 + 4 * (1 - z) * ((1.0 / o) / inv_sum)) - z) / (2 * (1 - z))
            for o in valid_odds
        ]
        norm = sum(true_probs)
        return [round(p / norm, 4) for p in true_probs]
    except Exception:
        return None

def poisson_pmf(k, lmbda):
    """泊松分布单点概率"""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def compute_dynamic_match_matrix(total_line=2.5, spread=-0.25, max_goals=6):
    """根据盘口大小球基准线与让球深度，数值反解两队预期进球"""
    home_xg = max(0.2, (total_line - spread) / 2.0)
    away_xg = max(0.2, (total_line + spread) / 2.0)

    prob_home_win = 0.0
    prob_draw = 0.0
    prob_away_win = 0.0
    total_goals_dist = {i: 0.0 for i in range(max_goals * 2 + 1)}
    score_matrix = {}

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, home_xg) * poisson_pmf(j, away_xg)
            if i > j:
                prob_home_win += p
            elif i == j:
                prob_draw += p
            else:
                prob_away_win += p
            
            total_goals_dist[i + j] += p
            score_matrix[f"{i}-{j}"] = round(p * 100, 2)

    sorted_scores = sorted(score_matrix.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "home_win": round(prob_home_win * 100, 2),
        "draw": round(prob_draw * 100, 2),
        "away_win": round(prob_away_win * 100, 2),
        "goals": {k: round(v * 100, 2) for k, v in total_goals_dist.items() if k <= 6},
        "top_scores": sorted_scores
    }

# ================= 真实 The Odds API 机构数据抓取 =================
def fetch_real_odds_api(api_key, sport="soccer", region="eu"):
    """拉取做市商实时赔率"""
    if not api_key:
        return None, "未配置 Odds API Key"
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={region}&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json(), None
        return None, f"API 状态码: {r.status_code} - {r.text[:150]}"
    except Exception as e:
        return None, f"网络请求异常: {str(e)}"

# ================= 纯 Python 本地全兼容确定性核销引擎 =================
def evaluate_score_locally(report_text, score_str):
    """
    100% 本地运算：完全兼容新老报告各种排版与输入法全角符号
    """
    if not score_str:
        return None, "比分未输入"
    
    clean_score = score_str.strip().replace('：', ':').replace(':', '-')
    m_score = re.search(r'(\d+)\s*[-]\s*(\d+)', clean_score)
    if not m_score:
        return None, "比分格式无效，请输入如 1-1 或 1-2"
    
    h_goals = int(m_score.group(1))
    a_goals = int(m_score.group(2))
    total_goals = h_goals + a_goals
    
    # 1. 判定欧盘胜平负
    actual_1x2 = "主胜" if h_goals > a_goals else ("平局" if h_goals == a_goals else "客胜")
    
    # 全兼容正则提取预测：优先检索欧盘段落
    m_ox_sec = re.search(r'(?:欧盘|胜平负).*?(?=(?:让球|亚盘|大小球|总进球|###|\Z))', report_text, re.DOTALL)
    ox_text = m_ox_sec.group(0) if m_ox_sec else report_text
    
    pred_1x2 = None
    if "客胜" in ox_text: pred_1x2 = "客胜"
    elif "主胜" in ox_text: pred_1x2 = "主胜"
    elif "平局" in ox_text: pred_1x2 = "平局"
    
    audit_1x2 = "未命中"
    if pred_1x2:
        audit_1x2 = "已命中" if pred_1x2 == actual_1x2 else "未命中"
    else:
        audit_1x2 = "未命中"
        
    # 2. 判定精确进球数双选
    m_goals_sec = re.search(r'(?:大小球|总进球数|进球数).*?(?=(?:###|0\.25x|\Z))', report_text, re.DOTALL)
    g_text = m_goals_sec.group(0) if m_goals_sec else report_text
    
    found_matches = re.findall(r'(?<![\.\d])(\d)\s*球', g_text)
    goals_nums = []
    for g in found_matches:
        gi = int(g)
        if gi not in goals_nums and gi <= 8:
            goals_nums.append(gi)
    goals_nums = goals_nums[:2]
    
    audit_goals = "未命中"
    if goals_nums and total_goals in goals_nums:
        audit_goals = "已命中"
        
    # 3. 判定亚盘/竞彩让球
    m_hand_sec = re.search(r'(?:让球|亚盘).*?(?=(?:大小球|总进球|欧盘|###|\Z))', report_text, re.DOTALL)
    hand_text = m_hand_sec.group(0) if m_hand_sec else report_text
    
    pred_handicap = None
    if "让负" in hand_text: pred_handicap = "让负"
    elif "让胜" in hand_text: pred_handicap = "让胜"
    elif "让平" in hand_text: pred_handicap = "让平"
    
    # 计算主队让球调整值 (h_adj)
    h_adj = -0.5
    if "受让半球" in hand_text or "+0.5" in hand_text:
        h_adj = 0.5 if ("主" in hand_text and "受让" in hand_text) else -0.5
    elif "让半球" in hand_text or "-0.5" in hand_text:
        h_adj = -0.5
    elif "平半" in hand_text or "0.25" in hand_text:
        h_adj = 0.25 if "受让" in hand_text else -0.25
    elif "半一" in hand_text or "0.75" in hand_text:
        h_adj = 0.75 if "受让" in hand_text else -0.75
    elif "一球" in hand_text or "1" in hand_text:
        h_adj = 1.0 if "受让" in hand_text else -1.0
    elif "平手" in hand_text:
        h_adj = 0.0
        
    diff = (h_goals + h_adj) - a_goals
    if diff > 0:
        actual_handicap = "让胜"
    elif diff == 0:
        actual_handicap = "让平"
    else:
        actual_handicap = "让负"
        
    audit_handicap = "未命中"
    if pred_handicap:
        if pred_handicap == actual_handicap:
            audit_handicap = "已命中"
        elif diff == 0 and "走盘" in pred_handicap:
            audit_handicap = "走盘"
            
    # 4. 计算三维综合成色
    hits = 0
    if audit_1x2 == "已命中": hits += 1
    if audit_handicap == "已命中": hits += 1
    if audit_goals == "已命中": hits += 1
    
    if hits == 3: comp_status = "全红极佳 (3/3)"
    elif hits == 2: comp_status = "双红达标 (2/3)"
    elif hits == 1: comp_status = "单红偏离 (1/3)"
    else: comp_status = "全黑盲区 (0/3)"
    
    summary = f"完场比分 {h_goals}-{a_goals} | 欧盘[{pred_1x2 or '已提取'}->{actual_1x2}:{audit_1x2}] | 让球[{pred_handicap or '已提取'}->{actual_handicap}:{audit_handicap}] | 进球[{goals_nums}->{total_goals}球:{audit_goals}]"
    
    return {
        "final_score": f"{h_goals}-{a_goals}",
        "audit_1x2": audit_1x2,
        "audit_handicap": audit_handicap,
        "audit_goals": audit_goals,
        "status": comp_status,
        "summary": summary
    }, None

# ================= 侧边栏：系统管理与军规记忆库 =================
with st.sidebar:
    st.header("⚙️ 机构对冲配置")
    bankroll = st.number_input("实战风控总本金 (单位: 元/USD)", min_value=1000, value=50000, step=5000)
    st.caption("基于 0.25x 凯利准则自动计算单场建议开仓金额")
    st.markdown("---")
    
    gemini_key_input = st.text_input("Gemini API Key (可选)", type="password")
    odds_key_input = st.text_input("The Odds API Key (可选)", type="password")
    st.caption("提示：云端已配置 Secrets 时后台将自动静默调用")
    
    st.markdown("---")
    st.subheader(f"🛡️ 避坑军规库 ({len(st.session_state.rules)}条已生效)")
    if st.session_state.rules:
        for idx, rule in enumerate(st.session_state.rules):
            st.caption(f"{idx+1}. {rule}")
        if st.button("🗑️ 清空所有已学生成军规"):
            st.session_state.rules = []
            save_rules([])
            st.success("军规库已重置！")
            st.rerun()
    else:
        st.caption("暂无回灌军规，在 Tab 3 进行错题归因后可一键注入。")

    st.markdown("---")
    st.subheader("💾 数据库全量热备份")
    json_str = json.dumps(st.session_state.records, ensure_ascii=False, indent=2)
    st.download_button(
        label="📥 导出全量对账历史",
        data=json_str,
        file_name=f"quant_vault_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json"
    )
    uploaded_backup = st.file_uploader("📤 恢复历史存档", type="json")
    if uploaded_backup is not None:
        try:
            imported = json.load(uploaded_backup)
            st.session_state.records = imported
            save_history(imported)
            st.success("量化档案恢复成功！")
        except Exception as e:
            st.error(f"恢复异常: {str(e)}")

gemini_api_key = st.secrets.get("GEMINI_API_KEY", gemini_key_input).strip()
odds_api_key = st.secrets.get("ODDS_API_KEY", odds_key_input).strip()

# ================= 多模态与联网搜索多通道调度 =================
def call_gemini_engine(api_key, prompt, images_payload=None, enable_search=False):
    models = ["gemini-2.5-flash", "gemini-1.5-flash"]
    headers = {"Content-Type": "application/json"}
    
    parts = [{"text": prompt}]
    if images_payload:
        for img_bytes, mime_type in images_payload:
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_b64
                }
            })
        
    payload = {"contents": [{"parts": parts}]}
    if enable_search:
        payload["tools"] = [{"google_search": {}}]

    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code == 200:
                data = r.json()
                if "candidates" in data and data["candidates"]:
                    content = data["candidates"][0].get("content", {})
                    ret_parts = content.get("parts", [])
                    text_list = [p.get("text", "") for p in ret_parts if "text" in p]
                    if text_list:
                        return "".join(text_list), model, None
            else:
                last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
            continue
    return None, None, last_err

def auto_search_score(gemini_key, match_name, match_date):
    """仅通过联网搜索抓取比分数字"""
    prompt = f"请联网查询足球比赛【{match_name}】（记录日期：{match_date}）的官方最终完场比分。请仅回复纯文本比分，例如：1-1 或 1-2。若比赛尚未完赛请回复：尚未完赛。"
    res_text, _, err = call_gemini_engine(gemini_key, prompt, enable_search=True)
    if res_text:
        if "尚未完赛" in res_text or "未开赛" in res_text:
            return None, "比赛尚未完赛或仍在进行中"
        m = re.search(r'\b(\d{1,2})\s*[-:：]\s*(\d{1,2})\b', res_text)
        if m:
            return f"{m.group(1)}-{m.group(2)}", "全网智能检索"
    return None, f"未检索到完场比分({err})"

# ================= 页面主交互导航 =================
tab1, tab2, tab3 = st.tabs(["🚀 实时双核量化推演", "📋 历史对账与三维结算", "🧠 错题归因与自适应进化"])

# ----------------- Tab 1: 实时推演 -----------------
with tab1:
    st.subheader("⚽ 赛事微观结构与剧本突变决策引擎（自进化全量版）")
    
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        match_input = st.text_input("🔍 目标对阵 / 联赛（例如：欧国联 哈萨克斯坦 vs 摩尔多瓦）", placeholder="输入对阵球队")
        
        with st.expander("🛠️ 本地数学层盘口校准参数（可选微调）", expanded=False):
            param_c1, param_c2 = st.columns(2)
            with param_c1:
                spread_val = st.number_input("主流亚盘让球深度（主队）", value=-0.25, step=0.25, help="如主让半球填 -0.5，客让平半填 0.25")
            with param_c2:
                total_val = st.number_input("主流大小球盘口基准线", value=2.25, step=0.25, help="如 2.25 球或 2.5 球")
                
    with col_in2:
        uploaded_imgs = st.file_uploader(
            "📸 批量上传做市商走势截图（多选相册：欧赔+亚盘+必发+首发）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
    if uploaded_imgs:
        st.write(f"已挂载 **{len(uploaded_imgs)}** 张盘口多模态数据切片：")
        cols = st.columns(min(len(uploaded_imgs), 4))
        for i, img_file in enumerate(uploaded_imgs):
            cols[i % len(cols)].image(img_file, caption=f"数据图 {i+1}", use_container_width=True)

    rules_context = ""
    if st.session_state.rules:
        rules_context = "【系统历史错题已进化生效的硬性避坑军规（最高优先级必须严格遵守）】：\n"
        for idx, r in enumerate(st.session_state.rules):
            rules_context += f"{idx+1}. {r}\n"

    btn_predict = st.button("🚀 启动工业级双核量化推演并持久化存盘")

    if btn_predict:
        if not gemini_api_key:
            st.error("未检测到有效密钥，请在侧边栏或 Secrets 中配置 Gemini API Key！")
        elif not match_input.strip() and not uploaded_imgs:
            st.warning("请至少输入对阵球队或上传盘口走势截图！")
        else:
            with st.spinner("双核自进化引擎运作中：[Shin 去抽水] + [动态 xG 求解] + [军规库强制过滤] + [Game-State 突变演进]..."):
                math_baseline = compute_dynamic_match_matrix(total_line=total_val, spread=spread_val)
                
                live_odds_info = "未配置 Odds API，以截图和输入盘口为准"
                if odds_api_key:
                    odds_data, odds_err = fetch_real_odds_api(odds_api_key)
                    if odds_data:
                        live_odds_info = f"已成功调取 The Odds API 实时市场样本，覆盖 {len(odds_data)} 场正在监控的比赛盘口。"

                prompt = f"""
你是一名顶级体育对冲基金首席量化研究员，精通做市商微观结构博弈、Shin (1993) 去抽水模型、联合分布自洽性与 Game-State 突变推演。
现对以下赛事启动深度交易研判：

【赛事信息】：{match_input if match_input else '详见上传截图中的赛事对阵'}
【外部实时做市商接口状态】：{live_odds_info}

{rules_context}

【本地确定性数理求解器动态输出（Python 硬核计算）】：
- 盘口动态解算预期进球 (Dynamic xG)：主队预期攻门 $\\lambda = {math_baseline['home_xg']}$ | 客队预期攻门 $\\mu = {math_baseline['away_xg']}$
- 动态泊松理论无偏概率：主胜 {math_baseline['home_win']}% | 平局 {math_baseline['draw']}% | 客胜 {math_baseline['away_win']}%
- 进球数理论离散度：0球({math_baseline['goals'].get(0)}%), 1球({math_baseline['goals'].get(1)}%), 2球({math_baseline['goals'].get(2)}%), 3球({math_baseline['goals'].get(3)}%)
- 数理最高概率比分 Top 3：1) {math_baseline['top_scores'][0][0]} ({math_baseline['top_scores'][0][1]}%) | 2) {math_baseline['top_scores'][1][0]} ({math_baseline['top_scores'][1][1]}%) | 3) {math_baseline['top_scores'][2][0]} ({math_baseline['top_scores'][2][1]}%)

【必须执行的最高分析铁律】：
1. **微观做市商模式强制定性**：明确归类【模式A：浅盘诱热 / 模式B：借题材阻盘 / 模式C：大单扫盘 Steam / 模式D：中立水钱对冲】。
2. **Game-State 突变与走地对冲指令**：推演弱队意外率先进球对大球的膨胀冲击，并给出明确的【走地突变对冲指令】。
3. **入场临界赔率（Cut-off Odds）**：每个选项必须标出“当前市场参考赔率”与“最低可接受入场赔率（Price Floor）”，跌破红线即放弃。
4. **主流亚盘大小球（Over/Under）与联合自洽比分**：必须映射至低抽水主流亚盘大小球（如 Under 2.25），并输出 Top 3 最可能具体比分。
5. **推演时效状态标定**：标明是【临场终盘确定态】还是【早盘战略预估态】。

请严格按照以下工业化格式输出报告：

### 一、做市商操盘定性与微观结构
- **做市商操盘模式归类**：明确标出模式 A/B/C/D，并说明底层资金逻辑。
- **平博/皇冠/利记异动解析**：初终盘变轨、升降水幅度与真实去抽水公允概率。
- **必发成交冷热**：资金成交量是否存在散户扎堆或主力暗盘。

### 二、Game-State 比赛剧本突变与走地对冲预案
- **基准剧本态（均势）**：双方正常战术下的攻防节奏。
- **破局突变态（压力测试）**：弱队/下盘若率先进球，强队全线前倾对大球的膨胀风险。
- **🚨 走地突变对冲指令**：赛中若触发突变，明确给出走地反手对冲的盘口与仓位建议。

### 三、核心量化决策（含公允临界点与联合自洽）
1. **欧盘胜平负**：
   - 核心结论：明确给出【主胜】、【平局】或【客胜】（单一选项）
   - 预测置信度：XX%
   - 价格边界：当前参考赔率 X.XX | 最低可接受赔率（Cut-off Odds）：X.XX
2. **亚盘让球盘**：
   - 明确盘口：标明让球方及让球幅度（如：客队受让半球）
   - 核心结论：明确给出【让胜】、【让平】或【让负】（单一选项）
   - 预测置信度：XX%
   - 价格边界：当前参考水位 X.XX | 最低可接受水位：X.XX
3. **大小球与总进球数**：
   - 主流亚盘大小球：【Over / Under X.X 球】（置信度：XX%，最低可接受赔率：X.XX）
   - 精确进球数两选：推荐一 X 球（XX%） | 推荐二 X 球（XX%）
4. **数理联合自洽 Top 3 终场比分**：
   - ① X-X（XX.X%）  ② X-X（XX.X%）  ③ X-X（XX.X%）

### 四、0.25x 凯利风控与执行纪律
- **核心价值投资项（Value Bet）**：指出全场最具正期望（+EV）的单一投注项。
- **动态期望值评估**：估算 EV = p * b - 1。
- **0.25x 凯利建议仓位**：明确给出建议开仓比例（如 1.5%~2.5%，若 EV 为负则 0% 放弃）。
- **推演时效状态**：【临场决战态（已定首发）】或【早盘战略态（未定首发）】。
"""

                images_payload = []
                if uploaded_imgs:
                    for img in uploaded_imgs:
                        images_payload.append((img.getvalue(), img.type))
                
                result_text, used_model, err = call_gemini_engine(
                    gemini_api_key, prompt, images_payload=images_payload
                )

                if result_text:
                    st.success(f"✅ 工业级双核量化推演完成！（计算节点：{used_model}）")
                    st.markdown(result_text)

                    display_name = match_input.strip() if match_input.strip() else "核心焦点赛事（多图交叉解析）"
                    new_record = {
                        "id": int(time.time()),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": display_name,
                        "model": used_model,
                        "report": result_text,
                        "status": "待结算",
                        "final_score": "",
                        "audit_1x2": "待结算",
                        "audit_handicap": "待结算",
                        "audit_goals": "待结算",
                        "clv_beaten": "待测算",
                        "audit_note": "",
                        "notes": ""
                    }
                    st.session_state.records.insert(0, new_record)
                    save_history(st.session_state.records)
                    st.toast("🎉 本次量化报告已自动存入持久化账本！", icon="💾")
                else:
                    st.error(f"接口响应异常：{err}")

# ----------------- Tab 2: 历史对账与三维结算 -----------------
with tab2:
    st.subheader("📋 推演历史对账与三维独立核销")
    if not st.session_state.records:
        st.info("暂无历史推演存档。请在【实时双核量化推演】中生成首次分析。")
    else:
        settled_records = [r for r in st.session_state.records if r.get("status") != "待结算"]
        settled_count = len(settled_records)

        hit_1x2 = len([r for r in settled_records if r.get("audit_1x2") == "已命中"])
        hit_handicap = len([r for r in settled_records if r.get("audit_handicap") == "已命中"])
        hit_goals = len([r for r in settled_records if r.get("audit_goals") == "已命中"])
        all_hit = len([r for r in settled_records if "3/3" in r.get("status", "")])

        rate_1x2 = (hit_1x2 / settled_count * 100) if settled_count > 0 else 0.0
        rate_handicap = (hit_handicap / settled_count * 100) if settled_count > 0 else 0.0
        rate_goals = (hit_goals / settled_count * 100) if settled_count > 0 else 0.0
        rate_all = (all_hit / settled_count * 100) if settled_count > 0 else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("欧盘独立胜率", f"{rate_1x2:.1f}%", f"{hit_1x2}/{settled_count} 场")
        m2.metric("让球独立胜率", f"{rate_handicap:.1f}%", f"{hit_handicap}/{settled_count} 场")
        m3.metric("进球数双选胜率", f"{rate_goals:.1f}%", f"{hit_goals}/{settled_count} 场")
        m4.metric("3/3 全红率", f"{rate_all:.1f}%", f"{all_hit}/{settled_count} 场")

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            current_status = rec.get('status', '待结算')
            with st.expander(f"【{current_status}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                
                # 状态标签展示
                st.markdown("##### 🔍 三维独立核验状态")
                tag_c1, tag_c2, tag_c3 = st.columns(3)
                
                st_1x2 = rec.get('audit_1x2', '待结算')
                st_hand = rec.get('audit_handicap', '待结算')
                st_g = rec.get('audit_goals', '待结算')

                if st_1x2 == "已命中": tag_c1.success(f"欧盘胜平负：**已命中** ✅")
                elif st_1x2 == "未命中": tag_c1.error(f"欧盘胜平负：**未命中** ❌")
                else: tag_c1.info(f"欧盘胜平负：**待结算**")

                if st_hand == "已命中": tag_c2.success(f"让球胜平负：**已命中** ✅")
                elif st_hand == "未命中": tag_c2.error(f"让球胜平负：**未命中** ❌")
                elif st_hand == "走盘": tag_c2.warning(f"让球胜平负：**走盘** ⚖️")
                else: tag_c2.info(f"让球胜平负：**待结算**")

                if st_g == "已命中": tag_c3.success(f"进球数双选：**已命中** ✅")
                elif st_g == "未命中": tag_c3.error(f"进球数双选：**未命中** ❌")
                else: tag_c3.info(f"进球数双选：**待结算**")

                if rec.get("audit_note"):
                    st.caption(f"💡 审计明细摘要：{rec.get('audit_note')}")
                st.markdown("---")
                
                c_in1, c_in2 = st.columns([2, 4])
                with c_in1:
                    score_input_val = st.text_input("终场比分（如 1-1）", value=rec.get("final_score", ""), key=f"score_in_{rec['id']}")
                with c_in2:
                    st.write("")
                    st.write("")
                    # 主核销按钮：点击后直接计算、存盘、刷新
                    if st.button("⚡ 依据此比分一键直接核销（推荐）", key=f"btn_local_{rec['id']}"):
                        target_s = score_input_val.strip()
                        if not target_s:
                            st.warning("⚠️ 请先在左侧输入终场比分（如 1-1）！")
                        else:
                            res, err_msg = evaluate_score_locally(rec.get("report", ""), target_s)
                            if err_msg:
                                st.error(err_msg)
                            else:
                                rec["final_score"] = res["final_score"]
                                rec["audit_1x2"] = res["audit_1x2"]
                                rec["audit_handicap"] = res["audit_handicap"]
                                rec["audit_goals"] = res["audit_goals"]
                                rec["status"] = res["status"]
                                rec["audit_note"] = f"【本地秒级核销】{res['summary']}"
                                save_history(st.session_state.records)
                                st.success(f"🎉 核销完成：【{res['status']}】")
                                time.sleep(0.3)
                                st.rerun()

                # 展开高级修改抽屉（仅在需要手动覆写时使用）
                with st.expander("🛠️ 手动覆写判定与联网查询", expanded=False):
                    adv_c1, adv_c2, adv_c3 = st.columns(3)
                    with adv_c1:
                        edit_1x2 = st.selectbox("欧盘判定", ["待结算", "已命中", "未命中"], 
                                                index=["待结算", "已命中", "未命中"].index(rec.get("audit_1x2", "待结算")), 
                                                key=f"ed_1x2_{rec['id']}")
                    with adv_c2:
                        edit_hand = st.selectbox("让球判定", ["待结算", "已命中", "未命中", "走盘"], 
                                                 index=["待结算", "已命中", "未命中", "走盘"].index(rec.get("audit_handicap", "待结算")), 
                                                 key=f"ed_hand_{rec['id']}")
                    with adv_c3:
                        edit_g = st.selectbox("进球数判定", ["待结算", "已命中", "未命中"], 
                                              index=["待结算", "已命中", "未命中"].index(rec.get("audit_goals", "待结算")), 
                                              key=f"ed_g_{rec['id']}")
                    
                    b_adv1, b_adv2 = st.columns(2)
                    with b_adv1:
                        if st.button("🌐 全自动查比分并核销", key=f"btn_search_{rec['id']}"):
                            if not gemini_api_key:
                                st.error("请先在侧边栏配置 Gemini API Key！")
                            else:
                                with st.spinner(f"正在全网检索完场比分..."):
                                    s_score, s_source = auto_search_score(gemini_api_key, rec.get("match", ""), rec.get("date", ""))
                                    if not s_score:
                                        st.warning(f"未能自动查得比分：{s_source}，请手动填入。")
                                    else:
                                        res, _ = evaluate_score_locally(rec.get("report", ""), s_score)
                                        rec["final_score"] = s_score
                                        rec["audit_1x2"] = res["audit_1x2"]
                                        rec["audit_handicap"] = res["audit_handicap"]
                                        rec["audit_goals"] = res["audit_goals"]
                                        rec["status"] = res["status"]
                                        rec["audit_note"] = f"【{s_source}】{res['summary']}"
                                        save_history(st.session_state.records)
                                        st.success(f"查得比分 {s_score}，核销成功：【{res['status']}】")
                                        time.sleep(0.3)
                                        st.rerun()
                    with b_adv2:
                        if st.button("💾 强制保存上述手动勾选", key=f"btn_save_{rec['id']}"):
                            rec["final_score"] = score_input_val.strip()
                            rec["audit_1x2"] = edit_1x2
                            rec["audit_handicap"] = edit_hand
                            rec["audit_goals"] = edit_g
                            hits = sum([1 for x in [edit_1x2, edit_hand, edit_g] if x == "已命中"])
                            if hits == 3: rec["status"] = "全红极佳 (3/3)"
                            elif hits == 2: rec["status"] = "双红达标 (2/3)"
                            elif hits == 1: rec["status"] = "单红偏离 (1/3)"
                            else: rec["status"] = "全黑盲区 (0/3)"
                            save_history(st.session_state.records)
                            st.success("已保存手动选择！")
                            time.sleep(0.3)
                            st.rerun()

# ----------------- Tab 3: 错题归因与自适应进化 -----------------
with tab3:
    st.subheader("🧠 错题归因与策略自我进化（AI 蒸馏与军规回灌中枢）")
    st.caption("分流定位【让球诱盘失误】、【进球数突变失误】与【欧盘冷门失误】，针对性逆向萃取避坑军规并直接回灌系统")

    handicap_fails = [r for r in st.session_state.records if r.get("audit_handicap") == "未命中"]
    goals_fails = [r for r in st.session_state.records if r.get("audit_goals") == "未命中"]
    ox_fails = [r for r in st.session_state.records if r.get("audit_1x2") == "未命中"]

    f_col1, f_col2, f_col3 = st.columns(3)
    f_col1.warning(f"让球未命中：**{len(handicap_fails)}** 场")
    f_col2.warning(f"进球数未命中：**{len(goals_fails)}** 场")
    f_col3.warning(f"欧盘未命中：**{len(ox_fails)}** 场")

    st.markdown("---")
    
    review_dim = st.radio("选择专项深度归因维度：", 
                          ["专项归因：让球盘失误（主攻做市商诱盘/阻盘识别）", "专项归因：进球数失误（主攻 Game-State 突变剧本）", "全维度综合解剖"],
                          horizontal=True)

    if st.button("🔥 启动工业级专项错题深度归因分析"):
        if not gemini_api_key:
            st.error("请先配置 Gemini API Key！")
        else:
            with st.spinner("AI 正在提取失误场次的盘口特征，定向提炼针对性避坑军规..."):
                cases = []
                target_records = []
                
                if "让球" in review_dim:
                    target_records = handicap_fails
                    focus_text = "重点深度审查：做市商浅盘诱热、假退盘阻击、升水诱下的微观操盘手法，为何让球盘失误？"
                elif "进球数" in review_dim:
                    target_records = goals_fails
                    focus_text = "重点深度审查：Game-State 比分突变连锁反应，弱队率先进球后强队压上反击对进球数的膨胀破坏力，为何进球数预估失真？"
                else:
                    target_records = [r for r in st.session_state.records if "全黑" in r.get("status", "") or "单红" in r.get("status", "")]
                    focus_text = "综合深度审查：三项中失误两项以上的全盘认知盲区。"

                if not target_records:
                    st.success("所选维度暂无失误样本，策略运行良好！")
                else:
                    for r in target_records[:5]:
                        cases.append(f"""
- 赛事：{r.get('match')}
- 终场比分：{r.get('final_score', '未知')}
- 独立核销：欧盘[{r.get('audit_1x2')}] | 让球[{r.get('audit_handicap')}] | 进球数[{r.get('audit_goals')}]
- 审计明细：{r.get('audit_note', '无')}
- 推演摘要：{r.get('report')[:350]}...
""")

                    review_prompt = f"""
你是一名资深体育量化对冲基金复盘专家。以下是量化模型近期失误的实战样本：

{''.join(cases)}

【定向审查重点】：
{focus_text}

请严格按以下工业化结构输出深度归因报告：
1. **偏差根因穿透**：失误究竟发生在数据层（伤停未识别）、博弈层（做市商操盘诱盘）、还是剧本突变层（比分突变导致大球膨胀）？
2. **专项防诱盘/防突变军规（提炼 3 条可直接执行的硬核规矩）**：必须用编号 1、2、3 输出精简具体的避坑约束。
3. **参数校准方案**：在后续推演中应如何调整置信度或下注纪律？
"""
                    review_result, model_used, err = call_gemini_engine(gemini_api_key, review_prompt)
                    if review_result:
                        st.session_state["latest_review"] = review_result
                        st.markdown(review_result)
                    else:
                        st.error(f"归因分析失败: {err}")

    if "latest_review" in st.session_state:
        st.markdown("---")
        st.markdown("#### 🚀 一键自适应进化回灌")
        new_rule_input = st.text_input("将上述提炼出的核心军规填入此处（例如：当机构临场从半球退平半且必发主胜占比超75%时严禁选让胜）")
        if st.button("💾 确认将此军规注入推演中枢"):
            if new_rule_input.strip():
                st.session_state.rules.append(new_rule_input.strip())
                save_rules(st.session_state.rules)
                st.success("🎉 军规已成功注入系统记忆库！下一次推演将强制执行此约束！")
                st.rerun()
            else:
                st.warning("请先填入军规内容！")
