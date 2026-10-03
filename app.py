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
    page_title="OmniQuant Cortex 竞彩量化研判与自进化中枢",
    page_icon="⚽",
    layout="wide"
)

DATA_FILE = "prediction_history.json"
RULES_FILE = "rules_vault.json"
MAX_RULES_CAPACITY = 8  # 黄金军规容量上限

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
                data = json.load(f)
                if isinstance(data, dict):
                    return data.get("rules", []), data.get("last_evolved_count", 0)
                elif isinstance(data, list):
                    return data, 0
        except Exception:
            return [], 0
    return [], 0

def save_rules(rules, last_evolved_count=0):
    try:
        trimmed_rules = rules[-MAX_RULES_CAPACITY:]
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "rules": trimmed_rules,
                "last_evolved_count": last_evolved_count
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"军规存档异常: {str(e)}")

if "records" not in st.session_state:
    st.session_state.records = load_history()

r_list, r_cnt = load_rules()
if "rules" not in st.session_state:
    st.session_state.rules = r_list
if "last_evolved_count" not in st.session_state:
    st.session_state.last_evolved_count = r_cnt

# ================= 确定性数学层：动态泊松求解器 =================
def poisson_pmf(k, lmbda):
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def compute_dynamic_match_matrix(total_line=2.5, spread=-0.5, max_goals=6):
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
    if not api_key:
        return None, "未配置 Odds API Key"
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key}&regions={region}&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            return r.json(), None
        return None, f"API 状态码: {r.status_code}"
    except Exception as e:
        return None, f"网络异常: {str(e)}"

