import os
import asyncio
import requests
import json
import base64
import re
import random
import sys
import time
import pickle
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import PIL.Image
from PIL import ImageOps, ImageFilter, ImageDraw, ImageFont
import numpy as np

# ====================== إعدادات تقليل اللوج (Clean Logs) ======================
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger('googleapiclient').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('moviepy').setLevel(logging.CRITICAL)

# ====================== إصلاح توافق Pillow مع MoviePy ======================
if not hasattr(PIL.Image, 'Resampling'):
    PIL.Image.Resampling = PIL.Image
try:
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
except AttributeError:
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip
from groq import Groq
import edge_tts

# ====================== المتغيرات البيئة والإعدادات ======================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
YOUTUBE_TOKEN_B64 = os.environ.get('YOUTUBE_TOKEN')
FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID')

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
FPS = 24
HISTORY_FILE = "history.json"
SOURCE_INDEX_FILE = "source_index.json"
CHANNEL_NAME_AR = "ملوك الملعب"
CHANNEL_NAME_EN = "Kings of the Stadium"

# ====================== موديلات Groq المدعومة ======================
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

# ====================== المصادر (محدثة ومُصلحة) ======================
# [إصلاح]: حذف Yardbarker (كان يجلب روابط من مواقع خارجية)
# [إصلاح]: استبدال TalkSport (لم يظهر أي رابط في التاريخ كاملاً)
# [إضافة]: مصادر عربية وعالمية جديدة متخصصة في كرة القدم
SOURCES = [
    # --- المصادر العربية ---
    {"id": 1,  "name": "Btolat",       "url": "https://www.btolat.com/news",                    "lang": "ar"},
    {"id": 2,  "name": "Arriyadiyah",  "url": "https://www.arriyadiyah.com/",                   "lang": "ar"},
    {"id": 3,  "name": "So3ody",       "url": "https://www.so3ody.com/news",                    "lang": "ar"},  # [إصلاح]: /news بدل /
    {"id": 4,  "name": "Filgoal",      "url": "https://www.filgoal.com/articles/",              "lang": "ar"},  # [جديد]
    {"id": 5,  "name": "Kooora",       "url": "https://www.kooora.com/?news",                   "lang": "ar"},  # [جديد]
    {"id": 6,  "name": "Yalla Kora",   "url": "https://www.yallakora.com/News/Latest-News",     "lang": "ar"},  # [جديد]
    {"id": 7,  "name": "Masrawy Sport","url": "https://www.masrawy.com/sports",                 "lang": "ar"},  # [جديد]
    {"id": 8,  "name": "Goal Arabic",  "url": "https://www.goal.com/ar/news",                  "lang": "ar"},  # [جديد]
    # --- المصادر الإنجليزية ---
    {"id": 9,  "name": "London Football","url": "https://www.football.london/",                 "lang": "en"},
    {"id": 10, "name": "FourFourTwo",  "url": "https://www.fourfourtwo.com/news",               "lang": "en"},
    {"id": 11, "name": "TeamTalk",     "url": "https://www.teamtalk.com/",                      "lang": "en"},
    {"id": 12, "name": "Man Evening",  "url": "https://www.manchestereveningnews.co.uk/sport/football/", "lang": "en"},
    {"id": 13, "name": "Sky Sports",   "url": "https://www.skysports.com/football/news",        "lang": "en"},  # [جديد]
    {"id": 14, "name": "BBC Sport",    "url": "https://www.bbc.com/sport/football",             "lang": "en"},  # [جديد]
    {"id": 15, "name": "90min",        "url": "https://www.90min.com/",                         "lang": "en"},  # [جديد]
    {"id": 16, "name": "AS English",   "url": "https://en.as.com/soccer/",                     "lang": "en"},  # [جديد]
]

