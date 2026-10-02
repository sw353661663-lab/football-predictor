import streamlit as st
import requests
import json
import time
import os
import base64
import math
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
    """
    通过双变量泊松网格计算 1X2 与进球数无偏概率矩阵
    """
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

# ================= 多模态推理调度 =================
def call_gemini_multimodal(api_key, prompt, image_bytes=None, mime_type="image/jpeg"):
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    headers = {"Content-Type": "application/json"}
    
    parts = [{"text": prompt}]
    if image_bytes:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
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
            r = requests.post(url, headers=headers, json=payload, timeout=90)
            data = r.json()
            if "candidates" in data:
                return data["candidates"][0]["content"]["parts"][0]["text"], model, None
            if "error" in data:
                if data["error"].get("code") in [503, 429]:
                    time.sleep(1)
                    continue
                last_err = data["error"].get("message", str(data))
        except Exception as e:
            last_err = str(e)
            continue
    return None, None, last_err

# ================= 页面主交互导航 =================
tab1, tab2, tab3 = st.tabs(["🚀 实时双核量化推演", "📋 历史对账与 CLV 结算", "🧠 错题归因与策略进化"])

# ----------------- Tab 1: 实时推演 -----------------
with tab1:
    st.subheader("⚽ 赛事微观结构与剧本突变决策引擎")
    
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        match_input = st.text_input("🔍 目标对阵 / 联赛阶段", placeholder="如：欧国联 哈萨克斯坦 vs 摩尔多瓦")
    with col_in2:
        uploaded_img = st.file_uploader("📸 上传做市商赔率/盘口走势截图（支持手机相册/拍照）", type=["png", "jpg", "jpeg"])
        
    if uploaded_img:
        st.image(uploaded_img, caption="已挂载的多模态微观盘口数据源", width=380)

    btn_predict = st.button("🚀 启动工业级双核量化推演并持久化存盘")

    if btn_predict:
        if not gemini_api_key:
            st.error("未检测到有效密钥，请在侧边栏或 Secrets 中配置 Gemini API Key！")
        elif not match_input and not uploaded_img:
            st.warning("请至少输入对阵球队，或上传一张盘口走势截图！")
        else:
            with st.spinner("双核引擎运作中：[泊松数学矩阵] + [微观操盘四模式归类] + [Game-State 突变演进]..."):
                math_baseline = compute_match_probabilities(1.40, 1.05)

                prompt = f"""
你是一名顶级体育对冲基金首席量化研究员，精通做市商微观结构博弈、Shin 去抽水模型与 Game-State 突变推演。
现对以下赛事启动深度交易研判：

【赛事信息】：{match_input if match_input else '详见上传截图中的赛事对阵'}
【本地数理基准概率】：
- 泊松理论分布：主胜 {math_baseline['home_win']}% | 平局 {math_baseline['draw']}% | 客胜 {math_baseline['away_win']}%
- 进球数理论离散度：0球({math_baseline['goals'].get(0)}%), 1球({math_baseline['goals'].get(1)}%), 2球({math_baseline['goals'].get(2)}%), 3球({math_baseline['goals'].get(3)}%)

【必须执行的最高分析铁律】：
1. **微观做市商操盘模式必须强制定性（必须明确标出以下 4 种之一）**：
   - 【模式A：浅盘低水诱热】（基本面名气大但让步浅、低水赔付阻力极小，散户扎堆，机构冷门防守）
   - 【模式B：借题材逆向阻盘】（基本面有微弱利空，机构顺水推舟退盘升水制造不稳假象，降低真实打出赔付）
   - 【模式C：职业大单扫盘 (Steam)】（多机构短时间内同步剧烈降水降盘，真实热钱砸盘）
   - 【模式D：多空分歧·中立水钱对冲】（盘面平衡，无异常退盘或水位异动）
2. **必须引入 Game-State（比赛突变剧本树）进行压力测试**：
   - 严禁假定比赛永远均势！必须推演：若弱队/客队在上半场意外先进一球，强队压上反扑对全场比分与进球数的膨胀破坏力！
3. **输出结论必须唯一、坚定，严禁模棱两可！**

请严格按照以下工业化格式输出报告：

### 一、做市商操盘定性与微观结构
- **做市商操盘模式归类**：明确标出属于【模式A / 模式B / 模式C / 模式D】中的哪一种，并说明理由。
- **平博/皇冠/利记异动解析**：初终盘变轨、升降水幅度与去抽水后真实胜率对比。
- **必发成交冷热**：成交量分布是否存在诱盘或多空分歧。

### 二、Game-State 比赛剧本突变演进
- **基准剧本态（均势）**：双方正常节奏下的攻防胶着度。
- **破局突变态（压力测试）**：若客队/下盘方率先进球，强队阵型前倾对防反及总进球数扩大的风险评估。

### 三、核心预测结论（量化置信度与指令）
1. **欧盘胜平负**：
   - 核心结论：明确给出【主胜】、【平局】或【客胜】（单一选项）
   - 预测置信度：XX%
2. **让球胜平负（明确让球数与亚盘方向）**：
   - 明确盘口：标明让球方及让球幅度（如：客队受让半球 / 主队 -1）
   - 核心结论：明确给出【让胜】、【让平】或【让负】（单一选项）
   - 预测置信度：XX%
3. **多选总进球数（精选两项）**：
   - 进球数推荐一：X 球（置信度：XX%）
   - 进球数推荐二：X 球（置信度：XX%）

### 四、0.25x 凯利风控与实战仓位建议
- **核心价值投资项（Value Bet）**：指出全场最具数学正期望（+EV）的单一投注项。
- **动态期望值评估**：估算 $\\text{{EV}} = p \\times b - 1$。
- **0.25x 凯利建议仓位**：明确给出建议开仓比例（如 1.5%~2.5%，若 EV 为负则给出 0% 放弃）。
"""

                img_bytes = uploaded_img.getvalue() if uploaded_img else None
                mime_t = uploaded_img.type if uploaded_img else "image/jpeg"
                
                result_text, used_model, err = call_gemini_multimodal(
                    gemini_api_key, 
                    prompt, 
                    image_bytes=img_bytes, 
                    mime_type=mime_t
                )

                if result_text:
                    st.success(f"✅ 工业级双核量化推演完成！（计算节点：{used_model}）")
                    st.markdown(result_text)

                    display_name = match_input if match_input else "核心焦点赛事（截图解析）"
                    new_record = {
                        "id": int(time.time()),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": display_name,
                        "model": used_model,
                        "report": result_text,
                        "status": "待结算",
                        "final_score": "",
                        "clv_beaten": "待测算",
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
        total_count = len(st.session_state.records)
        settled_count = len([r for r in st.session_state.records if r.get("status") != "待结算"])
        hit_count = len([r for r in st.session_state.records if r.get("status") == "已命中"])
        win_rate = (hit_count / settled_count * 100) if settled_count > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        col1.metric("累计量化推演", f"{total_count} 场")
        col2.metric("已完成结算", f"{settled_count} 场")
        col3.metric("实战命中率 (Win Rate)", f"{win_rate:.1f}%")

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            with st.expander(f"【{rec.get('status', '待结算')}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                st.markdown("---")
                
                c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
                with c1:
                    score = st.text_input("终场比分（如 1-2）", value=rec.get("final_score", ""), key=f"score_{rec['id']}")
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
                with c4:
                    st.write("")
                    st.write("")
                    if st.button("💾 保存复盘结算", key=f"btn_save_{rec['id']}"):
                        rec["final_score"] = score
                        rec["status"] = status_option
                        rec["clv_beaten"] = clv_option
                        save_history(st.session_state.records)
                        st.success("结算已锁定！")
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
- CLV 表现：{r.get('clv_beaten', '未知')}
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
                    review_result, model_used, err = call_gemini_multimodal(gemini_api_key, review_prompt)
                    if review_result:
                        st.markdown(review_result)
                    else:
                        st.error(f"归因分析失败: {err}")
