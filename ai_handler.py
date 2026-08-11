import re
from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

DANGER_WORDS = [
    "حمله",
    "انفجار",
    "بمباران",
    "موشک",
    "پهپاد",
    "پدافند",
    "آژیر",
    "تیراندازی",
    "درگیری",
    "کشته",
    "زخمی",
    "میزنن",
    "می‌زنن",
    "زیر آتش",
]

SYSTEM_PROMPT = """
تو یک سیستم تشخیص خبر فوری برای کانال خبری هستی.

قوانین:

- هر گزارشی درباره حمله، انفجار، بمباران، موشک، پهپاد، پدافند، تیراندازی، درگیری نظامی، کشته یا زخمی شدن مهم است.
- جملات ناقص و محاوره‌ای نیز مهم محسوب می‌شوند.
- فقط زمانی IMPORTANT: no بده که کاملاً مشخص باشد گزارش خبری مهمی نیست.

اگر مهم بود:
یک کپشن خبری رسمی، کوتاه و جذاب به فارسی بنویس (حداکثر ۸۰ کلمه).

فقط با این فرمت پاسخ بده:

IMPORTANT: yes
SUMMARY: متن خبر

یا

IMPORTANT: no
SUMMARY: -
"""


async def analyze_news(text: str, has_media: bool = False) -> dict:
    user_text = text.strip() if text else "(بدون متن)"

    emergency_match = any(
        word in user_text.lower()
        for word in DANGER_WORDS
    )

    prompt = SYSTEM_PROMPT + f"\n\nگزارش کاربر:\n{user_text}"

    if has_media:
        prompt += "\n\nکاربر عکس یا ویدیو نیز ارسال کرده است."

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )

        raw_text = response.text.strip()

        important_match = re.search(
            r"IMPORTANT\s*:\s*(yes|no)",
            raw_text,
            re.IGNORECASE
        )

        summary_match = re.search(
            r"SUMMARY\s*:\s*(.*)",
            raw_text,
            re.IGNORECASE | re.DOTALL
        )

        is_important = False

        if important_match:
            is_important = (
                important_match.group(1).lower() == "yes"
            )

        if emergency_match:
            is_important = True

        summary = None

        if summary_match:
            summary = summary_match.group(1).strip()

        return {
            "is_important": is_important,
            "summary": summary if is_important else None
        }

    except Exception as e:
        print("AI Error:", e)

        if emergency_match:
            return {
                "is_important": True,
                "summary": f"گزارش فوری: {user_text}"
            }

        return {
            "is_important": False,
            "summary": None
        }
