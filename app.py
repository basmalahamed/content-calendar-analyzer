import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai

st.set_page_config(page_title="محلل البراند وخطة المحتوى", layout="wide")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

if "brand_profile" not in st.session_state:
    st.session_state.brand_profile = None

def scrape_website(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentCalendarBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:8000], None
    except Exception as e:
        return None, str(e)

def extract_brand_profile(website_text, website_url, social_text, industry, market, audience, platforms, objective, language, priority_topics):
    prompt = f"""أنت خبير تحليل براندات. اقرأ المعلومات دي، وطلّع Brand Profile بصيغة JSON فقط بدون أي كلام إضافي، بالشكل ده بالظبط:

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

معلومات إضافية من العميل (استخدمها لتوجيه التحليل، وادمجها مع اللي هتستنتجه من النص):
- الصناعة: {industry}
- السوق: {market}
- الجمهور المستهدف (حسب العميل): {audience}
- المنصات: {', '.join(platforms) if platforms else 'غير محدد'}
- هدف الحملة: {objective}
- اللغة المفضلة: {language}
- مواضيع أو عروض ذات أولوية: {priority_topics}

نص الموقع:
{website_text}

نصوص من السوشيال ميديا (لو موجودة):
{social_text if social_text else 'لا يوجد'}
"""
    model = genai.GenerativeModel("gemini-3.6-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

st.title("🧠 محلل البراند وخطة المحتوى")

with st.form("inputs_form"):
    st.subheader("١. بيانات أساسية")
    col1, col2 = st.columns(2)
    with col1:
        website_url = st.text_input("رابط الموقع", placeholder="https://example.com")
        industry = st.text_input("الصناعة", placeholder="مثال: أزياء، مطاعم، تكنولوجيا")
        market = st.text_input("السوق", placeholder="مثال: مصر، السعودية")
        audience = st.text_input("الجمهور المستهدف", placeholder="مثال: شباب 18-30")
    with col2:
        platforms = st.multiselect("المنصات", ["Instagram", "Facebook", "TikTok", "LinkedIn", "X (Twitter)"])
        objective = st.text_input("هدف الحملة", placeholder="مثال: زيادة الوعي بالبراند")
        language = st.selectbox("اللغة المفضلة", ["العربية", "English", "عربي مصري (مزيج)"])
        priority_topics = st.text_input("مواضيع أو عروض ذات أولوية (اختياري)")

    st.subheader("٢. محتوى السوشيال ميديا (اختياري)")
    st.caption("منقدرش نسحب البوستات مباشرة من المنصات، فالصقي نصوص من بوستاتك هنا (لحد 20 بوست) أو روابطها.")
    social_text = st.text_area("الصقي نصوص أو روابط البوستات هنا", height=150)

    submitted = st.form_submit_button("حلل واستخرج البروفايل")

if submitted:
    if not website_url:
        st.error("لازم تدخلي رابط الموقع على الأقل")
    else:
        with st.spinner("بيقرا الموقع..."):
            text, error = scrape_website(website_url)
        if text is None:
            st.error(f"مقدرناش نوصل للموقع: {error}")
        else:
            with st.spinner("الـ AI بيحلل..."):
                try:
                    profile = extract_brand_profile(text, website_url, social_text, industry, market, audience, platforms, objective, language, priority_topics)
                    st.session_state.brand_profile = profile
                    st.success("تم التحليل! تقدري تعدلي في النتيجة تحت.")
                except Exception as e:
                    st.error(f"حصلت مشكلة: {e}")

if st.session_state.brand_profile:
    st.divider()
    st.subheader("٣. Brand Profile - قابل للتعديل")
    p = st.session_state.brand_profile

    with st.form("edit_form"):
        positioning = st.text_area("الموقع التنافسي (Positioning)", value=p.get("positioning", ""))
        target_audience = st.text_area("الجمهور المستهدف", value=p.get("target_audience", ""))
        products_services = st.text_area("المنتجات/الخدمات (سطر لكل عنصر)", value="\n".join(p.get("products_services", [])))
        tone_description = st.text_area("وصف نبرة الصوت", value=p.get("tone_of_voice", {}).get("description", ""))
        vocabulary = st.text_area("مفردات متكررة (سطر لكل كلمة)", value="\n".join(p.get("vocabulary", [])))
        visual_direction = st.text_area("الاتجاه البصري", value=p.get("visual_direction", ""))
        content_pillars = st.text_area("المواضيع الأساسية (سطر لكل موضوع)", value="\n".join(p.get("content_pillars", [])))
        calls_to_action = st.text_area("الـ CTAs (سطر لكل عنصر)", value="\n".join(p.get("calls_to_action", [])))
        topics_to_avoid = st.text_area("مواضيع نتجنبها (سطر لكل عنصر)", value="\n".join(p.get("topics_to_avoid", [])))

        save = st.form_submit_button("احفظي التعديلات")

    if save:
        st.session_state.brand_profile = {
            "positioning": positioning,
            "target_audience": target_audience,
            "products_services": [x.strip() for x in products_services.split("\n") if x.strip()],
            "tone_of_voice": {"description": tone_description, "evidence": p.get("tone_of_voice", {}).get("evidence", [])},
            "vocabulary": [x.strip() for x in vocabulary.split("\n") if x.strip()],
            "visual_direction": visual_direction,
            "content_pillars": [x.strip() for x in content_pillars.split("\n") if x.strip()],
            "calls_to_action": [x.strip() for x in calls_to_action.split("\n") if x.strip()],
            "topics_to_avoid": [x.strip() for x in topics_to_avoid.split("\n") if x.strip()],
            "sources": p.get("sources", []),
        }
        st.success("اتحفظت التعديلات!")

    with st.expander("عرض المصادر (Sources)"):
        st.json(p.get("sources", []))