# ====================== الكلمات المفتاحية (محدثة + ترندات 2026) ======================
KEYWORDS_ARABIC = [
    # أساسيات
    "كرة القدم", "مباراة", "هدف", "أهداف", "ملخص", "الدوري", "الكأس",
    "البطولة", "انتقالات", "ميركاتو", "صفقة", "عاجل", "رسميا",
    "تشكيل", "مدرب", "ركلة جزاء", "تسلل", "طرد", "إنذار",
    "حكم", "فار", "VAR", "إصابة", "تصفيات", "نهائي", "نصف نهائي",
    # بطولات
    "دوري أبطال", "الكونفدرالية", "الدوري الإنجليزي", "الدوري الإسباني",
    "الدوري السعودي", "دوري روشن", "كأس العالم", "كأس الأمم", "يورو",
    "السوبر", "الدوري الإيطالي", "الدوري الألماني", "الدوري الفرنسي",
    # 🔥 ترند 2026
    "كأس العالم 2026", "مونديال 2026", "أمريكا المكسيك كندا", "المونديال",
    "تصفيات المونديال", "قرعة كأس العالم",
    # أندية عربية
    "الأهلي", "الزمالك", "بيراميدز", "المصري", "الإسماعيلي",
    "الهلال", "النصر", "الاتحاد", "الأهلي السعودي", "الشباب",
    "الوداد", "الرجاء", "الترجي", "الأهلي الطرابلسي",
    # أندية عالمية
    "ريال مدريد", "برشلونة", "ليفربول", "مانشستر سيتي", "مانشستر يونايتد",
    "أرسنال", "تشيلسي", "بايرن ميونخ", "باريس سان جيرمان", "يوفنتوس",
    "إنتر ميلان", "أتلتيكو مدريد", "بوروسيا دورتموند",
    # نجوم
    "محمد صلاح", "صلاح", "كريستيانو رونالدو", "رونالدو", "ميسي",
    "نيمار", "بنزيما", "مبابي", "هالاند", "فينيسيوس",
    "بيلينغهام", "رودريغو", "كفاراتسخيليا",
]

KEYWORDS_ENGLISH = [
    "football", "soccer", "goal", "match", "league", "cup", "transfer",
    "premier league", "laliga", "serie a", "bundesliga", "champions league",
    "world cup", "euro", "real madrid", "barcelona", "liverpool",
    "man city", "arsenal", "al ahly", "zamalek", "al hilal", "al nassr",
    "salah", "messi", "ronaldo", "mbappe", "haaland", "benzema",
    "vinicius", "bellingham", "kvaratskhelia",
    # 🔥 ترند 2026
    "world cup 2026", "transfer window", "summer transfer", "free agent",
]

STRICT_KEYWORDS = KEYWORDS_ARABIC + KEYWORDS_ENGLISH

BLACKLIST_KEYWORDS = [
    "basketball", "tennis", "nba", "f1", "formula", "politics", "economy",
    "art", "cinema", "weather", "crime", "election", "cricket", "rugby",
    "كرة سلة", "تنس", "سياسة", "اقتصاد", "فن", "سينما", "طقس",
    "جريمة", "فورمولا", "كريكيت", "رجبي",
    # [إضافة]: فلترة صفحات غير مفيدة من So3ody
    "/matches/", "/Competitions/", "/schedule", "/standings",
]

# ====================== هاشتاقات افتراضية محسّنة (SEO 2026) ======================
DEFAULT_HASHTAGS = [
    "#كرة_القدم",
    "#أخبار_كروية_عاجلة",
    "#الدوري_الإنجليزي",
    "#دوري_أبطال_أوروبا",
    "#كأس_العالم_2026",
    "#الدوري_السعودي",
    "#الأهلي",
    "#الزمالك",
    "#الهلال",
    "#النصر",
    "#ريال_مدريد",
    "#برشلونة",
    "#ليفربول",
    "#محمد_صلاح",
    "#رونالدو",
    "#ميسي",
    "#مبابي",
    "#هالاند",
    "#ملوك_الملعب",
    "#football",
]


