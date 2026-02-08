from datetime import timezone

from flask import Flask, redirect, render_template, request, url_for, flash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from db import (
    init_db, set_setting, get_setting,
    list_messages, create_schedule, list_schedules,
    set_schedule_enabled, delete_schedule
)
from bot_manager import BotManager

app = Flask(__name__)
app.secret_key = "change-this-secret"

init_db()
bot = BotManager()

# Android hay lỗi tz -> dùng UTC ổn định
scheduler = BackgroundScheduler(timezone=timezone.utc)
scheduler.start()

def ensure_bot_loaded():
    token = get_setting("bot_token")
    if token:
        bot.configure(token)

def rebuild_jobs():
    scheduler.remove_all_jobs()
    ensure_bot_loaded()

    for s in list_schedules():
        if int(s["enabled"]) != 1:
            continue

        cron = (s["cron"] or "").strip()
        parts = cron.split()
        if len(parts) != 5:
            continue

        minute, hour, day, month, dow = parts

        def job(chat_id=s["chat_id"], text=s["text"]):
            try:
                ensure_bot_loaded()
                bot.send_message(chat_id, text)
            except Exception as e:
                print("Schedule send error:", e)

        scheduler.add_job(
            job,
            trigger=CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow),
            id=f"schedule_{s['id']}",
            replace_existing=True,
        )

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/setup", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        token = (request.form.get("token", "") or "").strip()
        persona = (request.form.get("persona", "") or "sweet").strip().lower()
        bot_name = (request.form.get("bot_name", "") or "Bot").strip()

        if token:
            set_setting("bot_token", token)
            bot.configure(token)

        if persona not in ["sweet", "blunt", "sassy"]:
            persona = "sweet"
        set_setting("persona", persona)

        set_setting("bot_name", bot_name or "Bot")

        flash("Đã lưu cấu hình.", "ok")
        return redirect(url_for("dashboard"))

    token = get_setting("bot_token") or ""
    persona = (get_setting("persona") or "sweet").strip().lower()
    bot_name = get_setting("bot_name") or "Bot"
    return render_template("setup.html", token=token, persona=persona, bot_name=bot_name, bot_running=bot.running)

@app.route("/bot/start", methods=["POST"])
def bot_start():
    ensure_bot_loaded()
    if not get_setting("bot_token"):
        flash("Chưa có token. Hãy vào Setup trước.", "error")
        return redirect(url_for("setup"))
    bot.start()
    flash("Bot đã chạy (polling).", "ok")
    return redirect(url_for("dashboard"))

@app.route("/bot/stop", methods=["POST"])
def bot_stop():
    bot.stop()
    flash("Đã yêu cầu dừng bot.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/autoreply/toggle", methods=["POST"])
def autoreply_toggle():
    enabled = request.form.get("enabled") == "1"
    set_setting("auto_reply_enabled", "1" if enabled else "0")
    flash("Đã cập nhật Auto Reply.", "ok")
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    ensure_bot_loaded()
    token = get_setting("bot_token") or ""
    schedules = list_schedules()
    auto_reply_enabled = (get_setting("auto_reply_enabled") or "0") == "1"
    persona = (get_setting("persona") or "sweet").strip().lower()
    bot_name = get_setting("bot_name") or "Bot"

    return render_template(
        "dashboard.html",
        has_token=bool(token),
        bot_running=bot.running,
        schedules=schedules,
        auto_reply_enabled=auto_reply_enabled,
        persona=persona,
        bot_name=bot_name
    )

@app.route("/send", methods=["GET", "POST"])
def send():
    ensure_bot_loaded()
    if request.method == "POST":
        chat_id = (request.form.get("chat_id", "") or "").strip()
        text = (request.form.get("text", "") or "").strip()
        if not chat_id or not text:
            flash("Thiếu chat_id hoặc nội dung.", "error")
            return redirect(url_for("send"))
        try:
            bot.send_message(chat_id, text)
            flash("Đã gửi.", "ok")
        except Exception as e:
            flash(f"Lỗi gửi: {e}", "error")
        return redirect(url_for("send"))

    return render_template("send.html", bot_running=bot.running)

@app.route("/messages")
def messages():
    rows = list_messages(200)
    return render_template("messages.html", rows=rows)

@app.route("/schedules", methods=["GET", "POST"])
def schedules():
    ensure_bot_loaded()
    if request.method == "POST":
        name = (request.form.get("name", "") or "").strip() or "Auto message"
        chat_id = (request.form.get("chat_id", "") or "").strip()
        text = (request.form.get("text", "") or "").strip()
        cron = (request.form.get("cron", "") or "").strip()

        if not chat_id or not text or not cron:
            flash("Thiếu chat_id / text / cron.", "error")
            return redirect(url_for("schedules"))

        create_schedule(name, chat_id, text, cron)
        rebuild_jobs()
        flash("Đã tạo lịch và nạp lại jobs.", "ok")
        return redirect(url_for("schedules"))

    rows = list_schedules()
    return render_template("schedules.html", rows=rows)

@app.route("/schedules/<int:sid>/toggle", methods=["POST"])
def schedules_toggle(sid: int):
    enabled = request.form.get("enabled") == "1"
    set_schedule_enabled(sid, enabled)
    rebuild_jobs()
    flash("Đã cập nhật bật/tắt.", "ok")
    return redirect(url_for("schedules"))

@app.route("/schedules/<int:sid>/delete", methods=["POST"])
def schedules_delete(sid: int):
    delete_schedule(sid)
    rebuild_jobs()
    flash("Đã xoá lịch.", "ok")
    return redirect(url_for("schedules"))

if __name__ == "__main__":
    ensure_bot_loaded()
    rebuild_jobs()
    app.run(host="0.0.0.0", port=8000, debug=False)