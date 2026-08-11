from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
تو یک سیستم تشخیص خبر فوری برای کانال خبری هستی.

قانون خیلی مهم:
- هر گزارشی که درباره حمله، بمباران، زدن شهر، صدای انفجار، پدافند، موشک، پهپاد، آژیر، درگیری نظامی، کشته و زخمی باشد → حتماً IMPORTANT: yes
- حتی اگر جمله ناقص یا محاوره‌ای باشد (مثل «تهران رو دارن می‌زنن» یا «صدای پدافند میاد») باز هم مهم حساب کن
- فقط وقتی IMPORTANT: no بده که کاملاً واضح باشد حرف شخصی، شایعه بی‌اساس، تبلیغ یا سوال معمولی است

اگر مهم بود:
یک کپشن خبری کوتاه، رسمی و جذاب به فارسی بنویس (حداکثر ۸۰ کلمه).

فرمت جوابت باید دقیقاً این باشد و هیچ چیز دیگری ننویس:

IMPORTANT: yes
SUMMARY: متن کپشن اینجا

یا

IMPORTANT: no
SUMMARY: -
"""

async def analyze_news(text: str, has_media: bool = False) -> dict:
    user_text = text.strip() if text else "(بدون متن)"
    
    prompt = SYSTEM_PROMPT + f"\n\nگزارش کاربر:\n{user_text}"
    
    if has_media:
        prompt += "\n\n(کاربر عکس یا فیلم هم فرستاده)"

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        result_text = response.text.strip().lower()

        is_important = "important: yes" in result_text
        
        summary = None
        if "summary:" in result_text:
            # استخراج خلاصه
            parts = response.text.split("SUMMARY:")
            if len(parts) > 1:
                summary = parts[-1].strip()
                # پاک کردن چیزهای اضافی
                summary = summary.split("\n")[0].strip()

        return {
            "is_important": is_important,
            "summary": summary if is_important else None
        }
    except Exception as e:
        print("AI Error:", e)
        # در صورت خطا، اگر کلمات کلیدی حمله داشت، مهم حساب کن
        danger_words = ["می‌زنن", "میزنن", "بمب", "انفجار", "پدافند", "موشک", "پهپاد", "حمله", "آژیر"]
        if any(word in user_text for word in danger_words):
            return {
                "is_important": True,
                "summary": f"گزارش فوری: {user_text}"
            }
        return {"is_important": False, "summary": None}
