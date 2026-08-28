import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import os
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import google.generativeai as genai

st.set_page_config(page_title="AI Content Calendar", page_icon="🧠", layout="wide")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

if "brand_profile" not in st.session_state:
    st.session_state.brand_profile = None
if "trends" not in st.session_state:
    st.session_state.trends = None
if "trend_pool" not in st.session_state:
    st.session_state.trend_pool = []

# ---------- Website analysis ----------

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
اكتبي محتوى النصوص (positioning, tone_of_voice, إلخ) بلغة: {language}.

معلومات إضافية من العميل (استخدمها لتوجيه التحليل، وادمجها مع اللي هتستنتجه من النص):
- الصناعة: {industry}
- السوق: {market}
- الجمهور المستهدف (حسب العميل): {audience}
- المنصات: {', '.join(platforms) if platforms else 'غير محدد'}
- هدف الحملة: {objective}
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

# ---------- Trend discovery ----------

def search_google_news(query, max_results=6):
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ar&gl=EG&ceid=EG:ar"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_results]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pubdate_raw = item.findtext("pubDate", "")
            try:
                pubdate = parsedate_to_datetime(pubdate_raw).strftime("%Y-%m-%d")
            except Exception:
                pubdate = ""
            items.append({"title": title, "link": link, "date": pubdate})
        return items
    except Exception:
        return []

