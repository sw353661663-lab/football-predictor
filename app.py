import streamlit as st
import requests
import json
import time

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

# 读取 API Key
gemini_api_key = st.secrets.get("GEMINI_API_KEY", gemini_key_input).strip()
odds_api_key = st.secrets.get("ODDS_API_KEY", odds_key_input).strip()

def get_available_models(api_key):
    """自动获取当前 Key 拥有的有效模型列表"""
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
            # 优先 flash，其次其它
            flash_list = [m for m in valid if "flash" in m]
            other_list = [m for m in valid if "flash" not in m]
            return flash_list + other_list
    except Exception:
        pass
    return ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]

def call_gemini_smart(api_key, prompt):
    """智能轮询推演：遇 503 拥堵自动秒切空闲模型"""
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
            
            # 若遇 503 拥堵或 429 限频，自动跳过尝试下一个可用节点
            if "error" in data:
                code = data["error"].get("code")
                if code in [503, 429]:
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

# 主操作区
match_input = st.text_input("🔍 输入对阵球队（如：拉脱维亚 VS 黑山、阿森纳、皇马）", placeholder="输入比赛或球队关键词")
btn_predict = st.button("🚀 执行量化深度分析")

if btn_predict:
    if not gemini_api_key:
        st.error("请先在左侧侧边栏填入 Gemini API Key！")
    else:
        with st.spinner("正在调度空闲推演节点并执行量化分析..."):
            market_context = "基于模型内置量化数学框架推演"
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

            result_text, used_model, err = call_gemini_smart(gemini_api_key, prompt)

            if result_text:
                st.success(f"✅ 量化分析推演完成！（响应节点：{used_model}）")
                st.markdown(result_text)
            else:
                st.error(f"所有线路节点暂时繁忙，请稍等片刻重试。错误反馈：{err}")
