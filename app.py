import streamlit as st
import requests
import json
import time
import os
from datetime import datetime

# 页面基础配置
st.set_page_config(
    page_title="足球赛事量化预测与自进化中枢",
    page_icon="⚽",
    layout="wide"
)

# 本地数据存储路径
DATA_FILE = "prediction_history.json"

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
        st.error(f"存档失败: {str(e)}")

# 初始化历史记录
if "records" not in st.session_state:
    st.session_state.records = load_history()

# 侧边栏：接口配置
with st.sidebar:
    st.header("⚙️ 接口配置")
    gemini_key_input = st.text_input("Gemini API Key", type="password")
    odds_key_input = st.text_input("The Odds API Key", type="password")
    st.caption("提示：在手机端首次打开时填入一次即可")
    st.markdown("---")
    st.subheader("💾 数据备份与恢复")
    # 支持一键下载存档文件到手机/电脑
    json_str = json.dumps(st.session_state.records, ensure_ascii=False, indent=2)
    st.download_button(
        label="📥 导出/备份所有推演历史",
        data=json_str,
        file_name=f"quant_records_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json"
    )
    # 支持导入已有数据
    uploaded_file = st.file_uploader("📤 恢复备份记录", type="json")
    if uploaded_file is not None:
        try:
            imported_data = json.load(uploaded_file)
            st.session_state.records = imported_data
            save_history(imported_data)
            st.success("备份记录恢复成功！")
        except Exception as e:
            st.error(f"恢复失败: {str(e)}")

gemini_api_key = st.secrets.get("GEMINI_API_KEY", gemini_key_input).strip()
odds_api_key = st.secrets.get("ODDS_API_KEY", odds_key_input).strip()

def get_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("models", [])
            valid = [
                m["name"].replace("models/", "")
                for m in data
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            flash_list = [m for m in valid if "flash" in m]
            other_list = [m for m in valid if "flash" not in m]
            return flash_list + other_list
    except Exception:
        pass
    return ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]

def call_gemini_smart(api_key, prompt):
    models = get_available_models(api_key)
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
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

