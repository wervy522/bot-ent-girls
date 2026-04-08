"""
Smile-ротатор: заголовки с эмодзи, интервал 18-22 минуты.
Запускается как отдельный systemd сервис google-ads-smile-{campaign_id}.
"""
import json
import sys
import time
import random
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def _setup_logging(campaign_id: str):
    log_file = f"/var/log/google-ads-smile-{campaign_id}.log"
    if not os.access("/var/log", os.W_OK):
        log_file = f"/tmp/google-ads-smile-{campaign_id}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [SMILE] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ── Стартовый пул с эмодзи ─────────────────────────────────────────────────

INITIAL_HEADLINES = [
    "🤔 Try Guru Free Today",
    "🚀 Master New Skills Fast",
    "💡 Your Personal AI Tutor",
    "🎯 Reach Your Goals Faster",
    "💪 Unlock Your Potential",
    "🎓 Study Less, Learn More",
    "🤩 Your Goals Start Here",
    "🏆 Level Up Your Skills",
    "🙌 Achieve More with Guru",
    "🧠 Get Smarter Every Day",
    "🚀 Learn Fast, Grow Faster",
    "🎯 Turn Goals into Reality",
    "🤓 Be Better Tomorrow",
    "🏅 Master Your Craft",
    "💡 Always Be Learning",
    "🧠 Sharpen Your Mind Daily",
    "🚀 Get Ahead with Guru",
    "🤔 Start Small, Win Big",
    "💪 Results in Days",
    "🎯 Progress Every Day",
    "🏆 Try It Risk Free",
    "🙌 Grow with Guru Daily",
    "🎓 Make Learning a Habit",
    "💡 Free Trial, No Card",
    "🤩 Learn on Your Schedule",
    "🧠 Smart Learning for You",
    "🏅 Get Guru for Free",
    "🤔 Your AI Tutor Awaits",
    "🎯 Skills That Pay Off",
    "💪 Hit Your Goals Faster",
    "🏆 One App, All Skills",
    "🤩 Boost Your Productivity",
    "🎓 Learn Anything, Anytime",
    "🧠 Invest in Yourself",
    "🚀 Your Success Starts Now",
    "🤔 Focus on What Matters",
    "💡 AI-Powered Learning App",
    "🎯 Download Guru Now",
    "💪 Start Your Free Trial",
    "🏆 Learn Smarter with Guru",
    "🙌 Build Better Habits",
    "🤓 Think Bigger with Guru",
    "🎓 No More Wasted Time",
    "🧠 Stay Ahead with Guru",
    "🚀 Expert Knowledge Daily",
    "🤔 Your Personal Coach",
    "💡 New Skills, New You",
    "🎯 Be Better Tomorrow",
    "🏅 Knowledge at Your Side",
    "🤩 Your Goals Start Here",
]

