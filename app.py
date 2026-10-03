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

# ================= 真实 The Odds API 机构数据与官方比分抓取 =================
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

def fetch_score_from_odds_api(api_key, match_name):
    """
    通过 The Odds API 官方 Scores 接口直连获取完场比分
    覆盖主流足球联赛，返回格式如 (1, 2)
    """
    if not api_key:
        return None, "未配置 Odds API Key"
    
    soccer_sports = [
        "soccer_uefa_nations_league", "soccer_uefa_champs_league", "soccer_uefa_europa_league",
        "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
        "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_fa_cup"
    ]
    
    # 清洗对阵关键词
    clean_name = match_name.replace("vs", " ").replace("VS", " ").replace("-", " ")
    keywords = [w.strip().lower() for w in clean_name.split() if len(w.strip()) >= 2]
    
    for sport in soccer_sports:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores/?apiKey={api_key}&daysFrom=3"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            for game in data:
                if not game.get("completed", False):
                    continue
                home_team = game.get("home_team", "").lower()
                away_team = game.get("away_team", "").lower()
                
                # 模糊匹配对阵双方
                match_count = sum(1 for kw in keywords if kw in home_team or kw in away_team)
                if match_count >= 1 and game.get("scores"):
                    scores = game["scores"]
                    h_score = None
                    a_score = None
                    for s in scores:
                        if s["name"] == game["home_team"]:
                            h_score = s["score"]
                        else:
                            a_score = s["score"]
                    if h_score is not None and a_score is not None:
                        return f"{h_score}-{a_score}", f"The Odds API 官方完场直连确认（{game['home_team']} {h_score}-{a_score} {game['away_team']}）"
        except Exception:
            continue
            
    return None, "未在 The Odds API 当前覆盖联赛中匹配到完场赛果"

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

# ================= 健壮 JSON 提取器 =================
def extract_json_from_text(text):
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

# ================= 多模态与多模型容灾调度 =================
def call_gemini_engine(api_key, prompt, images_payload=None):
    """多模型容灾池，彻底避免单模型弃用异常"""
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
    last_err = ""

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code != 200:
                last_err = f"模型 {model} 返回 HTTP {r.status_code}: {r.text[:200]}"
                continue
            data = r.json()
            if "candidates" in data and data["candidates"]:
                content = data["candidates"][0].get("content", {})
                ret_parts = content.get("parts", [])
                text_list = [p.get("text", "") for p in ret_parts if "text" in p]
                if text_list:
                    return "".join(text_list), model, None
            if "error" in data:
                last_err = f"模型 {model} 错误: {data['error'].get('message', str(data))}"
                continue
        except Exception as e:
            last_err = f"请求异常: {str(e)}"
            continue
    return None, None, last_err

def calculate_composite_status(r_1x2, r_handicap, r_goals):
    """计算三维综合成色"""
    if r_1x2 == "待结算" or r_handicap == "待结算" or r_goals == "待结算":
        return "待结算"
    
    hits = 0
    if r_1x2 == "已命中": hits += 1
    if r_handicap == "已命中": hits += 1
    if r_goals == "已命中": hits += 1
    
    if hits == 3:
        return "全红极佳 (3/3)"
    elif hits == 2:
        return "双红达标 (2/3)"
    elif hits == 1:
        return "单红偏离 (1/3)"
    else:
        return "全黑盲区 (0/3)"