def evaluate_trend_candidates(brand_profile, candidates, language, count=5):
    if not candidates:
        return []
    candidates_text = "\n".join([f"- {c['title']} | تاريخ: {c['date']} | رابط: {c['link']}" for c in candidates])
    prompt = f"""أنت خبير في الترندات والبراندات. عندك Brand Profile وقائمة أخبار/مواضيع ترند حالياً. اختر أفضل {count} منهم اللي تناسب البراند ده فعلاً، وقيّم كل واحد. لو مفيش ترند مناسب فعلاً، رجّع مصفوفة فاضية. متختاريش ترند غير مرتبط بالبراند فقط عشان هو شعبي. اكتبي description و brand_fit_explanation بلغة: {language}.

Brand Profile:
{json.dumps(brand_profile, ensure_ascii=False)}

المرشحون:
{candidates_text}

رجّعي مصفوفة JSON فقط (من غير أي كلام إضافي) بالشكل ده لكل ترند مختار:
[
  {{
    "trend_name": "...",
    "description": "...",
    "source_url": "...",
    "discovery_date": "YYYY-MM-DD",
    "brand_fit_score": 0,
    "brand_fit_explanation": "..."
  }}
]
"""
    model = genai.GenerativeModel("gemini-3.6-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

# ---------- UI ----------

st.title("🧠 AI Content Calendar")
st.caption("Analyzes a brand's website, extracts a Brand Profile, finds relevant trends, and helps you build a content calendar.")

with st.form("inputs_form"):
    st.subheader("1. Basic Information")
    col1, col2 = st.columns(2)
    with col1:
        website_url = st.text_input("Website URL", placeholder="https://example.com")
        industry = st.text_input("Industry", placeholder="e.g. Fashion, Restaurants, Tech")
        market = st.text_input("Market", placeholder="e.g. Egypt, Saudi Arabia")
        audience = st.text_input("Target Audience", placeholder="e.g. Youth 18-30")
    with col2:
        platforms = st.multiselect("Platforms", ["Instagram", "Facebook", "TikTok", "LinkedIn", "X (Twitter)"])
        objective = st.text_input("Campaign Objective", placeholder="e.g. Increase brand awareness")
        language = st.selectbox("Output Language", ["Arabic", "English", "Egyptian Arabic (mixed)"])
        priority_topics = st.text_input("Priority Topics / Offers (optional)")

    st.subheader("2. Social Media Content (optional)")
    st.caption("We can't scrape platforms directly. Paste post text (up to 20 posts) or post URLs below.")
    social_text = st.text_area("Paste post text or URLs here", height=150)

    submitted = st.form_submit_button("Analyze & Extract Brand Profile")

if submitted:
    if not website_url:
        st.error("Please enter a website URL at least")
    else:
        with st.spinner("Reading the website..."):
            text, error = scrape_website(website_url)
        if text is None:
            st.error(f"Couldn't reach the website: {error}")
        else:
            with st.spinner("AI is analyzing..."):
                try:
                    profile = extract_brand_profile(text, website_url, social_text, industry, market, audience, platforms, objective, language, priority_topics)
                    st.session_state.brand_profile = profile
                    st.session_state.trends = None
                    st.success("Analysis complete! You can edit the results below.")
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

if st.session_state.brand_profile:
    st.divider()
    st.subheader("3. Brand Profile — Editable")
    p = st.session_state.brand_profile

    with st.form("edit_form"):
        positioning = st.text_area("Positioning", value=p.get("positioning", ""))
        target_audience = st.text_area("Target Audience", value=p.get("target_audience", ""))
        products_services = st.text_area("Products / Services (one per line)", value="\n".join(p.get("products_services", [])))
        tone_description = st.text_area("Tone of Voice Description", value=p.get("tone_of_voice", {}).get("description", ""))
        vocabulary = st.text_area("Recurring Vocabulary (one per line)", value="\n".join(p.get("vocabulary", [])))
        visual_direction = st.text_area("Visual Direction", value=p.get("visual_direction", ""))
        content_pillars = st.text_area("Content Pillars (one per line)", value="\n".join(p.get("content_pillars", [])))
        calls_to_action = st.text_area("Calls to Action (one per line)", value="\n".join(p.get("calls_to_action", [])))
        topics_to_avoid = st.text_area("Topics to Avoid (one per line)", value="\n".join(p.get("topics_to_avoid", [])))

        save = st.form_submit_button("Save Changes")

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
        st.success("Changes saved!")

    with st.expander("View Sources"):
        st.json(p.get("sources", []))

    st.divider()
    st.subheader("4. Trend Discovery")
    st.caption("Source: Google News RSS (queried using the brand's content pillars + industry)")

    if st.button("Find Relevant Trends"):
        with st.spinner("Searching for recent trends..."):
            queries = list(st.session_state.brand_profile.get("content_pillars", []))[:3]
            if industry:
                queries.append(industry)
            all_candidates = []
            seen_links = set()
            for q in queries:
                for c in search_google_news(q):
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        all_candidates.append(c)
        if not all_candidates:
            st.warning("Couldn't find trend sources right now, try again shortly")
        else:
            with st.spinner("AI is evaluating brand fit for each trend..."):
                try:
                    trends = evaluate_trend_candidates(st.session_state.brand_profile, all_candidates, language)
                    st.session_state.trends = trends
                    st.session_state.trend_pool = all_candidates
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

    if st.session_state.trends:
        for i, t in enumerate(st.session_state.trends):
            with st.expander(f"📈 {t.get('trend_name','Trend')}"):
                st.markdown(
                    f"<span style='color:#FFD54A;font-weight:700;'>Brand fit: {t.get('brand_fit_score','?')}/10</span>",
                    unsafe_allow_html=True,
                )
                st.write(t.get("description", ""))
                st.caption(f"Source: {t.get('source_url','')} | Discovered: {t.get('discovery_date','')}")
                st.info(f"Why it fits the brand: {t.get('brand_fit_explanation','')}")
                if st.button("Replace with another trend", key=f"replace_{i}"):
                    used_links = {tr.get("source_url") for tr in st.session_state.trends}
                    remaining = [c for c in st.session_state.trend_pool if c["link"] not in used_links]
                    if remaining:
                        with st.spinner("Looking for an alternative..."):
                            try:
                                new_trend = evaluate_trend_candidates(st.session_state.brand_profile, remaining, language, count=1)
                                if new_trend:
                                    st.session_state.trends[i] = new_trend[0]
                                    st.rerun()
                                else:
                                    st.warning("No suitable alternative found right now")
                            except Exception as e:
                                st.error(f"Something went wrong: {e}")
                    else:
                        st.warning("No other candidates available")