INITIAL_DESCRIPTIONS = [
    "🤔 Guru helps you learn faster with AI coaching. Start your free trial today!",
    "🚀 Achieve your goals with expert guidance from Guru. Download now, try free.",
    "🎯 Join millions of learners. Get smarter with Guru every single day.",
    "💡 Unlock your potential with Guru smart learning system. No commitments.",
    "💪 Learn smarter, not harder. Guru adapts to your pace. Try it free now.",
    "🎓 Guru guides you step by step toward your goals. Try it free, no card needed.",
    "🧠 Smart learning that fits your schedule. Download Guru and start in minutes.",
    "🏆 Build better habits with Guru. Personalized plans, real results. Free trial.",
    "🤩 Guru users achieve goals 3x faster. Join them today and start for free.",
    "🙌 Your goals are closer than you think. Let Guru show you the way. Try free.",
    "💡 Get personalized learning plans from Guru AI. Free to try, easy to start.",
    "🎯 Guru makes learning effortless. Thousands of topics, one app. Download free.",
    "🤔 Stop procrastinating. Start with Guru and see results in days. Free trial.",
    "🧠 Guru adapts to your learning style. Smarter every session. Try it free now.",
    "🏅 Master any skill with Guru. AI-powered coaching right on your iPhone. Free.",
    "🚀 With Guru, every minute counts. Learn efficiently and reach goals sooner.",
    "💪 No fluff, just results. Guru gives you focused learning that actually works.",
    "🎓 Thousands of users trust Guru to help them grow. Start your free trial now.",
    "🤓 Download Guru today and get a personalized path to your goals. 100% free.",
    "🏆 Guru keeps you on track every day. Small steps, big results. Try it free.",
    "🎯 Whether career or personal goals, Guru has a plan for you. Start for free.",
    "🤩 Guru is the app that turns your potential into real achievement. Try free.",
    "💡 Science-backed learning techniques built into Guru. Start your trial today.",
    "🧠 Guru fits into any lifestyle. Learn in 5 minutes or 50. Always free to try.",
    "🙌 Your competition is already using Guru. Don't fall behind — start for free.",
    "🚀 Guru turns big ambitions into daily actions. Download and try it free now.",
    "🤔 Set a goal. Let Guru build the plan. Start your free trial in seconds.",
    "💪 Guru helps busy people learn more in less time. Try free, no card required.",
    "🏅 Level up your skills with Guru's expert-designed courses. Free trial today.",
    "🎓 From idea to achievement, Guru is with you every step. Download it free.",
]

# ── Файлы состояния ────────────────────────────────────────────────────────

_STATE_DIR = "/var/lib/google-ads-rotator"
if not os.path.exists(_STATE_DIR):
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
    except PermissionError:
        _STATE_DIR = "/tmp"


def _state_file(campaign_id: str) -> str:
    return os.path.join(_STATE_DIR, f"state_smile_{campaign_id}.json")


def _load_state(campaign_id: str) -> dict:
    path = _state_file(campaign_id)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "available_headlines": INITIAL_HEADLINES[:],
        "available_descriptions": INITIAL_DESCRIPTIONS[:],
        "used_headlines": [],
        "used_descriptions": [],
    }


