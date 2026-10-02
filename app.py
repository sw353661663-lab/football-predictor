import streamlit as st
import requests
import json

st.set_page_config(
    page_title="足球赛事量化预测中枢",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ 足球赛事量化预测中枢")
st.caption("基于做市商盘口资金异动与 Gemini 量化决策引擎")

# 侧边栏：接口配置
with st.sidebar:
    st.header("⚙️ 接口配置")
    gemini_key_input = st.text_input("Gemini API Key", type="password")
    odds_key_input = st.text_input("The Odds API Key", type="password")
    st.caption("提示：在手机端首次打开时填入一次即可")

# 读取 API Key（优先使用云端 Secrets，其次使用界面输入）
gemini_api_key = st.secrets.get("GEMINI_API_KEY", gemini_key_input).strip()
odds_api_key = st.secrets.get("ODDS_API_KEY", odds_key_input).strip()

def call_gemini(api_key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    try:
        # 超时时间放宽至 90 秒，避免长文本生成时超时熔断
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        return response.json(), None
    except requests.exceptions.Timeout:
        return None, "模型深度推演计算超时（超过90秒），请稍后重试或简化查询词。"
    except Exception as e:
        return None, f"调用接口网络异常: {str(e)}"

def fetch_odds_data(api_key, sport="soccer_epl"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(url, params=params, timeout=20)
        return response.json()
    except Exception:
        return None

# 主操作区
match_input = st.text_input("🔍 输入对阵球队（如：阿森纳、曼联、拉脱维亚 VS 黑山）", placeholder="输入比赛或球队关键词")
btn_predict = st.button("🚀 执行量化深度分析")

if btn_predict:
    if not gemini_api_key:
        st.error("请先在左侧侧边栏填入 Gemini API Key！")
    else:
        with st.spinner("正在获取做市商实时数据并执行量化深度推演（计算中，请稍候）..."):
            market_context = "未配置 Odds Key 或暂无外部盘口数据，基于模型内置量化数学模型分析"
            if odds_api_key:
                odds_data = fetch_odds_data(odds_api_key)
                if isinstance(odds_data, list):
                    market_context = json.dumps(odds_data[:3], ensure_ascii=False)

            prompt = f"""
你是一名专业足球赛事量化分析师，严格按照以下要求进行深度推演并输出，核心结论必须明确、不模棱两可：

目标赛事：{match_input if match_input else '近期核心焦点赛事'}
参考盘口数据：{market_context}

### 一、核心预测结论（置信度量化）
1. **欧盘胜平负**：给出明确结论（胜/平/负），必须标注预测置信度百分比。
2. **亚盘胜平负/让球**：给出具体推荐盘口与方向，必须标注预测置信度百分比。
3. **总进球数（多选两个）**：明确给出两个最可能出现的总进球数（或进球数区间），并分别标注预测置信度百分比。

### 二、做市商盘口与资金流向分析
- 赔率隐含概率与做市商赔付风险平衡点评估。
- 亚盘水位、让球阻力以及市场资金冷热流向。

### 三、基本面与预期进球（xG）推演
- 攻防两端关键指标、近期战术风格与阵容影响。
- 预期进球（xG）模型推演可能比分。

### 四、策略与风控评估
- 价值投注（Value Bet）空间评估与风险预警。
"""

            res_json, error_msg = call_gemini(gemini_api_key, prompt)

            if error_msg:
                st.warning(error_msg)
            elif res_json and "candidates" in res_json:
                try:
                    result_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    st.success("✅ 量化分析推演完成！")
                    st.markdown(result_text)
                except Exception as parse_err:
                    st.error(f"解析结果异常: {str(parse_err)}")
            else:
                st.error(f"接口响应异常，请检查 Gemini Key 额度或配置：{res_json}")
