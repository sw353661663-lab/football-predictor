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
    page_title="OmniQuant 工业级足球量化预测中枢",
    page_icon="⚽",
    layout="wide"
)

DATA_FILE = "prediction_history.json"

# ================= 数据持久化层 =================
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
        st.error(f"数据存档异常: {str(e)}")

if "records" not in st.session_state:
    st.session_state.records = load_history()

# ================= 纯 Python 确定性数学求解器 =================
def poisson_pmf(k, lmbda):
    """计算单个进球数的泊松概率"""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def compute_match_probabilities(home_xg=1.40, away_xg=1.10, max_goals=6):
    """通过双变量泊松网格计算 1X2 与进球数无偏概率矩阵"""
    prob_home_win = 0.0
    prob_draw = 0.0
    prob_away_win = 0.0
    total_goals_dist = {i: 0.0 for i in range(max_goals * 2 + 1)}

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

    return {
        "home_win": round(prob_home_win * 100, 2),
        "draw": round(prob_draw * 100, 2),
        "away_win": round(prob_away_win * 100, 2),
        "goals": {k: round(v * 100, 2) for k, v in total_goals_dist.items() if k <= 6}
    }

# ================= 侧边栏：系统管理 =================
with st.sidebar:
    st.header("⚙️ 量化配置与风控")
    bankroll = st.number_input("实战风控总本金 (单位: 元/USD)", min_value=1000, value=20000, step=1000)
    st.caption("基于 0.25x 凯利准则自动计算单场建议开仓金额")
    st.markdown("---")
    gemini_key_input = st.text_input("Gemini API Key (可选)", type="password")
    odds_key_input = st.text_input("The Odds API Key (可选)", type="password")
    st.caption("提示：云端已配置 Secrets 时后台将自动静默调用")
    st.markdown("---")
    st.subheader("💾 数据库冷备份")
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
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

# ================= 多模态与联网搜索推理调度 =================
def call_gemini_engine(api_key, prompt, images_payload=None, enable_search=False):
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
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
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            data = r.json()
            if "candidates" in data and data["candidates"]:
                content = data["candidates"][0].get("content", {})
                ret_parts = content.get("parts", [])
                text_list = [p.get("text", "") for p in ret_parts if "text" in p]
                if text_list:
                    return "".join(text_list), model, None
            if "error" in data:
                if data["error"].get("code") in [503, 429]:
                    time.sleep(1)
                    continue
                last_err = data["error"].get("message", str(data))
        except Exception as e:
            last_err = str(e)
            continue
    return None, None, last_err

def auto_search_and_settle(api_key, match_name, match_date, report_text):
    """通过 Google 联网搜索比分并全自动核销"""
    prompt = (
        "你是一名绝对客观的体育赛事官方核销审计员，拥有实时联网搜索权限。\n\n"
        "【任务指令】：\n"
        f"1. 请立即通过 Google 搜索查找以下赛事的官方终场比分（全场完赛比分）：\n"
        f"   - 对阵双方：{match_name}\n"
        f"   - 推演记录时间：{match_date}\n"
        "2. 若比赛尚未开打或进行中，状态标记为「待结算」，比分填「待定」。\n"
        "3. 若比赛已完赛：\n"
        "   - 提取真实终场比分（如 1-2）；\n"
        "   - 对照下方推演报告摘要，比对欧盘胜平负、让球胜平负、进球数两选；\n"
        "   - 严格核销：核心让球或欧盘打出为「已命中」，反向失误为「未命中」，整数盘为「走盘」。\n\n"
        f"【历史推演报告摘要】：\n{report_text[:1400]}\n\n"
        "【输出格式要求】：\n"
        "请直接输出标准 JSON 对象，字段必须包含：\n"
        "final_score: 实际完赛比分(如 1-2，未开赛填 待定)\n"
        "status: 已命中 / 未命中 / 走盘 / 待结算\n"
        "summary: 一句话判定明细（例如：联网检索终场比分 1-2，客胜打出，让负命中）\n"
    )
    result_text, _, err = call_gemini_engine(api_key, prompt, enable_search=True)
    parsed = extract_json_from_text(result_text)
    if parsed:
        return parsed.get("final_score", ""), parsed.get("status", "待结算"), parsed.get("summary", "")
    return "", "待结算", f"联网检索核销异常: {err}"