def _save_state(campaign_id: str, state: dict):
    with open(_state_file(campaign_id), "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── Генерация новых текстов через Claude ───────────────────────────────────

def _generate_new_texts(used_headlines: list, used_descriptions: list) -> tuple[list, list]:
    """Генерирует 50 новых заголовков с эмодзи и 30 описаний через OpenRouter API."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )

    used_h_str = "\n".join(f"- {h}" for h in used_headlines[-100:])
    used_d_str = "\n".join(f"- {d}" for d in used_descriptions[-60:])

    prompt = f"""You are a Google Ads copywriter for Guru — an iOS app for personal development, learning, and achieving life goals.

Generate NEW ad copy that has NOT been used before.

Already used headlines (do NOT repeat or closely paraphrase these):
{used_h_str}

Already used descriptions (do NOT repeat or closely paraphrase these):
{used_d_str}

Generate exactly:
- 50 headlines (max 30 characters each including emoji, no punctuation at end)
- 30 descriptions (max 90 characters each)

IMPORTANT for headlines AND descriptions:
- EVERY headline and EVERY description MUST start with one of these emojis ONLY: 🤔 🚀 💡 🎯 💪 🎓 🤩 🏆 🙌 🧠 🤓 🏅
- Do NOT use: ✨ 💫 🔥 💥 ⚡ 🌟 🌈 ⭐ 🔑 🌍 or any other emojis
- Format: [emoji][space][text]
- Headlines: keep total length under 30 characters including the emoji
- Descriptions: keep total length under 90 characters including the emoji
- Examples headlines: "🤔 Try Guru Free Today", "🚀 Learn Fast, Grow More"
- Examples descriptions: "🎯 Guru helps you learn faster with AI. Start your free trial today!", "🧠 Achieve goals 3x faster with Guru. Download now and try it free."

Focus on: free trial, personal growth, AI coaching, goals, productivity, learning, self-improvement.
Target audience: iOS users in the US, 18-45 years old.

Reply ONLY with valid JSON in this exact format:
{{
  "headlines": ["headline1", "headline2", ...],
  "descriptions": ["description1", "description2", ...]
}}"""

    log.info("Генерирую новые emoji-тексты через OpenRouter API...")
    response = client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)
    headlines = [h[:30] for h in data["headlines"]]
    descriptions = [d[:90] for d in data["descriptions"]]

    log.info(f"Сгенерировано: {len(headlines)} заголовков, {len(descriptions)} описаний")
    return headlines, descriptions


# ── Выборка текстов ────────────────────────────────────────────────────────

def _pick_texts(campaign_id: str) -> tuple[list, list]:
    state = _load_state(campaign_id)

    if len(state["available_headlines"]) < 2:
        log.info(f"Заголовков осталось {len(state['available_headlines'])} — генерирую новые")
        new_h, new_d = _generate_new_texts(state["used_headlines"], state["used_descriptions"])
        state["available_headlines"] = new_h
        state["available_descriptions"] = new_d
        state["used_headlines"] = []
        state["used_descriptions"] = []

    if len(state["available_descriptions"]) < 1:
        log.info(f"Описаний осталось 0 — генерирую новые")
        new_h, new_d = _generate_new_texts(state["used_headlines"], state["used_descriptions"])
        state["available_headlines"] = new_h
        state["available_descriptions"] = new_d
        state["used_headlines"] = []
        state["used_descriptions"] = []

    headlines = random.sample(state["available_headlines"], 2)
    descriptions = random.sample(state["available_descriptions"], 1)

    for h in headlines:
        state["available_headlines"].remove(h)
        state["used_headlines"].append(h)
    for d in descriptions:
        state["available_descriptions"].remove(d)
        state["used_descriptions"].append(d)

    _save_state(campaign_id, state)
    log.info(
        f"Осталось в пуле: {len(state['available_headlines'])} заголовков, "
        f"{len(state['available_descriptions'])} описаний"
    )
    return headlines, descriptions


# ── Основная логика ────────────────────────────────────────────────────────

def update_ads(campaign_id: str, customer_id: str = None):
    from google_ads_mcp.client import get_client, get_customer_id
    from google_ads_mcp.tools.assets import list_ad_group_ads, update_app_ad_texts

    client = get_client()
    cid = customer_id or get_customer_id()

    ads = list_ad_group_ads(client, cid, campaign_id)
    if not ads:
        log.warning(f"Кампания {campaign_id}: объявлений не найдено")
        return

    headlines, descriptions = _pick_texts(campaign_id)

    for ad in ads:
        try:
            update_app_ad_texts(client, cid, ad["ad_id"], headlines, descriptions, exempt_policy_violations=True)
            log.info(
                f"Ad {ad['ad_id']} ({ad['ad_group_name']}) обновлён.\n"
                f"  H: {headlines}\n"
                f"  D: {descriptions}"
            )
        except Exception as e:
            log.error(f"Ad {ad['ad_id']} — ошибка: {e}")


def run(campaign_id: str, customer_id: str = None, min_minutes: int = 18, max_minutes: int = 22):
    _setup_logging(campaign_id)
    cid_info = f", customer: {customer_id}" if customer_id else ""
    log.info(f"Smile-ротатор запущен. Кампания: {campaign_id}{cid_info}, интервал: {min_minutes}-{max_minutes} мин")

    while True:
        try:
            update_ads(campaign_id, customer_id)
        except Exception as e:
            log.error(f"Ошибка обновления: {e}")

        interval = random.randint(min_minutes * 60, max_minutes * 60)
        next_run = datetime.fromtimestamp(time.time() + interval).strftime("%H:%M:%S")
        log.info(f"Следующее обновление через {interval // 60} мин {interval % 60} сек (в {next_run})")
        time.sleep(interval)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m google_ads_mcp.rotator_smile <campaign_id> [customer_id]")
        sys.exit(1)
    _customer_id = sys.argv[2] if len(sys.argv) > 2 else None
    run(sys.argv[1], customer_id=_customer_id)
