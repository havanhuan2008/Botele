import asyncio
import threading
import re
import random
from typing import Optional, Dict, List, Tuple

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from db import add_message, get_setting, add_convo, get_recent_convo

# ========= SETTINGS =========
def _auto_reply_enabled() -> bool:
    return (get_setting("auto_reply_enabled") or "0") == "1"

def _persona() -> str:
    # sweet | blunt | sassy
    p = (get_setting("persona") or "sweet").strip().lower()
    return p if p in ("sweet", "blunt", "sassy") else "sweet"

def _bot_name() -> str:
    return (get_setting("bot_name") or "Bot").strip() or "Bot"

# ========= SAFETY GUARD: không chửi rủa/công kích =========
_BAD_WORDS = [
    "đồ ngu", "ngu vãi", "óc chó", "cút", "địt", "đmm", "dm", "đm", "fuck", "cặc", "lồn"
]
def _should_deescalate(user_text: str) -> bool:
    t = (user_text or "").lower()
    return any(w in t for w in _BAD_WORDS)

# ========= PERSONA STYLES =========
_SWEET_OPEN = ["Dạ nè 🥰", "Có em đây ✨", "Mình ơi 🫶", "Em nghe nè 💛"]
_SWEET_CLOSE = ["Mình kể thêm nha?", "Em ở đây với mình.", "Mình muốn em giúp gì tiếp nè?"]

_BLUNT_OPEN = ["Ok.", "Nghe đây.", "Nói thẳng:", "Mình chốt thế này:"]
_BLUNT_CLOSE = ["Trả lời 2 ý là đủ.", "Đưa thêm dữ kiện.", "Muốn nhanh hay chi tiết?"]

_SASSY_OPEN = ["Ờm…", "Rồi, nghe nè 😏", "Từ từ đã 🙃", "Ok ok 😼"]
_SASSY_CLOSE = ["Nói rõ hơn coi.", "Đừng mơ hồ.", "Đưa log/chi tiết lên.", "Chốt lại mục tiêu?"]

def _wrap(text: str) -> str:
    p = _persona()
    if p == "blunt":
        return f"{random.choice(_BLUNT_OPEN)} {text} {random.choice(_BLUNT_CLOSE)}"
    if p == "sassy":
        return f"{random.choice(_SASSY_OPEN)} {text} {random.choice(_SASSY_CLOSE)}"
    return f"{random.choice(_SWEET_OPEN)} {text} {random.choice(_SWEET_CLOSE)}"

# ========= “DEEP THINK” OFFLINE ENGINE =========
FAQ: List[Tuple[str, str]] = [
    (r"\bhello\b|\bhi\b|\bchào\b|\bxin chào\b", "Chào bạn. Bạn cần mình làm gì?"),
    (r"\bcảm ơn\b|\bthanks\b|\bthank you\b", "Ok. Có gì cứ nói tiếp."),
    (r"\bbuồn\b|\bmệt\b|\bstress\b|\bchán\b|\blo\b|\bcăng\b", "Nghe có vẻ bạn đang mệt. Nói 1 câu: chuyện gì xảy ra + bạn muốn kết quả gì?"),
    (r"\blỗi\b|\berror\b|\bbug\b|\bfix\b|\bsửa\b", "Bạn gửi 3–5 dòng cuối log + bạn đang làm tới bước nào, mình chỉ đúng chỗ sửa.")
]

def _intent(user_text: str) -> Dict[str, bool]:
    t = (user_text or "").strip().lower()
    return {
        "question": ("?" in t) or any(k in t for k in ["là gì", "sao", "tại sao", "cách", "làm thế nào", "hướng dẫn"]),
        "help": any(k in t for k in ["giúp", "hỗ trợ", "fix", "sửa", "lỗi", "cài", "chạy", "setup"]),
        "emotion": any(k in t for k in ["buồn", "mệt", "stress", "chán", "lo", "sợ", "căng"]),
        "greeting": any(k in t for k in ["hello", "hi", "chào", "xin chào"]),
        "short": len(t) <= 3
    }

def _extract_topic(user_text: str) -> str:
    t = (user_text or "").strip()
    if not t:
        return ""
    # lấy 1 “chủ đề” đơn giản: dòng đầu, tối đa 60 ký tự
    t = t.splitlines()[0].strip()
    return (t[:60] + "…") if len(t) > 60 else t