def auto_evaluate_with_given_score(api_key, report_text, final_score):
    """已有明确比分时，秒级智能核销"""
    prompt = (
        "你是一名客观的体育量化复盘审计员。请根据【终场比分】和【推演报告摘要】，精确核销赛果。\n\n"
        f"【终场比分】：{final_score}\n"
        f"【推演报告摘要】：\n{report_text[:1400]}\n\n"
        "【核算规则】：\n"
        "1. 结算终场胜负平、让球盘后赛果、双方总进球数。\n"
        "2. 对照报告结论：核心让球或欧盘打出为「已命中」，反向失误为「未命中」，走盘为「走盘」。\n\n"
        "【输出格式要求】：\n"
        "请直接输出标准 JSON 对象，包含字段：status（已命中/未命中/走盘）和 summary（判定明细字符串）。\n"
    )
    result_text, _, err = call_gemini_engine(api_key, prompt, enable_search=False)
    parsed = extract_json_from_text(result_text)
    if parsed:
        return parsed.get("status", "待结算"), parsed.get("summary", "")
    return "待结算", f"核销计算异常: {err}"

# ================= 页面主交互导航 =================
tab1, tab2, tab3 = st.tabs(["🚀 实时双核量化推演", "📋 历史对账与 CLV 结算", "🧠 错题归因与策略进化"])