# ====================== نظام ترتيب المصادر ======================
def get_current_source_index():
    if os.path.exists(SOURCE_INDEX_FILE):
        try:
            with open(SOURCE_INDEX_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('current_index', 0)
        except Exception as e:
            print(f"⚠️ خطأ في قراءة ملف المصادر: {e}")
            return 0
    return 0


def save_next_source_index(current_index):
    next_index = (current_index + 1) % len(SOURCES)
    data = {
        'current_index': next_index,
        'last_used_index': current_index,
        'last_used_source': SOURCES[current_index]['name'],
        'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'total_sources': len(SOURCES)
    }
    with open(SOURCE_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"📝 المصدر التالي: [{next_index + 1}/{len(SOURCES)}] {SOURCES[next_index]['name']}")


def get_current_source():
    current_index = get_current_source_index()
    # تأكد أن الـ index ضمن النطاق الجديد
    if current_index >= len(SOURCES):
        current_index = 0
    source = SOURCES[current_index]
    print(f"\n📌 ═══════════════════════════════════════════")
    print(f"📌 المصدر: [{source['id']}/{len(SOURCES)}] {source['name']} ({source['lang'].upper()})")
    print(f"📌 الرابط: {source['url']}")
    print(f"📌 ═══════════════════════════════════════════\n")
    return current_index, source


# ====================== دوال الهيستوري ======================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict):
                        return {item['link'] for item in data if 'link' in item}
                    else:
                        return set(data)
        except Exception as e:
            print(f"⚠️ خطأ في قراءة الهيستوري: {e}")
            return set()
    return set()


def save_history(link, source_name):
    data = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception:
            data = []

    new_entry = {
        "link": link,
        "source": source_name,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    data.append(new_entry)

    # الاحتفاظ بآخر 500 رابط فقط لمنع تضخم الملف
    if len(data) > 500:
        data = data[-500:]

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"✅ تم حفظ الرابط (إجمالي: {len(data)})")


# ====================== دوال التنظيف ======================
def clean_text_strict(text):
    """
    [إصلاح]: النسخة القديمة كانت تحذف كل الأحرف الإنجليزية
    مما يكسر الهاشتاقات مثل #Shorts و#VAR
    الحل: نظف النص لكن احتفظ بالأرقام والعلامات المهمة
    """
    if not text:
        return ""
    # احذف رموز التحكم والأحرف الغريبة لكن احتفظ بالعربي والإنجليزي والأرقام
    text = re.sub(r'[^\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF'
                  r'a-zA-Z0-9\s\.\,\!\?\(\)\-\#\_\:\؟\،\؛]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_arabic_only(text):
    """لتنظيف نصوص يجب أن تكون عربية فقط (مثل السكريبت الصوتي)"""
    if not text:
        return ""
    # احتفظ بالأرقام والعربي والعلامات
    text = re.sub(r'[a-zA-Z]', '', text)
    text = re.sub(r'[^\u0600-\u06FF0-9\s\.\,\!\?\(\)\-\؟\،\؛]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def download_and_flip_image(url, filename):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            img = PIL.Image.open(filename)
            img = img.convert('RGB')
            img = ImageOps.mirror(img)
            img.save(filename, 'JPEG', quality=95)
            print(f"✅ تم تحميل وعكس الصورة: {filename}")
            return True
        else:
            print(f"❌ فشل تحميل الصورة - Status: {response.status_code}")
    except Exception as e:
        print(f"❌ فشل تحميل الصورة: {e}")
    return False


# ====================== استخراج المحتوى ======================
def get_article_content(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ar,en;q=0.9',
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')

        title = ""
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()
        elif soup.title:
            title = soup.title.string or ""

        img_url = None
        for meta_prop in [("property", "og:image"), ("name", "twitter:image")]:
            tag = soup.find("meta", {meta_prop[0]: meta_prop[1]})
            if tag:
                img_url = tag.get("content")
                break
        if not img_url:
            first_img = soup.find("img", src=True)
            if first_img:
                img_url = first_img.get("src")

        if not img_url:
            return None

        paragraphs = soup.find_all('p')
        text_content = " ".join([
            p.get_text().strip()
            for p in paragraphs
            if len(p.get_text().strip()) > 30
        ])

        if len(text_content) < 500:
            return None

        return {
            'title': title,
            'text': text_content,
            'image': img_url,
            'url': url
        }
    except Exception:
        return None


# ====================== البحث عن الأخبار (مُصلح) ======================
def find_best_news():
    history = load_history()
    current_index, source = get_current_source()
    save_next_source_index(current_index)

    try:
        print(f"🔎 جاري البحث في: {source['name']}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ar,en;q=0.9',
        }
        resp = requests.get(source['url'], headers=headers, timeout=12)
        soup = BeautifulSoup(resp.content, 'html.parser')

        links = soup.find_all('a', href=True)
        base_domain = "/".join(source['url'].split('/')[:3])
        valid_links = []

        for a in links:
            href = a['href']

            # بناء الرابط الكامل
            if not href.startswith('http'):
                if href.startswith('/'):
                    href = base_domain + href
                else:
                    href = base_domain + '/' + href

            # [إصلاح]: تأكد أن الرابط من نفس الدومين (يمنع مشكلة Yardbarker)
            if base_domain not in href:
                continue

            if href in history:
                continue

            # [إصلاح]: فلترة صفحات الجداول والمسابقات من So3ody وغيره
            if any(bl in href for bl in ['/Competitions/', '/matches/', '/schedule', '/standings', '/table']):
                continue

            check_str = (href + " " + a.get_text()).lower()

            # فحص الكلمات السوداء
            if any(bl.lower() in check_str for bl in BLACKLIST_KEYWORDS):
                continue

            # فحص كلمات رياضية
            if not any(kw.lower() in check_str for kw in STRICT_KEYWORDS):
                continue

            if len(a.get_text().strip()) > 15:
                valid_links.append(href)

        # إزالة المكررات
        valid_links = list(dict.fromkeys(valid_links))
        print(f"📋 روابط محتملة: {len(valid_links)}")

        if valid_links:
            random.shuffle(valid_links)
            for chosen_link in valid_links[:12]:
                data = get_article_content(chosen_link)

                if data and len(data['text']) > 800 and data['image']:
                    title_check = data['title'].lower()
                    if any(kw.lower() in title_check for kw in STRICT_KEYWORDS):
                        print(f"🎯 خبر مناسب!")
                        data['source_name'] = source['name']
                        data['source_id'] = source['id']
                        data['source_lang'] = source['lang']
                        return data

        print(f"😔 لا يوجد خبر مناسب في {source['name']}")

    except Exception as e:
        print(f"❌ خطأ في {source['name']}: {e}")

    return None


# ====================== الذكاء الاصطناعي (SEO محسّن) ======================
def generate_ai_content(article):
    client = Groq(api_key=GROQ_API_KEY)

    # قائمة بكلمات مفتاحية ترند لإعطائها للذكاء الاصطناعي
    trending_keywords = [
        "كأس العالم 2026", "مونديال 2026", "انتقالات صيف 2026",
        "صلاح", "رونالدو", "ميسي", "مبابي", "هالاند", "فينيسيوس",
        "دوري أبطال أوروبا", "الدوري الإنجليزي الممتاز",
        "الدوري السعودي للمحترفين", "دوري روشن",
        "عاجل", "رسمياً", "الميركاتو", "إصابة خطيرة",
    ]

    prompt = f"""
أنت محلل رياضي محترف ومعلق كروي خبير ومتخصص في تحسين محركات البحث (SEO) على يوتيوب.
الجمهور المستهدف: شباب عرب (مصر، العراق، الجزائر)، 18-35 سنة، مهتمون بكرة القدم.

النص الأصلي:
العنوان: {article['title']}
المحتوى: {article['text'][:3000]}

كلمات مفتاحية ترندية يجب توظيفها بشكل طبيعي إن أمكن:
{', '.join(trending_keywords[:10])}

التعليمات الإلزامية:

[عنوان الفيديو - SEO]:
- من 60 إلى 90 حرف (يوتيوب يعرض أول 60 حرف في النتائج)
- ابدأ بكلمة قوية: (عاجل | رسمياً | حصري | مفاجأة | صدمة)
- ضع اسم النجم أو الفريق في أول 30 حرف
- أنهِ بسؤال استفزازي أو رقم: "ماذا حدث؟" أو "3 أسباب"

[وصف الفيديو - SEO]:
- 400-500 كلمة
- السطر الأول (أول 125 حرف) هو الأهم - يظهر قبل "عرض المزيد"
- أدرج الكلمات المفتاحية الرئيسية في أول 3 أسطر
- أضف قسم "الكلمات المفتاحية:" في النهاية مع 15 كلمة مفتاحية

[الهاشتاقات]:
- 20 هاشتاق بالضبط
- أول 3 هاشتاقات تظهر تحت الفيديو مباشرة - اختر الأهم
- مزيج من: اسم اللاعب، الفريق، البطولة، "عاجل"، "ملوك_الملعب"

[سكريبت الفيديو]:
- 1000-1400 كلمة عربية فصحى واضحة
- Hook أول 5 ثوانٍ: سؤال صادم أو رقم مثير
- Body: تفاصيل الخبر + تحليل + سياق تاريخي
- CTA في النهاية: "اشترك والضغط على الجرس"

[سكريبت الشورتس]:
- 60-90 ثانية (مش 30-45 - دا أقصر من اللازم)
- Hook قوي في أول 3 ثوانٍ يوقف التمرير
- بدون هاشتاقات داخل النص

أعطني JSON فقط بدون أي نص خارجه:
{{
    "video_title": "عنوان SEO محسّن للفيديو (60-90 حرف)",
    "video_script": "سكريبت الفيديو الكامل بالعربية الفصحى (1000-1400 كلمة)",
    "video_description": "وصف SEO محسّن (400-500 كلمة) ينتهي بـ\\n\\nالكلمات المفتاحية: ...",
    "shorts_title": "عنوان الشورتس (50-70 حرف)",
    "shorts_script": "سكريبت الشورتس بالعربية الفصحى (60-90 ثانية)",
    "hashtags": ["#هاشتاق1", "#هاشتاق2", "... 20 هاشتاق"],
    "facebook_post": "منشور فيسبوك جذاب مع إيموجي وكلمات مفتاحية"
}}
"""

    for model in GROQ_MODELS:
        try:
            print(f"🤖 جاري التجربة: {model}")
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a YouTube SEO expert and Arabic sports commentator. "
                            "Output ONLY valid JSON. Write all Arabic content in Modern Standard Arabic (فصحى). "
                            "Never invent facts not present in the source article. "
                            "Focus on high-CTR titles and SEO-optimized descriptions."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=8000,
                response_format={"type": "json_object"}
            )

            content = json.loads(completion.choices[0].message.content)

            # [إصلاح]: العنوان والوصف يُنظَّفان بشكل عام (يبقى إنجليزي في الهاشتاقات)
            content['video_title'] = clean_text_strict(content.get('video_title', ''))
            content['video_description'] = clean_text_strict(content.get('video_description', ''))
            content['facebook_post'] = clean_text_strict(content.get('facebook_post', ''))
            content['shorts_title'] = clean_text_strict(content.get('shorts_title', ''))

            # [إصلاح]: السكريبت الصوتي يحتاج عربية فقط (لأن TTS عربي)
            content['video_script'] = clean_arabic_only(content.get('video_script', ''))
            content['shorts_script'] = clean_arabic_only(content.get('shorts_script', ''))

            # معالجة الهاشتاقات
            tags = []
            for t in content.get('hashtags', []):
                # الهاشتاقات تبقى كما هي (عربي + إنجليزي)
                ct = t.strip().replace(' ', '_')
                if ct and not ct.startswith('#'):
                    ct = '#' + ct
                # إزالة الأحرف غير المقبولة من الهاشتاقات
                ct = re.sub(r'[^\u0600-\u06FF\u0750-\u077Fa-zA-Z0-9#_]', '', ct)
                if len(ct) > 2:
                    tags.append(ct)

            # أضف الهاشتاقات الافتراضية إن نقص العدد
            for d in DEFAULT_HASHTAGS:
                if len(tags) >= 20:
                    break
                if d not in tags:
                    tags.append(d)

            content['hashtags'] = tags[:20]

            # [تحسين SEO]: حد أقصى أرفع للعنوان
            if len(content['video_title']) > 90:
                content['video_title'] = content['video_title'][:87] + "..."
            if len(content['shorts_title']) > 70:
                content['shorts_title'] = content['shorts_title'][:67] + "..."

            # إضافة اسم القناة في نهاية الوصف
            channel_footer = (
                f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚽ قناة {CHANNEL_NAME_AR} - {CHANNEL_NAME_EN}\n"
                f"اشترك الآن واضغط على 🔔 لتصلك كل الأخبار أولاً بأول!\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            content['video_description'] = content['video_description'] + channel_footer

            print(f"✅ تم توليد المحتوى بنجاح: {model}")
            return content

        except Exception as e:
            print(f"⚠️ فشل {model}: {e}")
            continue

    print("❌ فشلت جميع الموديلات")
    return None


# ====================== توليد الصوت ======================
async def generate_audio(text, output_file):
    """صوت شاكر المصري - ar-EG-ShakirNeural"""
    voice = "ar-EG-ShakirNeural"
    rate = "-5%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_file)
    print(f"✅ تم توليد الصوت: {output_file}")
    return output_file


# ====================== إنشاء إطار الأخبار ======================
def create_news_overlay(width, height):
    img = PIL.Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bar_height = int(height * 0.12)
    bar_y = height - bar_height

    draw.rectangle([(0, bar_y), (width, height)], fill=(200, 0, 0, 230))
    draw.rectangle([(0, bar_y), (width, bar_y + 5)], fill=(255, 215, 0, 255))

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "arialbd.ttf"
    ]

    font = None
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, int(height * 0.04))
            break
        except Exception:
            continue
    if not font:
        font = ImageFont.load_default()

    text = f"{CHANNEL_NAME_AR} | {CHANNEL_NAME_EN}"
    try:
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    except Exception:
        text_width = len(text) * 20
        text_height = 40

    text_x = (width - text_width) / 2
    text_y = bar_y + (bar_height - text_height) / 2 - 5
    draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

    badge_width = int(width * 0.13)
    badge_height = int(height * 0.05)
    badge_x = width - badge_width - 10
    badge_y = bar_y - badge_height - 10

    draw.rectangle([(badge_x, badge_y), (width - 10, bar_y - 10)], fill=(255, 215, 0, 255))

    badge_font = None
    for path in font_paths:
        try:
            badge_font = ImageFont.truetype(path, int(height * 0.03))
            break
        except Exception:
            continue
    if not badge_font:
        badge_font = font

    badge_text = "عاجل"
    try:
        badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        badge_text_width = badge_bbox[2] - badge_bbox[0]
        badge_text_height = badge_bbox[3] - badge_bbox[1]
    except Exception:
        badge_text_width = 60
        badge_text_height = 30

    badge_text_x = badge_x + (badge_width - badge_text_width) / 2
    badge_text_y = badge_y + (badge_height - badge_text_height) / 2
    draw.text((badge_text_x, badge_text_y), badge_text, font=badge_font, fill=(200, 0, 0, 255))

    overlay_path = f"overlay_{width}x{height}.png"
    img.save(overlay_path)
    return overlay_path


# ====================== إنشاء الفيديو مع Zoom ======================
def create_zooming_video(image_path, audio_path, output_path, width, height, is_shorts):
    try:
        video_type = "شورتس" if is_shorts else "فيديو"
        print(f"🎬 جاري المونتاج ({video_type})...")

        audio = AudioFileClip(audio_path)
        duration = audio.duration + 1
        print(f"⏱️ المدة: {duration:.1f}ث ({duration/60:.2f} دقيقة)")

        img = ImageClip(image_path)
        aspect_ratio = img.w / img.h
        target_ratio = width / height

        if aspect_ratio > target_ratio:
            img = img.resize(height=height)
            x_center = (img.w - width) / 2
            img = img.crop(x1=x_center, width=width, height=height)
        else:
            img = img.resize(width=width)
            y_center = (img.h - height) / 2
            img = img.crop(y1=y_center, width=width, height=height)

        zoom_factor = 1.15 if is_shorts else 1.08

        def zoom_effect(t):
            return 1 + (zoom_factor - 1) * (t / duration)

        zoomed_bg = (img
                     .resize(zoom_effect)
                     .set_position('center')
                     .set_duration(duration))

        overlay_path = create_news_overlay(width, height)
        overlay_clip = (ImageClip(overlay_path)
                        .set_duration(duration)
                        .set_position(("center", "top")))

        final = CompositeVideoClip(
            [zoomed_bg, overlay_clip],
            size=(width, height)
        ).set_audio(audio)

        final.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            verbose=False,
            logger=None
        )

        if os.path.exists(overlay_path):
            os.remove(overlay_path)

        print(f"✅ تم إنشاء {video_type}: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Video Error: {e}")
        return False


# ====================== الرفع لليوتيوب ======================
def get_youtube_service():
    try:
        token_data = base64.b64decode(YOUTUBE_TOKEN_B64)
        try:
            creds = pickle.loads(token_data)
        except Exception:
            creds_data = json.loads(token_data.decode('utf-8'))
            creds = Credentials.from_authorized_user_info(creds_data)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"❌ Youtube Auth Error: {e}")
        return None