def _summarize_context(ctx: List[Dict[str, str]]) -> str:
    # lấy 1-2 ý gần nhất user nói
    last_user = ""
    prev_user = ""
    for item in reversed(ctx):
        if item["role"] == "user":
            if not last_user:
                last_user = item["text"]
            elif not prev_user:
                prev_user = item["text"]
                break
    pieces = []
    if prev_user:
        pieces.append(_extract_topic(prev_user))
    if last_user:
        pieces.append(_extract_topic(last_user))
    return " | ".join([p for p in pieces if p])

def _deep_reply(chat_id: str, user_text: str) -> str:
    text = (user_text or "").strip()
    low = text.lower()

    # nếu user chửi → hạ nhiệt (không chửi lại)
    if _should_deescalate(text):
        return _wrap("Mình không chửi lại đâu. Nếu bạn muốn mình giúp, nói rõ vấn đề + mục tiêu, mình xử lý cho nhanh.")

    # FAQ match
    for pat, ans in FAQ:
        if re.search(pat, low):
            return _wrap(ans)

    intent = _intent(text)
    ctx = get_recent_convo(chat_id, limit=14)
    ctx_summary = _summarize_context(ctx)

    if intent["short"]:
        # tin nhắn quá ngắn → hỏi lại
        return _wrap("Bạn nói rõ hơn 1 chút: bạn đang muốn hỏi gì, hay muốn mình làm gì?")

    if intent["emotion"]:
        # cấu trúc “3 câu” để dẫn dắt
        return _wrap("Mình hỏi 3 cái thôi: (1) chuyện gì xảy ra? (2) bạn đang cần gì ngay bây giờ? (3) có ràng buộc nào không?)")

    if intent["help"]:
        # hướng dẫn dạng checklist
        return _wrap(
            "Ok, mình xử lý theo checklist: "
            "1) Bạn đang dùng môi trường nào (Android/Pydroid/VPS)? "
            "2) Bạn làm tới bước nào? "
            "3) Dán 3–5 dòng cuối log. "
            + (f"Ngữ cảnh gần đây mình thấy: {ctx_summary}." if ctx_summary else "")
        )

    if intent["question"]:
        topic = _extract_topic(text.replace("?", ""))
        # trả lời kiểu “tư duy”: xác nhận + hỏi rõ + đưa lựa chọn
        return _wrap(
            f"Mình hiểu bạn đang hỏi về: “{topic}”. "
            "Bạn muốn câu trả lời theo kiểu A) nhanh gọn 3 ý, hay B) chi tiết từng bước? "
            + (f"Ngữ cảnh: {ctx_summary}." if ctx_summary else "")
        )

    # default: phản hồi thông minh dạng “phản chiếu + gợi mở”
    topic = _extract_topic(text)
    return _wrap(
        f"Mình nghe bạn nói: “{topic}”. "
        "Bạn muốn mình góp ý hướng giải quyết, hay bạn chỉ cần mình lắng nghe?"
        + (f" (Ngữ cảnh: {ctx_summary})" if ctx_summary else "")
    )

# ========= BOT MANAGER =========
class BotManager:
    def __init__(self):
        self._token: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._app: Optional[Application] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def configure(self, token: str):
        self._token = (token or "").strip()

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        # bỏ qua tin từ bot khác
        if update.effective_user and getattr(update.effective_user, "is_bot", False):
            return

        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        username = update.effective_user.username if update.effective_user else ""
        text = update.message.text or update.message.caption or ""

        add_message(chat_id, username or "", text or "")
        add_convo(chat_id, "user", (text or "").strip() or "[non-text]")

        # auto reply toggle
        if not _auto_reply_enabled():
            return

        # bỏ qua commands (bạn có thể bỏ dòng này nếu muốn bot trả lời cả /start)
        if (text or "").strip().startswith("/"):
            return

        reply = _deep_reply(chat_id, text or "")
        try:
            await context.bot.send_message(chat_id=chat_id, text=reply)
            add_convo(chat_id, "bot", reply)
        except Exception as e:
            print("Auto-reply send error:", e)

    async def _run_async(self):
        if not self._token:
            raise RuntimeError("Bot token chưa được cấu hình.")

        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.ALL, self._on_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        while not self._stop_event.is_set():
            await asyncio.sleep(0.4)

        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    def start(self):
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._run_async()), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    async def send_message_async(self, chat_id: str, text: str):
        if not self._token:
            raise RuntimeError("Chưa có token.")
        app = Application.builder().token(self._token).build()
        await app.bot.send_message(chat_id=chat_id, text=text)

    def send_message(self, chat_id: str, text: str):
        asyncio.run(self.send_message_async(chat_id, text))