# ----------------- Tab 1: 实时推演 -----------------
with tab1:
    st.subheader("⚽ 赛事微观结构与剧本突变决策引擎（终极量化版）")
    
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        match_input = st.text_input("🔍 目标对阵 / 联赛（留空可自动抓取今日焦点赛）", placeholder="如：欧国联 哈萨克斯坦 vs 摩尔多瓦（可留空）")
    with col_in2:
        uploaded_imgs = st.file_uploader(
            "📸 上传做市商走势截图（支持多选相册：欧赔+亚盘+必发+首发）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
    if uploaded_imgs:
        st.write(f"已挂载 **{len(uploaded_imgs)}** 张盘口多模态数据切片：")
        cols = st.columns(min(len(uploaded_imgs), 4))
        for i, img_file in enumerate(uploaded_imgs):
            cols[i % len(cols)].image(img_file, caption=f"数据图 {i+1}", use_container_width=True)

    btn_predict = st.button("🚀 启动工业级双核量化推演并持久化存盘")

    if btn_predict:
        if not gemini_api_key:
            st.error("未检测到有效密钥，请在侧边栏或 Secrets 中配置 Gemini API Key！")
        else:
            is_zero_input = (not match_input.strip() and not uploaded_imgs)
            spinner_text = "未输入信息，正在全网搜索今日最火热足球焦点赛事及最新赔率盘口..." if is_zero_input else "双核引擎运作中：[多图交叉比对] + [泊松矩阵] + [微观操盘四模式] + [Game-State 突变演进]..."
            
            with st.spinner(spinner_text):
                math_baseline = compute_match_probabilities(1.40, 1.05)

                if is_zero_input:
                    prompt = (
                        "你是一名顶级体育对冲基金首席量化研究员，具备实时 Google 联网搜索能力。\n"
                        "用户未输入任何比赛信息。请执行全自动任务：\n"
                        "1. 立即联网搜索今日或今晚即将进行的全球最受瞩目足球焦点比赛，确定 1 场重点对阵双方。\n"
                        "2. 检索该场比赛最新的做市商赔率、主流让球盘口与大小球盘口。\n"
                        "3. 严格按照顶级标准输出完整量化分析：操盘模式、剧本突变对冲指令、临界入场赔率、亚盘大小球、自洽比分与凯利仓位。\n"
                    )
                    enable_s = True
                else:
                    prompt = f"""
你是一名顶级体育对冲基金首席量化研究员，精通做市商微观结构博弈、Shin 去抽水模型、联合分布自洽性与 Game-State 突变推演。
现对以下赛事启动深度交易研判：

【赛事信息】：{match_input if match_input else '详见上传截图中的赛事对阵'}
【本地数理基准概率】：
- 泊松理论分布：主胜 {math_baseline['home_win']}% | 平局 {math_baseline['draw']}% | 客胜 {math_baseline['away_win']}%
- 进球数理论离散度：0球({math_baseline['goals'].get(0)}%), 1球({math_baseline['goals'].get(1)}%), 2球({math_baseline['goals'].get(2)}%), 3球({math_baseline['goals'].get(3)}%)

【必须执行的最高分析铁律（五大实战补全）】：
1. **微观做市商模式强制定性**：明确归类【模式A：浅盘诱热 / 模式B：借题材阻盘 / 模式C：大单扫盘 Steam / 模式D：中立水钱对冲】。
2. **Game-State 突变与走地对冲指令**：必须推演弱队意外率先进球对大球的膨胀冲击，并给出明确的【走地突变对冲指令】。
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
- **🚨 走地突变对冲指令**：赛中若触发突变（如指定时间前客队破门），明确给出走地反手对冲的盘口与仓位建议。

### 三、核心量化决策（含公允临界点与联合自洽）
1. **欧盘胜平负**：
   - 核心结论：明确给出【主胜】、【平局】或【客胜】（单一选项）
   - 预测置信度：XX%
   - 价格边界：当前参考赔率 X.XX | 最低可接受赔率（Cut-off Odds）：X.XX（低于此值放弃）
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
                    enable_s = False

                images_payload = []
                if uploaded_imgs:
                    for img in uploaded_imgs:
                        images_payload.append((img.getvalue(), img.type))
                
                result_text, used_model, err = call_gemini_engine(
                    gemini_api_key, 
                    prompt, 
                    images_payload=images_payload,
                    enable_search=enable_s
                )

                if result_text:
                    st.success(f"✅ 工业级双核量化推演完成！（计算节点：{used_model}）")
                    st.markdown(result_text)

                    display_name = match_input.strip() if match_input.strip() else "今日全网焦点对决（自动检索）"
                    new_record = {
                        "id": int(time.time()),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": display_name,
                        "model": used_model,
                        "report": result_text,
                        "status": "待结算",
                        "final_score": "",
                        "clv_beaten": "待测算",
                        "audit_note": "",
                        "notes": ""
                    }
                    st.session_state.records.insert(0, new_record)
                    save_history(st.session_state.records)
                    st.toast("🎉 本次量化报告与风控参数已自动存入持久化账本！", icon="💾")
                else:
                    st.error(f"接口响应异常：{err}")

# ----------------- Tab 2: 历史对账与 CLV 结算 -----------------
with tab2:
    st.subheader("📋 推演历史对账与收盘价值（CLV）结算")
    if not st.session_state.records:
        st.info("暂无历史推演存档。请在【实时双核量化推演】中生成首次分析。")
    else:
        pending_list = [r for r in st.session_state.records if r.get("status") == "待结算"]
        settled_count = len([r for r in st.session_state.records if r.get("status") != "待结算"])
        hit_count = len([r for r in st.session_state.records if r.get("status") == "已命中"])
        win_rate = (hit_count / settled_count * 100) if settled_count > 0 else 0.0

        col1, col2, col3, col4 = st.columns([1.5, 1.5, 1.5, 3.5])
        col1.metric("累计推演", f"{len(st.session_state.records)} 场")
        col2.metric("已完成结算", f"{settled_count} 场")
        col3.metric("实战胜率", f"{win_rate:.1f}%")
        
        with col4:
            st.write("")
            if pending_list and st.button(f"⚡ 一键全网检索核销所有待结算（{len(pending_list)}场）"):
                if not gemini_api_key:
                    st.error("请先配置 Gemini API Key！")
                else:
                    with st.spinner("正在全网检索官方终场比分并批量核销..."):
                        for r in pending_list:
                            s_score, s_status, s_note = auto_search_and_settle(
                                gemini_api_key, r.get("match", ""), r.get("date", ""), r.get("report", "")
                            )
                            if s_status != "待结算":
                                r["final_score"] = s_score
                                r["status"] = s_status
                                r["audit_note"] = s_note
                        save_history(st.session_state.records)
                        st.success("批量联网核销执行完毕！")
                        st.rerun()

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            with st.expander(f"【{rec.get('status', '待结算')}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                if rec.get("audit_note"):
                    st.info(f"💡 对账审计摘要：{rec.get('audit_note')}")
                st.markdown("---")
                
                c1, c2, c3 = st.columns([2.5, 2, 2])
                with c1:
                    score = st.text_input("终场比分（留空直接联网搜）", value=rec.get("final_score", ""), key=f"score_{rec['id']}")
                with c2:
                    status_option = st.selectbox(
                        "结算判定",
                        ["待结算", "已命中", "未命中", "走盘"],
                        index=["待结算", "已命中", "未命中", "走盘"].index(rec.get("status", "待结算")),
                        key=f"status_{rec['id']}"
                    )
                with c3:
                    clv_option = st.selectbox(
                        "CLV 收盘价值",
                        ["跑赢终盘 (+CLV)", "落后终盘 (-CLV)", "平盘持平", "待测算"],
                        index=["跑赢终盘 (+CLV)", "落后终盘 (-CLV)", "平盘持平", "待测算"].index(rec.get("clv_beaten", "待测算")),
                        key=f"clv_{rec['id']}"
                    )
                
                b_col1, b_col2, b_col3 = st.columns([3, 3, 2])
                with b_col1:
                    if st.button("🌐 联网查比分并自动核销", key=f"btn_search_{rec['id']}"):
                        if not gemini_api_key:
                            st.error("请先配置 Gemini API Key！")
                        else:
                            with st.spinner(f"正在联网核查【{rec.get('match')}】完赛比分..."):
                                s_score, s_status, s_note = auto_search_and_settle(
                                    gemini_api_key, rec.get("match", ""), rec.get("date", ""), rec.get("report", "")
                                )
                                rec["final_score"] = s_score
                                rec["status"] = s_status
                                rec["audit_note"] = s_note
                                save_history(st.session_state.records)
                                st.success(f"核销完成：【{s_status}】比分：{s_score} - {s_note}")
                                st.rerun()
                with b_col2:
                    if st.button("⚡ 依据此比分直接核销", key=f"btn_calc_{rec['id']}"):
                        if not score.strip():
                            st.warning("比分框为空，请先填写比分或点击左侧联网核销！")
                        elif not gemini_api_key:
                            st.error("请先配置 Gemini API Key！")
                        else:
                            with st.spinner("AI 正在根据指定比分核销赛果..."):
                                auto_status, auto_note = auto_evaluate_with_given_score(
                                    gemini_api_key, rec.get("report", ""), score.strip()
                                )
                                rec["final_score"] = score.strip()
                                rec["status"] = auto_status
                                rec["audit_note"] = auto_note
                                save_history(st.session_state.records)
                                st.success(f"核销完成：【{auto_status}】 - {auto_note}")
                                st.rerun()
                with b_col3:
                    if st.button("💾 仅保存更改", key=f"btn_save_{rec['id']}"):
                        rec["final_score"] = score
                        rec["status"] = status_option
                        rec["clv_beaten"] = clv_option
                        save_history(st.session_state.records)
                        st.success("已手动保存！")
                        st.rerun()

# ----------------- Tab 3: 错题归因与策略进化 -----------------
with tab3:
    st.subheader("🧠 错题归因与策略自我进化（AI 蒸馏中枢）")
    st.caption("自动归纳未命中比赛的做市商操盘共性，逆向萃取防诱盘规则")

    failed_records = [r for r in st.session_state.records if r.get("status") == "未命中"]

    if not failed_records:
        st.success("暂无【未命中】失误记录，量化策略运行稳健。")
    else:
        st.warning(f"检测到当前有 {len(failed_records)} 场【未命中】样本，可用于提取防诱盘硬规则。")

        if st.button("🔥 启动工业级错题深度归因分析"):
            if not gemini_api_key:
                st.error("请先配置 Gemini API Key！")
            else:
                with st.spinner("AI 正在比对做市商初终盘水位与赛果，提炼认知偏差与诱盘特征..."):
                    review_cases = []
                    for r in failed_records[:5]:
                        review_cases.append(f"""
- 赛事：{r.get('match')}
- 终场比分：{r.get('final_score', '未知')}
- 审计记录：{r.get('audit_note', '无')}
- 推演摘要：{r.get('report')[:350]}...
""")

                    review_prompt = f"""
你是一名资深体育量化对冲基金复盘专家。以下是量化模型近期失误（黑单）的实战案例：

{''.join(review_cases)}

请对以上失误场次进行系统性深度归因分析：
1. **偏差根因**：做市商是否采用了浅盘诱热、假退盘阻击、升水诱下等手法？模型在哪个环节产生了认知幻觉？
2. **防诱盘军规提炼**：请提炼出 3 条明确具体的「反做市商避坑规则」（针对特定盘口、水位的硬性约束）。
3. **参数/置信度校准建议**：后续在此类盘口下，模型应如何降低置信度或直接放弃？
"""
                    review_result, model_used, err = call_gemini_engine(gemini_api_key, review_prompt)
                    if review_result:
                        st.markdown(review_result)
                    else:
                        st.error(f"归因分析失败: {err}")