def upload_to_youtube(video_path, title, description, tags, is_shorts):
    youtube = get_youtube_service()
    if not youtube:
        return False

    video_type = "شورتس" if is_shorts else "فيديو"
    print(f"🚀 جاري رفع {video_type}...")

    final_title = title
    if is_shorts and "#Shorts" not in final_title and "#shorts" not in final_title:
        final_title = title + " #Shorts"

    hashtags_str = " ".join(tags)
    full_description = f"{description}\n\n{hashtags_str}"

    clean_tags = []
    for t in tags:
        clean_tag = t.replace("#", "").replace("_", " ").strip()
        if clean_tag:
            clean_tags.append(clean_tag)

    body = {
        'snippet': {
            'title': final_title[:100],  # حد يوتيوب 100 حرف
            'description': full_description[:5000],  # حد يوتيوب 5000 حرف
            'tags': clean_tags[:500],
            'categoryId': '17',  # Sports
            'defaultLanguage': 'ar',
            'defaultAudioLanguage': 'ar',
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False,
            'madeForKids': False,
        }
    }

    try:
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        res = None
        while res is None:
            status, res = req.next_chunk()
            if status:
                print(f"   📤 {int(status.progress() * 100)}%")

        video_id = res.get('id')
        print(f"✅ يوتيوب ({video_type}): https://youtu.be/{video_id}")
        return True

    except Exception as e:
        print(f"❌ Youtube Upload Failed: {e}")
        return False