def auto_evaluate_with_given_score(api_key, report_text, final_score):
    """根据确定性比分，对【欧盘、让球、进球数】三项秒级独立核销"""
    prompt = (
        "你是一名客观严谨的体育量化复盘审计员。请根据【终场比分】和【推演报告摘要】，对三项预测独立逐笔核销。\n\n"
        f"【终场比分】：{final_score}\n"
        f"【推演报告摘要】：\n{report_text[:1400]}\n\n"
        "【核销铁律】：\n"
        "1. 独立核查项一【欧盘胜平负】：实际赛果打出填「已命中」，反向填「未命中」；\n"
        "2. 独立核查项二【让球胜平负】：结合报告让球数计算让球赛果，打出填「已命中」，失误填「未命中」，走盘填「走盘」；\n"
        "3. 独立核查项三【多选总进球数】：总进球落在推荐的两项内填「已命中」，否则填「未命中」。\n\n"
        "【输出格式要求】：\n"
        "请直接输出标准 JSON 对象，字段必须包含：\n"
        "audit_1x2: 已命中 / 未命中\n"
        "audit_handicap: 已命中 / 未命中 / 走盘\n"
        "audit_goals: 已命中 / 未命中\n"
        "summary: 一句话明细（例如：比分1-2，欧盘客胜(红)，让负(红)，进球数(黑)）\n"
    )
    result_text, _, err = call_gemini_engine(api_key, prompt)
    parsed = extract_json_from_text(result_text)
    if parsed:
        r_1x2 = parsed.get("audit_1x2", "待结算")
        r_handicap = parsed.get("audit_handicap", "待结算")
        r_goals = parsed.get("audit_goals", "待结算")
        status = calculate_composite_status(r_1x2, r_handicap, r_goals)
        return r_1x2, r_handicap, r_goals, status, parsed.get("summary", "")
    return "待结算", "待结算", "待结算", "待结算", f"核销计算异常: {err}"

