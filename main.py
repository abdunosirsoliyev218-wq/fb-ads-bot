import os
import io
import base64
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
FB_TOKEN = os.getenv("FB_TOKEN")
AD_ACCOUNT = os.getenv("AD_ACCOUNT")
PAGE_ID = os.getenv("PAGE_ID")
ALLOWED_USER = int(os.getenv("ALLOWED_USER_ID", "0"))
BASE = "https://graph.facebook.com/v20.0"

(
    S_NAME, S_OBJ, S_BUDGET_TYPE, S_BUDGET, S_AUDIENCE,
    S_CONVLOC, S_LEADFORM, S_PIXEL, S_EVENT, S_URL,
    S_TEXT, S_HEADLINE, S_MEDIA_TYPE, S_IMAGE, S_VIDEO, S_CONFIRM
) = range(16)

def check_user(update: Update) -> bool:
    return ALLOWED_USER == 0 or update.effective_user.id == ALLOWED_USER

async def fb_get(path, params=None):
    p = params or {}
    p["access_token"] = FB_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE}/{path}", params=p) as r:
            return await r.json()

async def fb_post(path, data):
    data["access_token"] = FB_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}/{path}", json=data) as r:
            return await r.json()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    txt = (
        "🚀 *FB Ads Agent Bot*\n\n"
        "Buyruqlar:\n"
        "/newad — Yangi reklama yaratish\n"
        "/stats — Analitika\n"
        "/campaigns — Kampaniyalar\n"
        "/forms — Lead formalar\n"
        "/pause `ID` — To'xtatish\n"
        "/resume `ID` — Yoqish\n"
        "/budget `ID` `$` — Byudjet o'zgartirish\n"
        "/help — Yordam"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await start(update, ctx)

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    keyboard = [
        [InlineKeyboardButton("Bugun", callback_data="stats_today"),
         InlineKeyboardButton("Kecha", callback_data="stats_yesterday")],
        [InlineKeyboardButton("7 kun", callback_data="stats_last_7_days"),
         InlineKeyboardButton("30 kun", callback_data="stats_last_30_days")],
        [InlineKeyboardButton("Bu oy", callback_data="stats_this_month")]
    ]
    await update.message.reply_text("📊 Qaysi davr?", reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset = query.data.replace("stats_", "")
    await query.edit_message_text("⏳ Yuklanmoqda...")
    fields = "spend,impressions,clicks,ctr,cpm,reach,frequency,actions"
    d = await fb_get(f"{AD_ACCOUNT}/insights", {"fields": fields, "date_preset": preset, "level": "account"})
    if "error" in d:
        await query.edit_message_text(f"❌ {d['error']['message']}")
        return
    rows = d.get("data", [])
    if not rows:
        await query.edit_message_text("📭 Ma'lumot yo'q")
        return
    r = rows[0]
    spend = float(r.get("spend", 0))
    impr = int(r.get("impressions", 0))
    clicks = int(r.get("clicks", 0))
    ctr = float(r.get("ctr", 0))
    cpm = float(r.get("cpm", 0))
    reach = int(r.get("reach", 0))
    freq = float(r.get("frequency", 0))
    actions = r.get("actions", [])
    leads = next((int(a["value"]) for a in actions if a["action_type"] in ["lead", "onsite_conversion.lead_grouped"]), 0)
    cpl = f"${spend/leads:.2f}" if leads > 0 else "—"
    lead_rate = f"{leads/clicks*100:.1f}%" if clicks > 0 else "—"
    visit_rate = f"{clicks/impr*100:.2f}%" if impr > 0 else "—"
    names = {"today":"Bugun","yesterday":"Kecha","last_7_days":"7 kun","last_30_days":"30 kun","this_month":"Bu oy"}
    txt = (
        f"📊 *{names.get(preset, preset)}*\n\n"
        f"💰 Sarflangan: *${spend:.2f}*\n"
        f"👁 Ko'rishlar: *{impr:,}*\n"
        f"🖱 Kliklar: *{clicks:,}*\n"
        f"📈 CTR: *{ctr:.2f}%*\n"
        f"💵 CPM: *${cpm:.2f}*\n"
        f"👥 Reach: *{reach:,}*\n"
        f"🔄 Frequency: *{freq:.1f}*\n"
        f"📋 Leads: *{leads}*\n"
        f"💎 CPL: *{cpl}*\n"
        f"🎯 Lead Rate: *{lead_rate}*\n"
        f"🚶 Visit Rate: *{visit_rate}*"
    )
    await query.edit_message_text(txt, parse_mode="Markdown")

async def campaigns(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await update.message.reply_text("⏳ Yuklanmoqda...")
    d = await fb_get(f"{AD_ACCOUNT}/campaigns", {"fields": "id,name,status,objective,daily_budget,lifetime_budget", "limit": "20"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
        return
    camps = d.get("data", [])
    if not camps:
        await update.message.reply_text("📭 Kampaniyalar yo'q")
        return
    keyboard = []
    txt = "📋 *Kampaniyalar:*\n\n"
    for c in camps:
        icon = "🟢" if c["status"] == "ACTIVE" else "🔴"
        budget = f"${int(c['daily_budget'])/100:.0f}/kun" if c.get("daily_budget") else "CBO"
        txt += f"{icon} *{c['name'][:30]}*\n`{c['id']}` | {budget}\n\n"
        label = "⏸ To'xtat" if c["status"] == "ACTIVE" else "▶️ Yoq"
        keyboard.append([InlineKeyboardButton(f"{label}: {c['name'][:20]}", callback_data=f"toggle_{c['id']}_{c['status']}")])
    keyboard.append([InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_camps")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "refresh_camps":
        await query.edit_message_text("⏳ Yangilanmoqda...")
        d = await fb_get(f"{AD_ACCOUNT}/campaigns", {"fields": "id,name,status,daily_budget", "limit": "20"})
        camps = d.get("data", [])
        txt = "📋 *Kampaniyalar:*\n\n"
        keyboard = []
        for c in camps:
            icon = "🟢" if c["status"] == "ACTIVE" else "🔴"
            budget = f"${int(c['daily_budget'])/100:.0f}/kun" if c.get("daily_budget") else "CBO"
            txt += f"{icon} *{c['name'][:30]}*\n`{c['id']}` | {budget}\n\n"
            label = "⏸ To'xtat" if c["status"] == "ACTIVE" else "▶️ Yoq"
            keyboard.append([InlineKeyboardButton(f"{label}: {c['name'][:20]}", callback_data=f"toggle_{c['id']}_{c['status']}")])
        keyboard.append([InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_camps")])
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    parts = query.data.split("_", 2)
    camp_id, current_status = parts[1], parts[2]
    new_status = "PAUSED" if current_status == "ACTIVE" else "ACTIVE"
    d = await fb_post(camp_id, {"status": new_status})
    if "error" in d:
        await query.edit_message_text(f"❌ {d['error']['message']}")
    else:
        icon = "⏸" if new_status == "PAUSED" else "▶️"
        await query.edit_message_text(f"{icon} Holat o'zgartirildi: *{new_status}*", parse_mode="Markdown")

async def pause_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if not ctx.args:
        await update.message.reply_text("Foydalanish: /pause `ID`", parse_mode="Markdown")
        return
    d = await fb_post(ctx.args[0], {"status": "PAUSED"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"⏸ To'xtatildi: `{ctx.args[0]}`", parse_mode="Markdown")

async def resume_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if not ctx.args:
        await update.message.reply_text("Foydalanish: /resume `ID`", parse_mode="Markdown")
        return
    d = await fb_post(ctx.args[0], {"status": "ACTIVE"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"▶️ Yoqildi: `{ctx.args[0]}`", parse_mode="Markdown")

async def budget_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if len(ctx.args) < 2:
        await update.message.reply_text("Foydalanish: /budget `ID` `summa`", parse_mode="Markdown")
        return
    d = await fb_post(ctx.args[0], {"daily_budget": int(float(ctx.args[1]) * 100)})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"💰 Byudjet: *${ctx.args[1]}/kun*", parse_mode="Markdown")

async def forms_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await update.message.reply_text("⏳ Yuklanmoqda...")
    d = await fb_get(f"{PAGE_ID}/leadgen_forms", {"fields": "id,name,status,leads_count"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
        return
    forms = d.get("data", [])
    if not forms:
        await update.message.reply_text("📭 Formalar yo'q")
        return
    txt = "📋 *Lead Formalar:*\n\n"
    keyboard = []
    for f in forms:
        icon = "🟢" if f.get("status") == "ACTIVE" else "🟡"
        txt += f"{icon} *{f['name']}*\n`{f['id']}` | {f.get('leads_count', 0)} lead\n\n"
        keyboard.append([InlineKeyboardButton(f"📋 Dublikat: {f['name'][:25]}", callback_data=f"dupform_{f['id']}_{f['name'][:20]}")])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def dupform_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    form_id, form_name = parts[1], parts[2] if len(parts) > 2 else "Kopiya"
    d = await fb_post(f"{PAGE_ID}/leadgen_forms", {"clone_form_id": form_id, "name": form_name + " — Kopiya"})
    if "error" in d:
        await query.edit_message_text(f"❌ {d['error']['message']}")
    else:
        await query.edit_message_text(f"✅ Dublikat yaratildi!\nID: `{d.get('id')}`", parse_mode="Markdown")

# ===== /newad CONVERSATION =====
async def newad_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    ctx.user_data.clear()
    await update.message.reply_text(
        "🚀 *Yangi reklama*\n\n1️⃣ Kampaniya nomini kiriting:",
        parse_mode="Markdown"
    )
    return S_NAME

async def get_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("📋 Leads", callback_data="obj_OUTCOME_LEADS")],
        [InlineKeyboardButton("🌐 Traffic", callback_data="obj_OUTCOME_TRAFFIC")],
        [InlineKeyboardButton("🛒 Sales", callback_data="obj_OUTCOME_SALES")],
        [InlineKeyboardButton("📣 Awareness", callback_data="obj_OUTCOME_AWARENESS")],
    ]
    await update.message.reply_text("2️⃣ *Maqsad:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_OBJ

async def get_obj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["objective"] = query.data.replace("obj_", "")
    keyboard = [
        [InlineKeyboardButton("CBO — Kampaniya byudjeti", callback_data="bt_cbo")],
        [InlineKeyboardButton("ABO — Ad Set byudjeti", callback_data="bt_abo")],
    ]
    await query.edit_message_text("3️⃣ *Byudjet strategiyasi:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_BUDGET_TYPE

async def get_budget_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["budget_type"] = query.data.replace("bt_", "")
    await query.edit_message_text("4️⃣ *Kunlik byudjet ($):*\n_(masalan: 10)_", parse_mode="Markdown")
    return S_BUDGET

async def get_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["budget"] = float(update.message.text.strip().replace("$", ""))
    except:
        await update.message.reply_text("❌ Son kiriting, masalan: 10")
        return S_BUDGET
    await update.message.reply_text(
        "5️⃣ *Auditoriya:*\n`yosh_dan-yosh_gacha, jins, mamlakat`\n\nMasalan: `18-45, hammasi, UZ`",
        parse_mode="Markdown"
    )
    return S_AUDIENCE

async def get_audience(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    parts = [p.strip() for p in txt.split(",")]
    try:
        ages = parts[0].split("-")
        ctx.user_data["age_min"] = int(ages[0])
        ctx.user_data["age_max"] = int(ages[1])
    except:
        ctx.user_data["age_min"] = 18
        ctx.user_data["age_max"] = 65
    gender_map = {"erkak": 1, "ayol": 2, "hammasi": 0, "all": 0, "male": 1, "female": 2}
    ctx.user_data["gender"] = gender_map.get(parts[1].lower() if len(parts) > 1 else "hammasi", 0)
    ctx.user_data["countries"] = parts[2].upper().split() if len(parts) > 2 else ["UZ"]

    if ctx.user_data.get("objective") == "OUTCOME_LEADS":
        keyboard = [
            [InlineKeyboardButton("📋 Momentli forma (Lead Form)", callback_data="conv_ON_AD")],
            [InlineKeyboardButton("🌐 Sayt (Website)", callback_data="conv_WEBSITE")],
            [InlineKeyboardButton("💬 Messenger", callback_data="conv_MESSENGER")],
            [InlineKeyboardButton("📱 WhatsApp", callback_data="conv_WHATSAPP")],
        ]
        await update.message.reply_text("6️⃣ *Konversiya joyi:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return S_CONVLOC
    else:
        ctx.user_data["conv_loc"] = "WEBSITE"
        await update.message.reply_text("6️⃣ *Landing URL:*\n_(masalan: https://sayt.uz)_", parse_mode="Markdown")
        return S_URL

async def get_convloc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conv_loc = query.data.replace("conv_", "")
    ctx.user_data["conv_loc"] = conv_loc

    if conv_loc == "ON_AD":
        await query.edit_message_text("⏳ Lead formalar yuklanmoqda...")
        d = await fb_get(f"{PAGE_ID}/leadgen_forms", {"fields": "id,name,leads_count", "limit": "10"})
        if "error" in d or not d.get("data"):
            await query.edit_message_text("❌ Formalar topilmadi. /forms bilan tekshiring.")
            return ConversationHandler.END
        forms = d["data"]
        keyboard = [[InlineKeyboardButton(
            f"{i+1}. {f['name'][:30]} ({f.get('leads_count', 0)} lead)",
            callback_data=f"form_{f['id']}"
        )] for i, f in enumerate(forms)]
        await query.edit_message_text("📋 *Lead formani tanlang:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return S_LEADFORM

    elif conv_loc == "WEBSITE":
        await query.edit_message_text("6️⃣ *Pixel tanlash uchun yuklanmoqda...*")
        d = await fb_get(f"{AD_ACCOUNT}/adspixels", {"fields": "id,name"})
        pixels = d.get("data", [])
        if pixels:
            ctx.user_data["pixels_list"] = pixels
            keyboard = [[InlineKeyboardButton(f"{p['name']} ({p['id']})", callback_data=f"pixel_{p['id']}")] for p in pixels]
            keyboard.append([InlineKeyboardButton("⏭ Pixel o'tkazib yuborish", callback_data="pixel_skip")])
            await query.edit_message_text("6️⃣ *Pixel tanlang:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return S_PIXEL
        else:
            await query.edit_message_text("7️⃣ *Landing URL:*\n_(masalan: https://sayt.uz)_", parse_mode="Markdown")
            return S_URL
    else:
        await query.edit_message_text("7️⃣ *Landing URL:*\n_(masalan: https://sayt.uz)_", parse_mode="Markdown")
        return S_URL

async def get_leadform(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["lead_form_id"] = query.data.replace("form_", "")
    await query.edit_message_text("7️⃣ *Reklama matni (Primary text):*", parse_mode="Markdown")
    return S_TEXT

async def get_pixel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "pixel_skip":
        ctx.user_data["pixel_id"] = None
        await query.edit_message_text("7️⃣ *Landing URL:*\n_(masalan: https://sayt.uz)_", parse_mode="Markdown")
        return S_URL
    ctx.user_data["pixel_id"] = query.data.replace("pixel_", "")
    keyboard = [
        [InlineKeyboardButton("Lead", callback_data="event_LEAD")],
        [InlineKeyboardButton("Purchase", callback_data="event_PURCHASE")],
        [InlineKeyboardButton("Submit Application", callback_data="event_SUBMIT_APPLICATION")],
        [InlineKeyboardButton("Complete Registration", callback_data="event_COMPLETE_REGISTRATION")],
        [InlineKeyboardButton("Contact", callback_data="event_CONTACT")],
    ]
    await query.edit_message_text("6️⃣ *Konversiya eventi:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_EVENT

async def get_event(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["conv_event"] = query.data.replace("event_", "")
    await query.edit_message_text("7️⃣ *Landing URL:*\n_(masalan: https://sayt.uz)_", parse_mode="Markdown")
    return S_URL

async def get_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        url = "https://" + url
    ctx.user_data["url"] = url
    await update.message.reply_text("8️⃣ *Reklama matni (Primary text):*", parse_mode="Markdown")
    return S_TEXT

async def get_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["text"] = update.message.text.strip()
    await update.message.reply_text("9️⃣ *Sarlavha (Headline):*", parse_mode="Markdown")
    return S_HEADLINE

async def get_headline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["headline"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("🖼 Rasm yuklash", callback_data="media_image")],
        [InlineKeyboardButton("🎬 Video yuklash", callback_data="media_video")],
        [InlineKeyboardButton("⏭ Media o'tkazib yuborish", callback_data="media_skip")],
    ]
    await update.message.reply_text("🔟 *Media turi:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_MEDIA_TYPE

async def get_media_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    media = query.data.replace("media_", "")
    if media == "skip":
        ctx.user_data["img_hash"] = None
        ctx.user_data["video_id"] = None
        return await show_confirm(query.message, ctx)
    elif media == "image":
        await query.edit_message_text("🖼 *Rasm yuboring:*\n_(JPG yoki PNG)_", parse_mode="Markdown")
        return S_IMAGE
    else:
        await query.edit_message_text("🎬 *Video yuboring:*\n_(MP4, max 50MB)_", parse_mode="Markdown")
        return S_VIDEO

async def get_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Rasm yuklanmoqda...")
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document if update.message.document else None
    file_obj = photo or doc
    if not file_obj:
        await update.message.reply_text("❌ Rasm yuboring")
        return S_IMAGE
    try:
        tg_file = await file_obj.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        d = await fb_post(f"{AD_ACCOUNT}/adimages", {"bytes": b64, "name": "tg_upload"})
        if "error" in d:
            await update.message.reply_text(f"❌ {d['error']['message']}")
            return S_IMAGE
        hash_val = list(d.get("images", {}).values())[0]["hash"]
        ctx.user_data["img_hash"] = hash_val
        ctx.user_data["video_id"] = None
        await update.message.reply_text("✅ Rasm yuklandi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")
        ctx.user_data["img_hash"] = None
        ctx.user_data["video_id"] = None
    return await show_confirm(update.message, ctx)

async def get_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Video yuklanmoqda... (biroz kuting)")
    doc = update.message.document if update.message.document else None
    video = update.message.video if update.message.video else None
    file_obj = doc or video
    if not file_obj:
        await update.message.reply_text("❌ Video yuboring")
        return S_VIDEO
    try:
        tg_file = await file_obj.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        file_size = len(buf.getvalue())
        buf.seek(0)
        init_res = await fb_post(f"{AD_ACCOUNT}/advideos", {
            "upload_phase": "start",
            "file_size": file_size
        })
        if "error" in init_res:
            raise Exception(init_res["error"]["message"])
        upload_session_id = init_res["upload_session_id"]
        video_id = init_res["video_id"]
        chunk_size = 4 * 1024 * 1024
        offset = 0
        while offset < file_size:
            chunk = buf.read(chunk_size)
            form = aiohttp.FormData()
            form.add_field("upload_phase", "transfer")
            form.add_field("upload_session_id", str(upload_session_id))
            form.add_field("start_offset", str(offset))
            form.add_field("access_token", FB_TOKEN)
            form.add_field("video_file_chunk", chunk, filename="chunk", content_type="application/octet-stream")
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{BASE}/{AD_ACCOUNT}/advideos", data=form) as r:
                    td = await r.json()
            if "error" in td:
                raise Exception(td["error"]["message"])
            offset = int(td.get("start_offset", offset + chunk_size))
        fin = await fb_post(f"{AD_ACCOUNT}/advideos", {
            "upload_phase": "finish",
            "upload_session_id": upload_session_id
        })
        if "error" in fin:
            raise Exception(fin["error"]["message"])
        ctx.user_data["video_id"] = video_id
        ctx.user_data["img_hash"] = None
        await update.message.reply_text("✅ Video yuklandi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")
        ctx.user_data["video_id"] = None
        ctx.user_data["img_hash"] = None
    return await show_confirm(update.message, ctx)

async def show_confirm(msg, ctx):
    d = ctx.user_data
    obj_names = {"OUTCOME_LEADS": "Leads", "OUTCOME_TRAFFIC": "Traffic", "OUTCOME_SALES": "Sales", "OUTCOME_AWARENESS": "Awareness"}
    conv_names = {"ON_AD": "Momentli forma", "WEBSITE": "Sayt", "MESSENGER": "Messenger", "WHATSAPP": "WhatsApp"}
    media_info = "🖼 Rasm ✅" if d.get("img_hash") else ("🎬 Video ✅" if d.get("video_id") else "❌ Media yo'q")
    txt = (
        "✅ *Tasdiqlash:*\n\n"
        f"📌 Nom: *{d.get('name')}*\n"
        f"🎯 Maqsad: *{obj_names.get(d.get('objective', ''), '')}*\n"
        f"💰 Byudjet: *${d.get('budget')}/kun* ({d.get('budget_type', 'cbo').upper()})\n"
        f"👥 Yosh: *{d.get('age_min')}-{d.get('age_max')}*\n"
        f"🌍 Mamlakat: *{' '.join(d.get('countries', ['UZ']))}*\n"
        f"📍 Konversiya: *{conv_names.get(d.get('conv_loc', ''), '')}*\n"
        f"🔗 URL: *{d.get('url', '—')}*\n"
        f"📊 Pixel: *{d.get('pixel_id', '—')}*\n"
        f"🎪 Event: *{d.get('conv_event', '—')}*\n"
        f"{media_info}\n\n"
        "Reklamani yoqamizmi?"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Ha, yoq!", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ Bekor", callback_data="confirm_no")]
    ]
    await msg.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_CONFIRM

async def confirm_launch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_no":
        await query.edit_message_text("❌ Bekor qilindi.")
        return ConversationHandler.END

    await query.edit_message_text("🚀 1/4 Kampaniya yaratilmoqda...")
    d = ctx.user_data
    AA = AD_ACCOUNT
    is_cbo = d.get("budget_type") == "cbo"
    budget_cents = int(d["budget"] * 100)

    try:
        camp_body = {"name": d["name"], "objective": d["objective"], "status": "ACTIVE", "special_ad_categories": []}
        if is_cbo:
            camp_body["daily_budget"] = budget_cents
            camp_body["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"
        camp = await fb_post(f"{AA}/campaigns", camp_body)
        if "error" in camp:
            raise Exception("Kampaniya: " + camp["error"]["message"])

        await query.edit_message_text("🚀 ✅ Kampaniya\n2/4 Ad Set yaratilmoqda...")

        targeting = {
            "age_min": d.get("age_min", 18),
            "age_max": d.get("age_max", 65),
            "geo_locations": {"countries": d.get("countries", ["UZ"])}
        }
        if d.get("gender", 0) > 0:
            targeting["genders"] = [d["gender"]]

        opt_map = {"OUTCOME_LEADS": "LEAD_GENERATION", "OUTCOME_TRAFFIC": "LINK_CLICKS", "OUTCOME_SALES": "CONVERSIONS", "OUTCOME_AWARENESS": "REACH"}
        adset_body = {
            "name": d["name"] + " — AdSet",
            "campaign_id": camp["id"],
            "optimization_goal": opt_map.get(d["objective"], "LINK_CLICKS"),
            "billing_event": "IMPRESSIONS",
            "targeting": targeting,
            "status": "ACTIVE",
            "start_time": int(datetime.now().timestamp())
        }
        if not is_cbo:
            adset_body["daily_budget"] = budget_cents
            adset_body["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"

        conv_loc = d.get("conv_loc", "WEBSITE")
        if conv_loc not in ("WEBSITE", "ON_AD"):
            adset_body["destination_type"] = conv_loc

        if d.get("pixel_id") and d.get("conv_event"):
            adset_body["promoted_object"] = {
                "pixel_id": d["pixel_id"],
                "custom_event_type": d["conv_event"]
            }

        adset = await fb_post(f"{AA}/adsets", adset_body)
        if "error" in adset:
            raise Exception("AdSet: " + adset["error"]["message"])

        await query.edit_message_text("🚀 ✅ Kampaniya\n✅ Ad Set\n3/4 Creative yaratilmoqda...")

        if conv_loc == "ON_AD" and d.get("lead_form_id"):
            link_data = {
                "message": d.get("text", ""),
                "name": d.get("headline", d["name"]),
                "link": "https://www.facebook.com/",
                "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": d["lead_form_id"]}}
            }
            if d.get("img_hash"):
                link_data["image_hash"] = d["img_hash"]
            creative_body = {"name": d["name"] + " — Creative", "object_story_spec": {"page_id": PAGE_ID, "link_data": link_data}}

        elif d.get("video_id"):
            creative_body = {
                "name": d["name"] + " — Creative",
                "object_story_spec": {
                    "page_id": PAGE_ID,
                    "video_data": {
                        "video_id": d["video_id"],
                        "message": d.get("text", ""),
                        "title": d.get("headline", d["name"]),
                        "call_to_action": {"type": "LEARN_MORE", "value": {"link": d.get("url", "https://facebook.com")}}
                    }
                }
            }
        else:
            link_data = {
                "message": d.get("text", ""),
                "name": d.get("headline", d["name"]),
                "link": d.get("url", "https://facebook.com"),
                "call_to_action": {"type": "LEARN_MORE", "value": {"link": d.get("url", "https://facebook.com")}}
            }
            if d.get("img_hash"):
                link_data["image_hash"] = d["img_hash"]
            creative_body = {"name": d["name"] + " — Creative", "object_story_spec": {"page_id": PAGE_ID, "link_data": link_data}}

        creative_body["access_token"] = FB_TOKEN
        creative = await fb_post(f"{AA}/adcreatives", creative_body)
        if "error" in creative:
            raise Exception("Creative: " + creative["error"]["message"])

        await query.edit_message_text("🚀 ✅ Kampaniya\n✅ Ad Set\n✅ Creative\n4/4 Ad yoqilmoqda...")

        ad = await fb_post(f"{AA}/ads", {"name": d["name"] + " — Ad", "adset_id": adset["id"], "creative": {"creative_id": creative["id"]}, "status": "ACTIVE"})
        if "error" in ad:
            raise Exception("Ad: " + ad["error"]["message"])

        txt = (
            "🎉 *Reklama yoqildi!*\n\n"
            f"📌 *{d['name']}*\n"
            f"🆔 Campaign: `{camp['id']}`\n"
            f"🆔 AdSet: `{adset['id']}`\n"
            f"🆔 Ad: `{ad['id']}`\n\n"
            f"💰 ${d['budget']}/kun\n"
            "📊 /stats bilan kuzating"
        )
        await query.edit_message_text(txt, parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ Xato: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TG_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("newad", newad_start)],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            S_OBJ: [CallbackQueryHandler(get_obj, pattern="^obj_")],
            S_BUDGET_TYPE: [CallbackQueryHandler(get_budget_type, pattern="^bt_")],
            S_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            S_AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_audience)],
            S_CONVLOC: [CallbackQueryHandler(get_convloc, pattern="^conv_")],
            S_LEADFORM: [CallbackQueryHandler(get_leadform, pattern="^form_")],
            S_PIXEL: [CallbackQueryHandler(get_pixel, pattern="^pixel_")],
            S_EVENT: [CallbackQueryHandler(get_event, pattern="^event_")],
            S_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url)],
            S_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_text)],
            S_HEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_headline)],
            S_MEDIA_TYPE: [CallbackQueryHandler(get_media_type, pattern="^media_")],
            S_IMAGE: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, get_image)],
            S_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, get_video)],
            S_CONFIRM: [CallbackQueryHandler(confirm_launch, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("campaigns", campaigns))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("budget", budget_cmd))
    app.add_handler(CommandHandler("forms", forms_cmd))
    app.add_handler(CallbackQueryHandler(stats_callback, pattern="^stats_"))
    app.add_handler(CallbackQueryHandler(toggle_callback, pattern="^(toggle_|refresh_)"))
    app.add_handler(CallbackQueryHandler(dupform_callback, pattern="^dupform_"))
    print("✅ FB Ads Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