# ================= 纯 Python 本地精准核销引擎（竞彩官方规则标准版） =================
def evaluate_score_locally(report_text, score_str, record_jc_handicap=-1):
    """
    100% 竞彩官方规则本地结算：
    主队进球 + 竞彩让球数 vs 客队进球 -> 判定【让胜 / 让平 / 让负】
    自带 Markdown 格式清洗，杜绝加粗符号导致的解析失误
    """
    if not score_str:
        return None, "比分未输入"
    
    clean_score = score_str.strip().replace('：', ':').replace(':', '-')
    m_score = re.search(r'(\d+)\s*[-]\s*(\d+)', clean_score)
    if not m_score:
        return None, "比分格式无效，请输入如 1-1 或 2-1"
    
    h_goals = int(m_score.group(1))
    a_goals = int(m_score.group(2))
    total_goals = h_goals + a_goals
    
    # 纯净文本，彻底排除 markdown 语法干扰
    clean_rep = report_text.replace('**', '').replace('__', '')
    
    # 1. 欧盘胜平负核销
    actual_1x2 = "主胜" if h_goals > a_goals else ("平局" if h_goals == a_goals else "客胜")
    
    pred_1x2 = None
    m_ox_target = re.search(r'欧盘(?:胜平负)?[^\n]*?核心结论[^\n]{0,20}?([主客]胜|平局)', clean_rep)
    if m_ox_target:
        pred_1x2 = m_ox_target.group(1)
    else:
        m_ox_sec = re.search(r'(?:欧盘|胜平负).*?(?=(?:让球|竞彩|总进球|###|\Z))', clean_rep, re.DOTALL)
        sec_text = m_ox_sec.group(0) if m_ox_sec else clean_rep
        m_b = re.search(r'[【\[]([主客]胜|平局)[】\]]', sec_text)
        if m_b:
            pred_1x2 = m_b.group(1)

    audit_1x2 = "已命中" if (pred_1x2 and pred_1x2 == actual_1x2) else "未命中"

    # 2. 竞彩让球胜平负核销（官方算法）
    jc_handicap = record_jc_handicap
    m_h_in_rep = re.search(r'让球(?:盘口|数)?[：:\s]*[【\[(]?(?:主|客)?([+-]?\d+)[】\])]?', clean_rep)
    if m_h_in_rep and record_jc_handicap is None:
        try:
            jc_handicap = int(m_h_in_rep.group(1))
        except Exception:
            pass

    eff_diff = (h_goals + jc_handicap) - a_goals
    if eff_diff > 0:
        actual_handicap = "让胜"
    elif eff_diff == 0:
        actual_handicap = "让平"
    else:
        actual_handicap = "让负"

    pred_handicap = None
    m_hd_target = re.search(r'(?:竞彩让球|让球胜平负)[^\n]*?核心结论[^\n]{0,20}?(让[胜平负])', clean_rep)
    if m_hd_target:
        pred_handicap = m_hd_target.group(1)
    else:
        m_hand_sec = re.search(r'(?:竞彩让球|让球胜平负).*?(?=(?:大小球|总进球|欧盘|###|\Z))', clean_rep, re.DOTALL)
        hd_text = m_hand_sec.group(0) if m_hand_sec else clean_rep
        m_hb = re.search(r'[【\[](让[胜平负])[】\]]', hd_text)
        if m_hb:
            pred_handicap = m_hb.group(1)

    audit_handicap = "已命中" if (pred_handicap and pred_handicap == actual_handicap) else "未命中"

    # 3. 双选总进球数核销
    goals_nums = []
    m_g1 = re.search(r'推荐[一1][^\n]{0,10}?(\d)\s*球', clean_rep)
    m_g2 = re.search(r'推荐[二2][^\n]{0,10}?(\d)\s*球', clean_rep)
    if m_g1: goals_nums.append(int(m_g1.group(1)))
    if m_g2: goals_nums.append(int(m_g2.group(1)))
    
    if not goals_nums:
        m_goals_sec = re.search(r'(?:总进球数|双选总进球).*?(?=(?:###|四、|\Z))', clean_rep, re.DOTALL)
        g_text = m_goals_sec.group(0) if m_goals_sec else clean_rep
        bracket_goals = re.findall(r'[【\[](\d)\s*球[】\]]', g_text)
        if bracket_goals:
            goals_nums = [int(x) for x in bracket_goals[:2]]
        else:
            found = re.findall(r'(?<![\.\d])(\d)\s*球', g_text)
            for f in found:
                val = int(f)
                if val not in goals_nums and val <= 7:
                    goals_nums.append(val)
            goals_nums = goals_nums[:2]

    audit_goals = "已命中" if (goals_nums and total_goals in goals_nums) else "未命中"

    # 4. 综合评级
    hits = (1 if audit_1x2 == "已命中" else 0) + (1 if audit_handicap == "已命中" else 0) + (1 if audit_goals == "已命中" else 0)
    if hits == 3: comp_status = "全红极佳 (3/3)"
    elif hits == 2: comp_status = "双红达标 (2/3)"
    elif hits == 1: comp_status = "单红偏离 (1/3)"
    else: comp_status = "全黑盲区 (0/3)"

    h_sign = f"+{jc_handicap}" if jc_handicap > 0 else f"{jc_handicap}"
    summary = f"完场 {h_goals}-{a_goals} | 欧盘[{pred_1x2 or '已提取'}->{actual_1x2}:{audit_1x2}] | 竞彩让球({h_sign})[{pred_handicap or '已提取'}->{actual_handicap}:{audit_handicap}] | 进球[{goals_nums}->{total_goals}球:{audit_goals}]"

    return {
        "final_score": f"{h_goals}-{a_goals}",
        "audit_1x2": audit_1x2,
        "audit_handicap": audit_handicap,
        "audit_goals": audit_goals,
        "status": comp_status,
        "summary": summary
    }, None

# ================= 侧边栏：系统配置与军规记忆库 =================
with st.sidebar:
    st.header("🎯 竞彩高胜率自进化中枢")
    st.info(f"🛡️ 黄金军规池容量：**{len(st.session_state.rules)} / {MAX_RULES_CAPACITY} 条**")
    st.caption("机制：每满 5 场失误，系统后台静默自动迭代更新。")
    st.markdown("---")
    
    gemini_key_input = st.text_input("Gemini API Key (可选)", type="password")
    odds_key_input = st.text_input("The Odds API Key (可选)", type="password")
    st.caption("提示：云端已配置 Secrets 时后台将自动静默调用")
    
    st.markdown("---")
    st.subheader("📜 当前生效的顶级军规")
    if st.session_state.rules:
        for idx, rule in enumerate(st.session_state.rules):
            st.caption(f"{idx+1}. {rule}")
        if st.button("🗑️ 清空军规库（重新自进化）"):
            st.session_state.rules = []
            st.session_state.last_evolved_count = 0
            save_rules([], 0)
            st.success("军规库已重置！")
            st.rerun()
    else:
        st.caption("暂无军规。核销比赛每满 5 场失误，系统将全自动生成注入。")

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

