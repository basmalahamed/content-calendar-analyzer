import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai

st.set_page_config(page_title="محلل البراند - الخطوة 1", layout="wide")

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def scrape_website(url):
    """يجيب النص الظاهر من صفحة الموقع"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentCalendarBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:8000], None
    except Exception as e:
        return None, str(e)

def extract_brand_profile(website_text, website_url):
    prompt = f"""أنت خبير تحليل براندات. اقرأ النص التالي المستخرج من موقع شركة، وطلّع Brand Profile بصيغة JSON فقط بدون أي كلام إضافي، بالشكل ده بالظبط:

{{
  "positioning": "...",
  "target_audience": "...",
  "products_services": ["..."],
  "tone_of_voice": {{"description": "...", "evidence": ["..."]}},
  "vocabulary": ["..."],
  "visual_direction": "...",
  "content_pillars": ["..."],
  "calls_to_action": ["..."],
  "topics_to_avoid": ["..."],
  "sources": [{{"type": "website_page", "url": "{website_url}", "note": "..."}}]
}}

كل استنتاج لازم يكون مبني على دليل واضح من النص، واذكر الدليل ده في evidence أو note.

نص الموقع:
{website_text}
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

st.title("🧠 محلل البراند - الخطوة الأولى")
st.write("حط رابط موقع الشركة وشوف الـ AI هيستخرج منه إيه")

url = st.text_input("رابط الموقع", placeholder="https://example.com")

if st.button("حلل الموقع"):
    if not url:
        st.error("لازم تدخل رابط الأول")
    else:
        with st.spinner("بيقرا الموقع..."):
            text, error = scrape_website(url)
        if text is None:
            st.error(f"مقدرناش نوصل للموقع: {error}")
        else:
            with st.spinner("الـ AI بيحلل..."):
                try:
                    profile = extract_brand_profile(text, url)
                    st.success("تم التحليل!")
                    st.json(profile)
                except Exception as e:
                    st.error(f"حصلت مشكلة: {e}")