# ====================== الرفع لفيسبوك ======================
def upload_to_facebook(video_path, message_body, hashtags_list):
    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID:
        print("⚠️ فيسبوك غير مفعل")
        return False

    print("🚀 جاري رفع الفيديو لفيسبوك...")
    hashtags_str = " ".join(hashtags_list)
    full_message = f"{message_body}\n\n{hashtags_str}"
    url = f"https://graph-video.facebook.com/v18.0/{FACEBOOK_PAGE_ID}/videos"

    try:
        file_size = os.path.getsize(video_path)
        start_response = requests.post(
            url,
            params={
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'upload_phase': 'start',
                'file_size': file_size
            }
        ).json()

        session_id = start_response.get('upload_session_id')
        if not session_id:
            print(f"❌ فشل بدء رفع فيسبوك: {start_response}")
            return False

        with open(video_path, 'rb') as f:
            requests.post(
                url,
                data={
                    'access_token': FACEBOOK_ACCESS_TOKEN,
                    'upload_phase': 'transfer',
                    'start_offset': 0,
                    'upload_session_id': session_id
                },
                files={
                    'video_file_chunk': (os.path.basename(video_path), f, 'video/mp4')
                }
            )

        finish_response = requests.post(
            url,
            data={
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'upload_phase': 'finish',
                'upload_session_id': session_id,
                'description': full_message
            }
        ).json()

        if finish_response.get('success'):
            print("✅ فيسبوك: تم الرفع")
            return True
        else:
            print(f"❌ فيسبوك فشل: {finish_response}")
            return False

    except Exception as e:
        print(f"❌ Facebook Failed: {e}")
        return False