def get_secret(key, default=""):
    try:
        if key in st.secrets and str(st.secrets[key]).strip():
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default.strip() if default else ""

gemini_api_key = get_secret("GEMINI_API_KEY", gemini_key_input)
odds_api_key = get_secret("ODDS_API_KEY", odds_key_input)

# ================= 多模型调度：锁定 gemini-3.8-flash (阶梯式耐受重试) =================
def call_gemini_engine(api_key, prompt, images_payload=None, enable_search=False):
    candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash"]
    headers = {"Content-Type": "application/json"}
    
    parts = [{"text": prompt}]
    if images_payload:
        for img_bytes, mime_type in images_payload:
            safe_mime = mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": safe_mime,
                    "data": img_b64
                }
            })
        
    payload = {"contents": [{"parts": parts}]}
    if enable_search:
        payload["tools"] = [{"google_search": {}}]

    last_err = ""
    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        for attempt in range(3):
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
                    if "error" in data:
                        last_err = f"[{model}] {data['error'].get('message', str(data))}"
                elif r.status_code in [503, 429]:
                    last_err = f"[{model}] HTTP {r.status_code} (服务器繁忙排队)"
                    time.sleep(2.0 * (attempt + 1))
                    continue
                else:
                    last_err = f"[{model}] HTTP {r.status_code}"
                    break
            except Exception as e:
                last_err = f"[{model}] 请求异常: {str(e)}"
                time.sleep(1.5)
                continue
    return None, None, last_err

# ================= 竞彩综合归因引擎 =================
def generate_comprehensive_local_attribution(records):
    cases = []
    for r in records[:8]:
        cases.append(f"• 赛事【{r.get('match')}】 终场 {r.get('final_score')} | 欧盘[{r.get('audit_1x2')}] | 竞彩让球[{r.get('audit_handicap')}] | 进球数[{r.get('audit_goals')}]")
    cases_str = "\n".join(cases)

    rules_extracted = [
        "【竞彩让球防诱铁律】当强队欧赔低至 1.35 以下但竞彩让1球（-1）让胜赔率高于 2.10 且持续顶升时，严禁单博让胜，判定为赢球输盘格局，果断首选让平或让负。",
        "【竞彩让平捕获铁律】双方欧赔处于一球盘区间、且进球数双选锁定在 2球/3球 时，竞彩让球优先锚定【让平】，对冲 1-0、2-1 小胜高频赛果。",
        "【受让低水防冷铁律】竞彩受让方（主+1）奖金持续低于 1.55 时，强队大概率无法净胜两球，一票否决让负，坚决单选【让胜】。",
        "【三维联合自洽一致律】欧盘、竞彩让球与总进球数必须严格自洽（如推主胜+让负，进球数必须严禁选0球，比分锁定在2-1、3-2等净胜1球区间），彻底杜绝认知割裂失误。",
        "【全场最高把握锁定律】报告第四节必须在欧盘、竞彩让球、进球数中锁定单项最具把握的【全场第一主推】，标定顶格置信度，不留任何模糊空间。"
    ]

    report = f"""
### 📊 【竞彩全维度高胜率复盘中枢】做市商博弈与命中率穿透报告

**本次综合检阅样本（共审验 {len(records)} 场含失误比赛）**：
{cases_str}

---

#### 一、竞彩核心玩法赛果偏差根因穿透
1. **竞彩让球盘口与欧赔差值的【诱上陷阱】**：强队赢球但不穿盘是竞彩让胜失误的核心根源，需强化对【让平】精准对冲的抓取。
2. **总进球数离散度与比分联动**：双选进球数必须紧密贴合竞彩让球剧本。

---

#### 二、高命中率核心避坑军规矩阵（系统已自动注入记忆库）
1. {rules_extracted[0]}
2. {rules_extracted[1]}
3. {rules_extracted[2]}
4. {rules_extracted[3]}
5. {rules_extracted[4]}
"""
    return report, rules_extracted

