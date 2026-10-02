import streamlit as st
import requests
import json

st.set_page_config(page_title="足球量化预测中枢", page_icon="⚽", layout="centered")

st.title("⚽ 足球赛事量化预测中枢")
st.caption("基于做市商盘口资金异动与 Gemini 量化决策引擎")

# 侧边栏：填写密钥（手机端首次打开填入一次即可记住）
with st.sidebar:
    st.header("⚙️ 接口配置")
    gemini_key = st.text_input("Gemini API Key", value=st.secrets.get("GEMINI_API_KEY", ""), type="password")
    odds_key = st.text_input("The Odds API Key", value=st.secrets.get("ODDS_API_KEY", ""), type="password")
    st.markdown("---")
    st.caption("提示：在手机端首次打开时填入一次即可")

match_name = st.text_input("🔍 输入对阵球队（如：阿森纳、曼联、皇马）", placeholder="输入球队关键词")

if st.button("🚀 执行量化深度分析", use_container_width=True):
    if not match_name.strip():
        st.warning("⚠️ 请先输入对阵球队名称！")
    elif not gemini_key or not odds_key:
        st.error("⚠️ 请在左侧侧边栏填入您的 Gemini Key 和 The Odds API Key！")
    else:
        with st.spinner("正在抓取做市商最新盘口数据并执行量化决策..."):
            # 1. 抓取做市商实时赔率
            odds_summary = "未检索到做市商实时异动，按历史大盘基准推算"
            try:
                odds_url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={odds_key}&regions=eu&markets=h2h,totals"
                res = requests.get(odds_url, timeout=10).json()
                for item in res:
                    h_team = item.get("home_team", "").lower()
                    a_team = item.get("away_team", "").lower()
                    if match_name.lower() in h_team or match_name.lower() in a_team:
                        odds_summary = json.dumps(item, ensure_ascii=False)
                        break
            except Exception:
                pass

            # 2. 调用 Gemini 量化模型（严格按照分析师要求设定）
            prompt = f"""
            你是专业足球赛事分析师，针对比赛【{match_name}】，结合做市商数据【{odds_summary}】，严格按照以下要求输出：
            1. 核心结论要求明确，不模棱两可；
            2. 输出必须包含以下三项结论，且三项结论必须增加你预测后的置信度：
               - 【欧盘胜平负】：[明确胜/平/负]（置信度：X%）
               - 【亚盘胜负平】：[明确主胜/客胜/走水，含让球盘口规格]（置信度：X%）
               - 【总进球数多选】：给出两个最可能的总进球数（置信度：X%）
            3. 附带50字以内做市商盘口与主力筹码异动简要依据。
            """

            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }

            try:
                resp = requests.post(gemini_url, json=payload, timeout=25)
                data = resp.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    analysis = data["candidates"][0]["content"]["parts"][0]["text"]
                    st.success("✅ 量化策略分析完成！")
                    st.markdown(analysis)
                else:
                    st.error(f"接口响应异常，请检查 Gemini Key 额度或配置：{data}")
            except Exception as e:
                st.error(f"分析请求失败：{e}")