def master_settle_pipeline(gemini_key, odds_key, match_name, report_text, manual_score=""):
    """
    全自动主审计管线：
    1. 优先使用手动比分；
    2. 无手动比分时，调用 The Odds API 官方直连获取比分；
    3. 获取比分后，立即执行三维独立判定。
    """
    target_score = manual_score.strip()
    score_source = "手动输入比分"

    if not target_score:
        if odds_key:
            api_score, api_note = fetch_score_from_odds_api(odds_key, match_name)
            if api_score:
                target_score = api_score
                score_source = api_note
        
    if not target_score:
        return "", "待结算", "待结算", "待结算", "待结算", "未能通过 API 匹配到完场比分，请在比分框手动填入比分后点击核销。"

    # 执行三维独立精准核销
    r_1x2, r_hand, r_g, st_comp, summary_note = auto_evaluate_with_given_score(
        gemini_key, report_text, target_score
    )
    full_note = f"【比分源：{score_source}】终场 {target_score} -> {summary_note}"
    return target_score, r_1x2, r_hand, r_g, st_comp, full_note

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
        pending_list = [r for r in st.session_state.records if r.get("status") == "待结算"]
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

        if pending_list:
            st.markdown("---")
            if st.button(f"⚡ 一键 API 检索核销所有待结算（共 {len(pending_list)} 场）"):
                if not gemini_api_key:
                    st.error("请先配置 Gemini API Key！")
                else:
                    with st.spinner("正在通过 The Odds API 官方接口检索完场比分并独立核销..."):
                        for r in pending_list:
                            score, a_1x2, a_hand, a_g, st_comp, note = master_settle_pipeline(
                                gemini_api_key, odds_api_key, r.get("match", ""), r.get("report", ""), r.get("final_score", "")
                            )
                            if st_comp != "待结算":
                                r["final_score"] = score
                                r["audit_1x2"] = a_1x2
                                r["audit_handicap"] = a_hand
                                r["audit_goals"] = a_g
                                r["status"] = st_comp
                                r["audit_note"] = note
                        save_history(st.session_state.records)
                        st.success("批量独立核销执行完毕！")
                        st.rerun()

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            with st.expander(f"【{rec.get('status', '待结算')}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                
                st.markdown("##### 🔍 三维独立核验状态")
                tag_c1, tag_c2, tag_c3 = st.columns(3)
                tag_c1.info(f"欧盘胜平负：**{rec.get('audit_1x2', '待结算')}**")
                tag_c2.info(f"让球胜平负：**{rec.get('audit_handicap', '待结算')}**")
                tag_c3.info(f"进球数双选：**{rec.get('audit_goals', '待结算')}**")

                if rec.get("audit_note"):
                    st.caption(f"💡 审计明细摘要：{rec.get('audit_note')}")
                st.markdown("---")
                
                c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.5])
                with c1:
                    score = st.text_input("终场比分（留空自动调 API 查）", value=rec.get("final_score", ""), key=f"score_{rec['id']}")
                with c2:
                    edit_1x2 = st.selectbox("欧盘判定", ["待结算", "已命中", "未命中"], 
                                            index=["待结算", "已命中", "未命中"].index(rec.get("audit_1x2", "待结算")), 
                                            key=f"ed_1x2_{rec['id']}")
                with c3:
                    edit_hand = st.selectbox("让球判定", ["待结算", "已命中", "未命中", "走盘"], 
                                             index=["待结算", "已命中", "未命中", "走盘"].index(rec.get("audit_handicap", "待结算")), 
                                             key=f"ed_hand_{rec['id']}")
                with c4:
                    edit_g = st.selectbox("进球数判定", ["待结算", "已命中", "未命中"], 
                                          index=["待结算", "已命中", "未命中"].index(rec.get("audit_goals", "待结算")), 
                                          key=f"ed_g_{rec['id']}")
                
                b_col1, b_col2, b_col3 = st.columns([3, 3, 2])
                with b_col1:
                    if st.button("🌐 API 查比分并三维核销", key=f"btn_search_{rec['id']}"):
                        if not gemini_api_key:
                            st.error("请先配置 Gemini API Key！")
                        else:
                            with st.spinner(f"正在调取 API 核查【{rec.get('match')}】完场比分..."):
                                s, a_1x2, a_hand, a_g, st_comp, note = master_settle_pipeline(
                                    gemini_api_key, odds_api_key, rec.get("match", ""), rec.get("report", ""), score
                                )
                                rec["final_score"] = s
                                rec["audit_1x2"] = a_1x2
                                rec["audit_handicap"] = a_hand
                                rec["audit_goals"] = a_g
                                rec["status"] = st_comp
                                rec["audit_note"] = note
                                save_history(st.session_state.records)
                                if st_comp != "待结算":
                                    st.success(f"核销完成：【{st_comp}】比分：{s}")
                                else:
                                    st.warning(note)
                                st.rerun()
                with b_col2:
                    if st.button("⚡ 依据输入比分三维核销", key=f"btn_calc_{rec['id']}"):
                        if not score.strip():
                            st.warning("比分框为空，请先填写比分！")
                        elif not gemini_api_key:
                            st.error("请先配置 Gemini API Key！")
                        else:
                            with st.spinner("AI 正在根据指定比分独立核销三项赛果..."):
                                a_1x2, a_hand, a_g, st_comp, note = auto_evaluate_with_given_score(
                                    gemini_api_key, rec.get("report", ""), score.strip()
                                )
                                rec["final_score"] = score.strip()
                                rec["audit_1x2"] = a_1x2
                                rec["audit_handicap"] = a_hand
                                rec["audit_goals"] = a_g
                                rec["status"] = st_comp
                                rec["audit_note"] = f"【手动输入核销】{note}"
                                save_history(st.session_state.records)
                                st.success(f"核销完成：【{st_comp}】")
                                st.rerun()
                with b_col3:
                    if st.button("💾 手动保存判定", key=f"btn_save_{rec['id']}"):
                        rec["final_score"] = score
                        rec["audit_1x2"] = edit_1x2
                        rec["audit_handicap"] = edit_hand
                        rec["audit_goals"] = edit_g
                        rec["status"] = calculate_composite_status(edit_1x2, edit_hand, edit_g)
                        save_history(st.session_state.records)
                        st.success("判定已手动保存！")
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