# ====================== التنفيذ الرئيسي ======================
async def main():
    print("=" * 60)
    print("⚽ بوت ملوك الملعب - نسخة محسّنة ⚽")
    print("=" * 60)
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 المصادر: {len(SOURCES)} مصدر")
    print("=" * 60)

    article = find_best_news()
    if not article:
        print("😴 لم يتم العثور على أخبار جديدة.")
        print("💡 سيتم الانتقال للمصدر التالي في التشغيل القادم.")
        return

    print(f"\n📰 الخبر:")
    print(f"   المصدر: [{article['source_id']}] {article['source_name']}")
    print(f"   العنوان: {article['title'][:80]}...")
    print(f"   الرابط: {article['url']}")
    print(f"   المحتوى: {len(article['text'])} حرف")

    ai = generate_ai_content(article)
    if not ai:
        print("❌ فشل إنشاء المحتوى")
        return

    print(f"\n✍️ المحتوى:")
    print(f"   عنوان الفيديو: {ai['video_title']}")
    print(f"   عنوان الشورتس: {ai['shorts_title']}")
    print(f"   سكريبت الفيديو: {len(ai['video_script'])} حرف")
    print(f"   هاشتاقات: {len(ai['hashtags'])}")

    img_file = "image.jpg"
    video_audio = "video_audio.mp3"
    shorts_audio = "shorts_audio.mp3"
    video_file = "video.mp4"
    shorts_file = "shorts.mp4"

    print("\n📥 تحميل الصورة...")
    if not download_and_flip_image(article['image'], img_file):
        print("❌ فشل تحميل الصورة")
        return

    print("\n🎙️ توليد الصوت...")
    await generate_audio(ai['video_script'], video_audio)
    await generate_audio(ai['shorts_script'], shorts_audio)

    print("\n🎬 المونتاج...")
    video_success = create_zooming_video(img_file, video_audio, video_file, VIDEO_WIDTH, VIDEO_HEIGHT, False)
    shorts_success = create_zooming_video(img_file, shorts_audio, shorts_file, SHORTS_WIDTH, SHORTS_HEIGHT, True)

    if video_success:
        print("\n📤 رفع الفيديو الطويل...")
        upload_to_youtube(video_file, ai['video_title'], ai['video_description'], ai['hashtags'], False)
        upload_to_facebook(video_file, ai['facebook_post'], ai['hashtags'])

    if shorts_success:
        print("\n📤 رفع الشورتس...")
        upload_to_youtube(shorts_file, ai['shorts_title'], ai['shorts_script'], ai['hashtags'], True)

    print("\n💾 حفظ في الهيستوري...")
    save_history(article['url'], article['source_name'])

    print("\n🧹 تنظيف الملفات...")
    for f in [img_file, video_audio, shorts_audio, video_file, shorts_file]:
        if os.path.exists(f):
            os.remove(f)
            print(f"   ✓ {f}")

    print("\n" + "=" * 60)
    print("✅ اكتمل التنفيذ")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
