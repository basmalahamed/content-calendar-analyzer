import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import os
import io
import html
import hashlib
from datetime import date, timedelta
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import pandas as pd
import google.generativeai as genai

st.set_page_config(page_title="Tempo", page_icon="🔍", layout="wide")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

for key, default in [("brand_profile", None), ("trends", None), ("trend_pool", []), ("calendar", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

PILLAR_PALETTE = ["#2E86FF", "#FFD54A", "#3DDC84", "#FF8A65", "#B388FF", "#4DD0E1", "#F06292"]

def pillar_color(pillar_name):
    idx = int(hashlib.md5(pillar_name.encode("utf-8")).hexdigest(), 16) % len(PILLAR_PALETTE)
    return PILLAR_PALETTE[idx]

def score_color(score):
    try:
        score = float(score)
    except Exception:
        return "#AAAAAA"
    if score >= 70:
        return "#1E9E5A"
    if score >= 40:
        return "#B8860B"
    return "#D9463A"

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

معلومات إضافية من العميل:
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

رجّعي مصفوفة JSON فقط بالشكل ده لكل ترند مختار:
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

# ---------- Calendar generation ----------

CALENDAR_ITEM_SCHEMA = """{
  "date": "YYYY-MM-DD",
  "recommended_time": "HH:MM",
  "platform": "...",
  "format": "...",
  "content_pillar": "...",
  "objective": "...",
  "content_idea": "...",
  "hook": "...",
  "caption_direction": "...",
  "visual_direction": "...",
  "call_to_action": "...",
  "trend_used": {"trend_name": null, "source_url": null, "discovery_date": null, "brand_fit_explanation": null},
  "viral_potential_score": {
    "score": 0,
    "factors": {"freshness": 0, "relevance": 0, "brand_fit": 0, "shareability": 0, "value": 0, "platform_suitability": 0},
    "disclaimer": "This is an estimate only and does not guarantee virality."
  }
}"""

def generate_calendar(brand_profile, trends, platforms, objective, language, duration, posting_frequency, start_date):
    weeks_map = {"1 Week": 1, "2 Weeks": 2, "1 Month": 4}
    weeks = weeks_map[duration]
    total_posts = weeks * posting_frequency
    end_date = start_date + timedelta(weeks=weeks)
    trends_text = json.dumps(trends, ensure_ascii=False) if trends else "لا يوجد ترندات مختارة"
    prompt = f"""أنت مخطط محتوى محترف. عندك Brand Profile وقائمة ترندات مقيّمة. ابني خطة محتوى (content calendar) كاملة.

Brand Profile:
{json.dumps(brand_profile, ensure_ascii=False)}

الترندات المتاحة (استخدمي منها بس لو تناسب البوست فعلاً، غير كده سيبي trend_used فاضي/null):
{trends_text}

المنصات: {', '.join(platforms) if platforms else 'أي منصة مناسبة'}
هدف الحملة: {objective}
الفترة الزمنية: من {start_date} إلى {end_date}
عدد البوستات المطلوب: {total_posts} تقريباً (بمعدل {posting_frequency} بوست أسبوعياً)
لغة المحتوى: {language}

قواعد مهمة:
- وزّعي البوستات على content_pillars مختلفة من الـ Brand Profile، متكرريش نفس الـ pillar في كل بوست
- نوّعي الـ format حسب كل منصة
- الـ viral_potential_score تقدير فقط، ومتضمنيش انتشار فعلي أبداً - اكتبي ده في الـ disclaimer
- كل تاريخ لازم يكون داخل الفترة الزمنية المحددة
- مهم جداً: كل عامل في factors (freshness, relevance, brand_fit, shareability, value, platform_suitability) لازم يكون رقم من 0 لـ10 بس. أما score الكلي فلازم يكون رقم من 0 لـ100 (يعني تقريباً مجموع الستة عوامل بعد ضربهم في نسبة مناسبة عشان يوصلوا لمقياس من 100). مثال صحيح: لو كل العوامل حواليها 7 من 10، يبقى score الكلي المفروض يكون حوالي 70 من 100، مش 7.

رجّعي مصفوفة JSON فقط (من غير أي كلام إضافي)، كل عنصر بالشكل ده بالظبط:
[{CALENDAR_ITEM_SCHEMA}]
"""
    model = genai.GenerativeModel("gemini-3.6-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def regenerate_calendar_item(brand_profile, trends, language, slot):
    trends_text = json.dumps(trends, ensure_ascii=False) if trends else "لا يوجد"
    prompt = f"""أنت مخطط محتوى محترف. عايزين فكرة جديدة ومختلفة عن الأول لنفس الخانة دي بالظبط (متغيريش التاريخ ولا المنصة ولا الفورمات ولا الـ content pillar):

Brand Profile:
{json.dumps(brand_profile, ensure_ascii=False)}

الترندات المتاحة:
{trends_text}

الخانة الثابتة:
- date: {slot.get('date')}
- platform: {slot.get('platform')}
- format: {slot.get('format')}
- content_pillar: {slot.get('content_pillar')}
- objective: {slot.get('objective')}

لغة المحتوى: {language}

رجّعي عنصر JSON واحد فقط (من غير مصفوفة، من غير أي كلام إضافي) بالشكل ده، وخلي date/platform/format/content_pillar/objective زي ما هما فوق بالظبط، ومهم جداً score الكلي يبقى من 0 لـ100:
{CALENDAR_ITEM_SCHEMA}
"""
    model = genai.GenerativeModel("gemini-3.6-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

# ---------- Export helpers ----------

def flatten_calendar(calendar_items):
    rows = []
    for item in calendar_items:
        vps = item.get("viral_potential_score", {}) or {}
        factors = vps.get("factors", {}) or {}
        trend = item.get("trend_used") or {}
        rows.append({
            "Date": item.get("date", ""),
            "Time": item.get("recommended_time", ""),
            "Platform": item.get("platform", ""),
            "Format": item.get("format", ""),
            "Content Pillar": item.get("content_pillar", ""),
            "Objective": item.get("objective", ""),
            "Content Idea": item.get("content_idea", ""),
            "Hook": item.get("hook", ""),
            "Caption Direction": item.get("caption_direction", ""),
            "Visual Direction": item.get("visual_direction", ""),
            "Call to Action": item.get("call_to_action", ""),
            "Trend Used": trend.get("trend_name") or "",
            "Trend Source": trend.get("source_url") or "",
            "Trend Discovery Date": trend.get("discovery_date") or "",
            "Trend Brand Fit": trend.get("brand_fit_explanation") or "",
            "Viral Score (0-100, estimate)": vps.get("score", ""),
            "Freshness": factors.get("freshness", ""),
            "Relevance": factors.get("relevance", ""),
            "Brand Fit": factors.get("brand_fit", ""),
            "Shareability": factors.get("shareability", ""),
            "Value": factors.get("value", ""),
            "Platform Suitability": factors.get("platform_suitability", ""),
        })
    return pd.DataFrame(rows)

def render_profile_card(icon, label, content, color):
    safe_content = html.escape(content) if content else "<i style='color:#888'>Not set</i>"
    st.markdown(
        f"""<div style='background:#1C1F26;border-top:4px solid {color};border-radius:10px;
        padding:16px;margin-bottom:16px;min-height:150px;'>
        <div style='font-size:20px;margin-bottom:8px;'>{icon}
        <span style='font-size:15px;color:{color};font-weight:700;'> {html.escape(label)}</span></div>
        <div style='font-size:15px;line-height:1.6;color:#FFFFFF;'>{safe_content}</div>
        </div>""",
        unsafe_allow_html=True,
    )

# ---------- UI ----------

st.title("Basata")
st.caption("Analyzes a brand's website, extracts a Brand Profile, finds relevant trends, and generates a content calendar.")

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
                    st.session_state.calendar = None
                    st.success("Analysis complete! Scroll down to see your Brand Profile.")
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

if st.session_state.brand_profile:
    st.divider()
    st.subheader("3. Brand Profile")
    p = st.session_state.brand_profile

    profile_cards = [
        ("🎯", "Positioning", p.get("positioning", ""), "#2E86FF"),
        ("👥", "Target Audience", p.get("target_audience", ""), "#FF8A65"),
        ("🛍️", "Products & Services", ", ".join(p.get("products_services", [])), "#3DDC84"),
        ("🗣️", "Tone of Voice", p.get("tone_of_voice", {}).get("description", ""), "#B388FF"),
        ("🔤", "Vocabulary", ", ".join(p.get("vocabulary", [])), "#4DD0E1"),
        ("🎨", "Visual Direction", p.get("visual_direction", ""), "#F06292"),
        ("📌", "Content Pillars", ", ".join(p.get("content_pillars", [])), "#FFD54A"),
        ("📢", "Calls to Action", ", ".join(p.get("calls_to_action", [])), "#7C4DFF"),
        ("🚫", "Topics to Avoid", ", ".join(p.get("topics_to_avoid", [])), "#26C6DA"),
    ]

    cardcols = st.columns(3)
    for idx, (icon, label, content, color) in enumerate(profile_cards):
        with cardcols[idx % 3]:
            render_profile_card(icon, label, content, color)

    with st.expander("✏️ Edit Brand Profile"):
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
            st.rerun()

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
                    f"<span style='color:#B8860B;font-weight:700;'>Brand fit: {t.get('brand_fit_score','?')}/10</span>",
                    unsafe_allow_html=True,
                )
                st.write(t.get("description", ""))
                st.caption(f"Source: {t.get('source_url','')} | Discovered: {t.get('discovery_date','')}")
                st.info(f"Why it fits the brand: {t.get('brand_fit_explanation','')}")
                if st.button("Replace with another trend", key=f"replace_trend_{i}"):
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

    st.divider()
    st.subheader("5. Content Calendar")

    c1, c2, c3 = st.columns(3)
    with c1:
        duration = st.selectbox("Calendar Duration", ["1 Week", "2 Weeks", "1 Month"])
    with c2:
        posting_frequency = st.number_input("Posts per week", min_value=1, max_value=14, value=3)
    with c3:
        start_date = st.date_input("Start Date", value=date.today())

    if st.button("Generate Content Calendar", type="primary"):
        with st.spinner("AI is building your content calendar... this may take a moment"):
            try:
                calendar_items = generate_calendar(
                    st.session_state.brand_profile,
                    st.session_state.trends,
                    platforms, objective, language,
                    duration, posting_frequency, start_date,
                )
                st.session_state.calendar = calendar_items
                st.success(f"Generated {len(calendar_items)} posts!")
            except Exception as e:
                st.error(f"Something went wrong: {e}")

    if st.session_state.calendar:
        calendar_items = st.session_state.calendar
        df_summary = pd.DataFrame(calendar_items)

        st.markdown("#### Distribution Overview")
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.caption("Posts by Content Pillar")
            pillar_counts = df_summary["content_pillar"].value_counts()
            st.bar_chart(pillar_counts)
        with chart_col2:
            st.caption("Posts by Platform")
            platform_counts = df_summary["platform"].value_counts()
            st.bar_chart(platform_counts)

        view_mode = st.radio("View", ["Table", "Calendar Grid"], horizontal=True)

        if view_mode == "Table":
            rows_html = ""
            for item in calendar_items:
                pillar = item.get("content_pillar", "")
                pcolor = pillar_color(pillar)
                score = item.get("viral_potential_score", {}).get("score", 0)
                scolor = score_color(score)
                rows_html += f"""<tr>
                    <td style='padding:6px;border-bottom:1px solid #333;'>{html.escape(str(item.get('date','')))}</td>
                    <td style='padding:6px;border-bottom:1px solid #333;'>{html.escape(str(item.get('recommended_time','')))}</td>
                    <td style='padding:6px;border-bottom:1px solid #333;'>{html.escape(str(item.get('platform','')))}</td>
                    <td style='padding:6px;border-bottom:1px solid #333;'>{html.escape(str(item.get('format','')))}</td>
                    <td style='padding:6px;border-bottom:1px solid #333;'><span style='background:{pcolor};color:#0E1117;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600;'>{html.escape(pillar)}</span></td>
                    <td style='padding:6px;border-bottom:1px solid #333;'>{html.escape(str(item.get('content_idea','')))}</td>
                    <td style='padding:6px;border-bottom:1px solid #333;'><span style='color:{scolor};font-weight:700;'>{html.escape(str(score))}/100</span></td>
                </tr>"""
            table_html = f"""<table style='width:100%;border-collapse:collapse;font-size:14px;'>
                <thead><tr style='text-align:left;border-bottom:2px solid #555;'>
                    <th style='padding:6px;'>Date</th><th style='padding:6px;'>Time</th><th style='padding:6px;'>Platform</th>
                    <th style='padding:6px;'>Format</th><th style='padding:6px;'>Pillar</th><th style='padding:6px;'>Idea</th><th style='padding:6px;'>Viral Score</th>
                </tr></thead>
                <tbody>{rows_html}</tbody></table>"""
            st.markdown(table_html, unsafe_allow_html=True)
        else:
            items_by_date = {}
            for item in calendar_items:
                items_by_date.setdefault(item.get("date", ""), []).append(item)
            sorted_dates = sorted(items_by_date.keys())
            weeks_grouped = {}
            for d in sorted_dates:
                try:
                    y, w, _ = date.fromisoformat(d).isocalendar()
                    weeks_grouped.setdefault((y, w), []).append(d)
                except Exception:
                    pass
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for (y, w), dates_in_week in weeks_grouped.items():
                st.markdown(f"**Week {w}, {y}**")
                cols = st.columns(7)
                week_start = date.fromisocalendar(y, w, 1)
                for offset in range(7):
                    day = week_start + timedelta(days=offset)
                    day_str = day.isoformat()
                    with cols[offset]:
                        st.caption(f"{day_names[offset]} {day.strftime('%d/%m')}")
                        for item in items_by_date.get(day_str, []):
                            pcolor = pillar_color(item.get("content_pillar", ""))
                            idea_short = (item.get("content_idea", "")[:40] + "…") if len(item.get("content_idea", "")) > 40 else item.get("content_idea", "")
                            st.markdown(
                                f"<div style='background:{pcolor};color:#0E1117;padding:6px;border-radius:6px;margin-bottom:4px;font-size:12px;'>"
                                f"<b>{html.escape(item.get('platform',''))}</b><br>{html.escape(idea_short)}</div>",
                                unsafe_allow_html=True,
                            )

        st.markdown("#### Post Details")
        for i, item in enumerate(calendar_items):
            title = f"{item.get('date','')} — {item.get('platform','')} — {item.get('content_idea','')[:50]}"
            with st.expander(title):
                colA, colB = st.columns(2)
                with colA:
                    st.write(f"**Content Pillar:** {item.get('content_pillar','')}")
                    st.write(f"**Objective:** {item.get('objective','')}")
                    st.write(f"**Format:** {item.get('format','')}")
                    st.write(f"**Hook:** {item.get('hook','')}")
                    st.write(f"**Caption Direction:** {item.get('caption_direction','')}")
                    st.write(f"**Visual Direction:** {item.get('visual_direction','')}")
                    st.write(f"**Call to Action:** {item.get('call_to_action','')}")
                with colB:
                    vps = item.get("viral_potential_score", {}) or {}
                    st.markdown(f"<span style='color:{score_color(vps.get('score',0))};font-weight:700;font-size:18px;'>Viral Potential: {vps.get('score','?')}/100 (estimate)</span>", unsafe_allow_html=True)
                    st.caption(vps.get("disclaimer", "This is an estimate only and does not guarantee virality."))
                    factors = vps.get("factors", {}) or {}
                    if factors:
                        st.table(pd.DataFrame([factors]).T.rename(columns={0: "Score (0-10)"}))
                    trend = item.get("trend_used") or {}
                    if trend.get("trend_name"):
                        st.write(f"**Trend used:** {trend.get('trend_name')}")
                        st.caption(f"Source: {trend.get('source_url','')} | Discovered: {trend.get('discovery_date','')}")
                        st.write(f"**Brand fit:** {trend.get('brand_fit_explanation','')}")

                if st.button("Regenerate this idea", key=f"regen_{i}"):
                    with st.spinner("Generating a new idea for this slot..."):
                        try:
                            new_item = regenerate_calendar_item(st.session_state.brand_profile, st.session_state.trends, language, item)
                            st.session_state.calendar[i] = new_item
                            st.rerun()
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")

        st.markdown("#### Export")
        df_export = flatten_calendar(calendar_items)
        exp1, exp2 = st.columns(2)
        with exp1:
            csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Download CSV", data=csv_bytes, file_name="content_calendar.csv", mime="text/csv")
        with exp2:
            excel_buffer = io.BytesIO()
            df_export.to_excel(excel_buffer, index=False, engine="openpyxl")
            st.download_button("Download Excel", data=excel_buffer.getvalue(), file_name="content_calendar.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
