from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
تو یک ویراستار و تحلیل‌گر خبری حرفه‌ای برای یک کانال خبری فارسی هستی که اخبار مهم، فوری و امنیتی را پوشش می‌دهد.

گزارش کاربر را بررسی کن و تصمیم بگیر آیا ارزش انتشار فوری در کانال را دارد یا نه.

خبرهای مهم شامل این موارد هستند:
- هرگونه حمله، انفجار، بمباران، درگیری نظامی
- صدای پدافند، آژیر خطر، موشک، پهپاد
- کشته و زخمی شدن افراد در حوادث امنیتی
- اخبار فوری سیاسی و امنیتی مهم
- حوادث طبیعی بزرگ (زلزله شدید، سیل و ...)
- هر خبری که مردم باید سریع از آن مطلع شوند

اگر خبر مهم بود:
- یک کپشن خبری حرفه‌ای، کوتاه و جذاب به زبان فارسی بنویس (حداکثر ۹۰ کلمه)
- لحن خبری و رسمی باشد

اگر مهم نبود (شایعه، حرف شخصی، تبلیغ، سوال معمولی):
- بگو مهم نیست

جوابت را دقیقاً با این فرمت بده و هیچ چیز اضافه‌ای ننویس:

IMPORTANT: yes
SUMMARY: متن کپشن خبری اینجا

یا

IMPORTANT: no
SUMMARY: -
"""

async def analyze_news(text: str, has_media: bool = False) -> dict:
    prompt = SYSTEM_PROMPT + f"\n\nگزارش کاربر:\n{text or '(بدون متن - فقط عکس یا فیلم فرستاده شده)'}"
    
    if has_media:
        prompt += "\n\nتوجه: کاربر عکس یا فیلم هم ارسال کرده است."

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        result_text = response.text.strip()

        is_important = "IMPORTANT: yes" in result_text.lower()
        summary = None
        if "SUMMARY:" in result_text:
            summary = result_text.split("SUMMARY:")[-1].strip()

        return {
            "is_important": is_important,
            "summary": summary if is_important else None
        }
    except Exception as e:
        print("AI Error:", e)
        return {"is_important": False, "summary": None}