def fetch_odds_data(api_key, sport="soccer_epl"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        return response.json()
    except Exception:
        return None

# ================= 页面主交互：三大中枢导航 =================
tab1, tab2, tab3 = st.tabs(["🚀 实时量化推演", "📋 历史存档与结算", "🧠 错题归因与策略进化"])

# ----------------- Tab 1: 实时量化推演 -----------------
with tab1:
    st.subheader("⚽ 赛事量化决策引擎")
    match_input = st.text_input("🔍 输入对阵球队（如：阿森纳 VS 曼联、拉脱维亚 VS 黑山）", placeholder="输入比赛或球队关键词")
    btn_predict = st.button("🚀 执行量化深度分析并自动存档")

    if btn_predict:
        if not gemini_api_key:
            st.error("请先在左侧侧边栏填入 Gemini API Key！")
        else:
            with st.spinner("正在调度多维数据（历史战绩 + 盘口赔率 + xG矩阵）推演中..."):
                market_context = "基于量化模型内置数学框架推演"
                if odds_api_key:
                    odds_data = fetch_odds_data(odds_api_key)
                    if isinstance(odds_data, list):
                        market_context = json.dumps(odds_data[:3], ensure_ascii=False)

                prompt = f"""
你是一名顶级专业足球赛事量化分析师，严格按照以下要求输出，核心结论必须明确坚决，严禁模棱两可：

目标赛事：{match_input if match_input else '近期核心焦点赛事'}
参考盘口与市场数据：{market_context}

### 一、核心预测结论（严格置信度量化）
1. **欧盘胜平负**：
   - 核心结论：明确给出【主胜】、【平局】或【客胜】（单一选项）
   - 预测置信度：XX%
2. **让球胜平负（明确让球数与亚盘方向）**：
   - 明确盘口：标明让球方及让球幅度（如：主让半球 / 客队+0.5）
   - 核心结论：明确给出【让球胜】、【让球平】或【让球负】（单一选项）
   - 预测置信度：XX%
3. **多选总进球数（精选两项）**：
   - 进球数推荐一：X 球（置信度：XX%）
   - 进球数推荐二：X 球（置信度：XX%）

### 二、历史数据背景与交锋走势（关键量化特征）
- 双方近 5 次历史交锋（H2H）战术风格克制、比分倾向与得失球特征。
- 双方近 6 轮主客场战绩与攻防期望进球（xG）变化轨迹。

### 三、做市商盘口与资金异动深度解析
- 赔率隐含概率与做市商赔付风险平衡点评估。
- 盘口水位震荡、冷热资金流向与诱盘/阻盘特征。

### 四、策略与风控评估
- 价值投注（Value Bet）空间与风险预警。
"""

                result_text, used_model, err = call_gemini_smart(gemini_api_key, prompt)

                if result_text:
                    st.success(f"✅ 量化分析推演完成！（响应节点：{used_model}）")
                    st.markdown(result_text)

                    # 自动建立历史存档记录
                    new_record = {
                        "id": int(time.time()),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "match": match_input if match_input else "核心焦点赛事",
                        "model": used_model,
                        "report": result_text,
                        "status": "待结算",  # 待结算 / 已命中 / 未命中
                        "final_score": "",
                        "actual_result": "",
                        "notes": ""
                    }
                    st.session_state.records.insert(0, new_record)
                    save_history(st.session_state.records)
                    st.toast("🎉 本次推演已自动完成持久化存档！", icon="💾")
                else:
                    st.error(f"接口响应异常：{err}")

# ----------------- Tab 2: 历史存档与结算 -----------------
with tab2:
    st.subheader("📋 推演历史对账与赛果复盘")
    if not st.session_state.records:
        st.info("暂无历史推演存档。请在【实时量化推演】中生成首次分析。")
    else:
        # 统计面板
        total_count = len(st.session_state.records)
        settled_count = len([r for r in st.session_state.records if r.get("status") != "待结算"])
        hit_count = len([r for r in st.session_state.records if r.get("status") == "已命中"])
        win_rate = (hit_count / settled_count * 100) if settled_count > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        col1.metric("累计推演场次", f"{total_count} 场")
        col2.metric("已结算场次", f"{settled_count} 场")
        col3.metric("复盘实战胜率", f"{win_rate:.1f}%")

        st.markdown("---")

        for idx, rec in enumerate(st.session_state.records):
            with st.expander(f"【{rec.get('status', '待结算')}】 {rec.get('date', '')} | {rec.get('match', '')}", expanded=(idx == 0)):
                st.markdown(rec.get("report", ""))
                st.markdown("---")
                
                # 录入赛果结算
                c1, c2, c3 = st.columns([2, 2, 2])
                with c1:
                    score = st.text_input(f"终场比分（如 2-1）", value=rec.get("final_score", ""), key=f"score_{rec['id']}")
                with c2:
                    status_option = st.selectbox(
                        "结算判定",
                        ["待结算", "已命中", "未命中", "走盘"],
                        index=["待结算", "已命中", "未命中", "走盘"].index(rec.get("status", "待结算")),
                        key=f"status_{rec['id']}"
                    )
                with c3:
                    st.write("")
                    st.write("")
                    if st.button("💾 保存复盘结算", key=f"btn_save_{rec['id']}"):
                        rec["final_score"] = score
                        rec["status"] = status_option
                        save_history(st.session_state.records)
                        st.success("结算记录已保存！")
                        st.rerun()

# ----------------- Tab 3: 错题归因与策略进化 -----------------
with tab3:
    st.subheader("🧠 错题归因与策略自我进化")
    st.caption("从失误的比赛中提取做市商操盘共性，将归因总结为防诱盘规则反哺模型")

    # 提取所有失误场次
    failed_records = [r for r in st.session_state.records if r.get("status") == "未命中"]

    if not failed_records:
        st.success("目前没有标记为【未命中】的场次，或所有场次尚未结算。")
    else:
        st.warning(f"检测到当前有 {len(failed_records)} 场【未命中】的失误记录，可用于策略蒸馏。")

        if st.button("🔥 启动 AI 错题集深度归因分析"):
            if not gemini_api_key:
                st.error("请先填入 Gemini API Key！")
            else:
                with st.spinner("AI 正在比对做市商盘口、初终盘水位与真实赛果，提取认知偏差..."):
                    review_cases = []
                    for r in failed_records[:5]:  # 提取最近 5 场失误
                        review_cases.append(f"""
- 赛事：{r.get('match')}
- 实际比分：{r.get('final_score', '未知')}
- 当时推演关键部分：{r.get('report')[:300]}...
""")

                    review_prompt = f"""
你是一名资深量化交易复盘专家。以下是量化模型近期预测失误（黑单）的比赛案例：

{''.join(review_cases)}

请对以上失误场次进行系统性深度归因分析：
1. **偏差根因归因**：做市商是否采用了浅盘诱热、假退盘阻击、升水诱下等手法？模型在哪个环节产生了认知幻觉？
2. **防诱盘军规提炼**：请提炼出 3 条明确具体的「反做市商避坑规则」（例如：针对某类深浅盘口、冷热水位的硬性约束）。
3. **参数/置信度校准建议**：后续在此类盘口下，模型应如何降低置信度或直接放弃？
"""
                    review_result, model_used, err = call_gemini_smart(gemini_api_key, review_prompt)
                    if review_result:
                        st.markdown(review_result)
                    else:
                        st.error(f"归因分析失败：{err}")