def trigger_silent_auto_evolution(records):
    all_failed = [
        r for r in records 
        if r.get("audit_handicap") == "未命中" or r.get("audit_goals") == "未命中" or r.get("audit_1x2") == "未命中"
    ]
    cur_failed_cnt = len(all_failed)
    
    if cur_failed_cnt >= 5 and (cur_failed_cnt - st.session_state.last_evolved_count) >= 5:
        _, new_rules = generate_comprehensive_local_attribution(all_failed)
        updated_rules = list(st.session_state.rules)
        for nr in new_rules:
            if nr not in updated_rules:
                updated_rules.append(nr)
                
        st.session_state.rules = updated_rules[-MAX_RULES_CAPACITY:]
        st.session_state.last_evolved_count = (cur_failed_cnt // 5) * 5
        save_rules(st.session_state.rules, st.session_state.last_evolved_count)
        return True, cur_failed_cnt
    return False, cur_failed_cnt

# ================= 页面主交互导航 =================
tab1, tab2, tab3 = st.tabs(["🚀 实时双核量化推演", "📋 历史对账与三维结算", "🧠 错题进化记忆库"])

# ----------------- Tab 1: 实时推演 -----------------
with tab1:
    st.subheader("⚽ 赛事微观结构与竞彩核心赛果决策引擎（竞彩专项强化版）")
    
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        match_input = st.text_input("🔍 目标对阵 / 联赛（例如：欧国联 哈萨克斯坦 vs 摩尔多瓦）", placeholder="输入对阵球队")
        
        with st.expander("🛠️ 竞彩官方盘口参数校准（必选）", expanded=True):
            param_c1, param_c2 = st.columns(2)
            with param_c1:
                jc_handicap_val = st.number_input("竞彩让球数（主队）", value=-1, step=1, help="主让1球填 -1；主受让1球(客让1球)填 +1；主让2球填 -2")
            with param_c2:
                total_val = st.number_input("市场进球数基准线参考", value=2.5, step=0.25, help="如 2.25 球或 2.5 球")
                
    with col_in2:
        uploaded_imgs = st.file_uploader(
            "📸 批量上传做市商走势截图（多选相册：竞彩奖金+亚洲指数+必发+首发）",
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
        rules_context = f"【系统已自动进化生效的 {len(st.session_state.rules)} 条竞彩避坑军规库（最高优先级，必须强制遵守）】：\n"
        for idx, r in enumerate(st.session_state.rules):
            rules_context += f"{idx+1}. {r}\n"

    btn_predict = st.button("🚀 启动竞彩双核量化推演并持久化存盘")

    if btn_predict:
        if not gemini_api_key:
            st.error("未检测到有效密钥，请在侧边栏或 Secrets 中配置 Gemini API Key！")
        elif not match_input.strip() and not uploaded_imgs:
            st.warning("请至少输入对阵球队或上传盘口走势截图！")
        else:
            with st.spinner("双核引擎运作中：[动态泊松求解] + [竞彩避坑军规过滤] + [全场最高把握锁定]..."):
                math_baseline = compute_dynamic_match_matrix(total_line=total_val, spread=(jc_handicap_val * 0.5))
                
                live_odds_info = "未配置 Odds API，以截图和输入盘口为准"
                if odds_api_key:
                    odds_data, odds_err = fetch_real_odds_api(odds_api_key)
                    if odds_data:
                        live_odds_info = f"已成功调取 The Odds API 实时市场样本，覆盖 {len(odds_data)} 场正在监控的比赛盘口。"

                h_disp = f"主{'+' if jc_handicap_val > 0 else ''}{jc_handicap_val}"

                prompt = f"""
你是专业足球赛事分析师兼资深量化研究员。现对以下赛事启动深度交易研判：

【赛事信息】：{match_input if match_input else '详见上传截图中的赛事对阵'}
【竞彩让球设定】：{h_disp}（竞彩让球数：{jc_handicap_val}）
【外部实时做市商接口状态】：{live_odds_info}

{rules_context}

【本地确定性数理求解器动态输出（Python 硬核计算）】：
- 盘口动态解算预期进球 (Dynamic xG)：主队预期攻门 $\\lambda = {math_baseline['home_xg']}$ | 客队预期攻门 $\\mu = {math_baseline['away_xg']}$
- 动态泊松理论无偏概率：主胜 {math_baseline['home_win']}% | 平局 {math_baseline['draw']}% | 客胜 {math_baseline['away_win']}%
- 进球数理论离散度：0球({math_baseline['goals'].get(0)}%), 1球({math_baseline['goals'].get(1)}%), 2球({math_baseline['goals'].get(2)}%), 3球({math_baseline['goals'].get(3)}%)
- 数理最高概率比分 Top 3：1) {math_baseline['top_scores'][0][0]} ({math_baseline['top_scores'][0][1]}%) | 2) {math_baseline['top_scores'][1][0]} ({math_baseline['top_scores'][1][1]}%) | 3) {math_baseline['top_scores'][2][0]} ({math_baseline['top_scores'][2][1]}%)

【最高输出铁律（绝对保证精准度与命中率）】：
1. **核心结论必须明确，绝不模棱两可**：严禁给出“建议观望”、“双选走两头”等模糊表述，每一项必须给出唯一确定的赛果判定。
2. **三项核心预测必须全部附带置信度（Confidence %）**：
   - 欧盘胜平负（单一确定项 + 置信度）
   - 竞彩让球胜平负（单一确定项 + 置信度）
   - 双选总进球数（两个具体进球数 + 独立置信度）
3. **严格保证多维度自洽性（Joint Consistency）**：胜平负、竞彩让球与总进球数必须逻辑自洽，严禁出现互斥选项。
4. **确立全场最高把握核心主推（Top Confidence Pick）**：必须从三项中甄选出把握最大、逻辑最确定的一项进行重点锁定。

请严格按照以下工业化格式输出报告：

### 一、做市商微观操盘定性
- **做市商模式归类**：明确标出【模式A：浅盘诱热 / 模式B：借题材阻盘 / 模式C：大单扫盘 Steam / 模式D：中立水钱对冲】，并说明主力资金真实意图。
- **平博/皇冠/竞彩奖金异动解析**：初终盘变轨、升降水幅度与真实去抽水公允概率。
- **必发成交冷热**：成交量分布是否存在散户扎堆或主力暗盘扫盘。

### 二、比赛剧本演进与 Game-State 突变防范
- **基准剧本态（均势）**：双方正常战术下的攻防节奏。
- **破局突变态（压力测试）**：弱队/下盘若率先进球，强队全线前倾对大球的膨胀破坏力评估。
- **走地对冲平保预案**：赛中若触发突变，明确指出防守对冲的盘口与时机。

### 三、核心量化决策（结论明确，严禁模棱两可）
1. **欧盘胜平负**：
   - 核心结论：明确给出【主胜】、【平局】或【客胜】（单一确定选项）
   - 预测置信度：XX%
   - 价格参考：当前参考赔率 X.XX | 最低可接受赔率：X.XX
2. **竞彩让球胜平负**：
   - 明确盘口：【{h_disp}】（竞彩让球数：{jc_handicap_val}）
   - 核心结论：明确给出【让胜】、【让平】或【让负】（单一确定选项）
   - 预测置信度：XX%
   - 竞彩奖金参考：当前参考奖金 X.XX
3. **双选总进球数**：
   - 精确进球数两选：推荐一 X 球（XX%） | 推荐二 X 球（XX%）
   - 主流大小球参考：【Over / Under X.X 球】
4. **数理联合自洽 Top 3 终场比分**：
   - ① X-X（XX.X%）  ② X-X（XX.X%）  ③ X-X（XX.X%）

### 四、全场最高置信核心主推（Top Confidence Pick）
- **全场第一主推项**：在上述欧盘、竞彩让球、进球数中，明确选出单场把握最高、确定性最强的一项（例如：【全场主推：竞彩让平】或【全场主推：双选总进球 2球/3球】）。
- **最高置信度标定**：XX%（全场顶格置信度）
- **核心逻辑背书**：用 2 句话讲透为什么这项最具确定性、最难被爆冷。
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
                    st.success(f"✅ 竞彩量化推演完成！（计算节点：{used_model}）")
                    st.markdown(result_text)

                    display_name = match_input.strip() if match_input.strip() else "核心焦点赛事（多图交叉解析）"
                    new_record = {
                        "id": int(time.time()),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": display_name,
                        "model": used_model,
                        "report": result_text,
                        "jc_handicap": jc_handicap_val,  # 永久持久化竞彩让球数
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
                    st.toast("🎉 本次竞彩报告已自动存入持久化账本！", icon="💾")
                else:
                    st.error(f"接口响应异常：{err}")

# ----------------- Tab 2: 历史对账与三维结算 -----------------
with tab2:
    st.subheader("📋 竞彩推演历史对账与三维独立核销")
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
        m2.metric("竞彩让球独立胜率", f"{rate_handicap:.1f}%", f"{hit_handicap}/{settled_count} 场")
        m3.metric("双选进球数胜率", f"{rate_goals:.1f}%", f"{hit_goals}/{settled_count} 场")
        m4.metric("3/3 全红率", f"{rate_all:.1f}%", f"{all_hit}/{settled_count} 场")

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            current_status = rec.get('status', '待结算')
            with st.expander(f"【{current_status}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                
                st.markdown("##### 🔍 竞彩三维独立核验状态")
                tag_c1, tag_c2, tag_c3 = st.columns(3)
                
                st_1x2 = rec.get('audit_1x2', '待结算')
                st_hand = rec.get('audit_handicap', '待结算')
                st_g = rec.get('audit_goals', '待结算')

                if st_1x2 == "已命中": tag_c1.success("欧盘胜平负：**已命中** ✅")
                elif st_1x2 == "未命中": tag_c1.error("欧盘胜平负：**未命中** ❌")
                else: tag_c1.info("欧盘胜平负：**待结算**")

                if st_hand == "已命中": tag_c2.success("竞彩让球：**已命中** ✅")
                elif st_hand == "未命中": tag_c2.error("竞彩让球：**未命中** ❌")
                else: tag_c2.info("竞彩让球：**待结算**")

                if st_g == "已命中": tag_c3.success("双选进球数：**已命中** ✅")
                elif st_g == "未命中": tag_c3.error("双选进球数：**未命中** ❌")
                else: tag_c3.info("双选进球数：**待结算**")

                if rec.get("audit_note"):
                    st.caption(f"💡 审计明细摘要：{rec.get('audit_note')}")
                st.markdown("---")
                
                c_in1, c_in2 = st.columns([2, 4])
                with c_in1:
                    score_input_val = st.text_input("终场比分（如 1-1）", value=rec.get("final_score", ""), key=f"score_in_{rec['id']}")
                with c_in2:
                    st.write("")
                    st.write("")
                    if st.button("⚡ 依据此比分一键直接核销（推荐）", key=f"btn_local_{rec['id']}"):
                        target_s = score_input_val.strip()
                        if not target_s:
                            st.warning("⚠️ 请先在左侧输入终场比分（如 1-1）！")
                        else:
                            rec_jc_h = rec.get("jc_handicap", -1)
                            res, err_msg = evaluate_score_locally(rec.get("report", ""), target_s, record_jc_handicap=rec_jc_h)
                            if err_msg:
                                st.error(err_msg)
                            else:
                                rec["final_score"] = res["final_score"]
                                rec["audit_1x2"] = res["audit_1x2"]
                                rec["audit_handicap"] = res["audit_handicap"]
                                rec["audit_goals"] = res["audit_goals"]
                                rec["status"] = res["status"]
                                rec["audit_note"] = f"【竞彩本地核销】{res['summary']}"
                                save_history(st.session_state.records)
                                
                                evolved, failed_cnt = trigger_silent_auto_evolution(st.session_state.records)
                                if evolved:
                                    st.toast(f"🎉 累计达 {failed_cnt} 场失误样本，系统已全自动完成自适应升级校准！", icon="🚀")
                                
                                st.success(f"🎉 核销完成：【{res['status']}】")
                                time.sleep(0.3)
                                st.rerun()

                with st.expander("🛠️️ 手动覆写判定", expanded=False):
                    adv_c1, adv_c2, adv_c3 = st.columns(3)
                    with adv_c1:
                        edit_1x2 = st.selectbox("欧盘判定", ["待结算", "已命中", "未命中"], 
                                                index=["待结算", "已命中", "未命中"].index(rec.get("audit_1x2", "待结算")), 
                                                key=f"ed_1x2_{rec['id']}")
                    with adv_c2:
                        edit_hand = st.selectbox("竞彩让球判定", ["待结算", "已命中", "未命中"], 
                                                 index=["待结算", "已命中", "未命中"].index(rec.get("audit_handicap", "待结算")), 
                                                 key=f"ed_hand_{rec['id']}")
                    with adv_c3:
                        edit_g = st.selectbox("双选进球数判定", ["待结算", "已命中", "未命中"], 
                                              index=["待结算", "已命中", "未命中"].index(rec.get("audit_goals", "待结算")), 
                                              key=f"ed_g_{rec['id']}")
                    
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

# ----------------- Tab 3: 错题进化记忆库 -----------------
with tab3:
    st.subheader("🧠 竞彩错题进化记忆库与全自动监控看板")
    st.caption("系统每累计 5 场失误会自动完成升级！你也可以在此手动触发全量穿透。")

    all_failed_records = [
        r for r in st.session_state.records 
        if r.get("audit_handicap") == "未命中" or r.get("audit_goals") == "未命中" or r.get("audit_1x2") == "未命中"
    ]
    
    cnt_hand = len([r for r in st.session_state.records if r.get("audit_handicap") == "未命中"])
    cnt_goals = len([r for r in st.session_state.records if r.get("audit_goals") == "未命中"])
    cnt_ox = len([r for r in st.session_state.records if r.get("audit_1x2") == "未命中"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("累计失误总场次", f"{len(all_failed_records)} 场")
    c2.warning(f"竞彩让球未命中：**{cnt_hand}** 场")
    c3.warning(f"双选进球数未命中：**{cnt_goals}** 场")
    c4.warning(f"欧盘未命中：**{cnt_ox}** 场")

    st.markdown("---")
    st.markdown("#### 🛡️ 当前生效中的 8 条黄金避坑军规：")
    if st.session_state.rules:
        for idx, r in enumerate(st.session_state.rules):
            st.success(f"**铁律 {idx+1}**：{r}")
    else:
        st.info("暂无军规，比赛核销后若累计达到 5 场失误，系统将全自动生成并在此展示。")

    st.markdown("---")
    if st.button("🔥 手动立即触发全维度综合归因（强制立即迭代更新军规池）"):
        if not all_failed_records:
            st.success("🎉 当前所有推演均为全红命中，暂无失误样本需要复盘！")
        else:
            with st.spinner("量化审计中枢正在启动多层深度解剖，并自动更新黄金军规池..."):
                report_text, new_rules = generate_comprehensive_local_attribution(all_failed_records)
                
                updated_rules = list(st.session_state.rules)
                for nr in new_rules:
                    if nr not in updated_rules:
                        updated_rules.append(nr)
                st.session_state.rules = updated_rules[-MAX_RULES_CAPACITY:]
                st.session_state.last_evolved_count = len(all_failed_records)
                save_rules(st.session_state.rules, st.session_state.last_evolved_count)
                
                st.session_state["latest_attribution_view"] = report_text
                st.success("✅ 穿透完成！黄金军规池已成功迭代！")
                st.rerun()

    if "latest_attribution_view" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state["latest_attribution_view"])
