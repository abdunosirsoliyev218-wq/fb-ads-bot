import os
import json
import asyncio
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
AD_ACCOUNT = os.getenv("AD_ACCOUNT")  # act_XXXXXXXXX
PAGE_ID = os.getenv("PAGE_ID")
ALLOWED_USER = int(os.getenv("ALLOWED_USER_ID", "0"))
BASE = "https://graph.facebook.com/v20.0"

# Conversation states
(
    S_NAME, S_OBJ, S_BUDGET_TYPE, S_BUDGET, S_AUDIENCE,
    S_CONVLOC, S_LEADFORM, S_TEXT, S_HEADLINE, S_IMAGE, S_CONFIRM
) = range(11)

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

async def fb_post_form(path, form_data):
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}/{path}", data=form_data) as r:
            return await r.json()

# ===== /start =====
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    txt = (
        "🚀 *FB Ads Agent Bot*\n\n"
        "Buyruqlar:\n"
        "/newad — Yangi reklama yaratish\n"
        "/stats — Analitika (bugun/7kun/30kun)\n"
        "/campaigns — Kampaniyalar ro'yxati\n"
        "/forms — Lead formalar\n"
        "/pause `ID` — Kampaniyani to'xtatish\n"
        "/resume `ID` — Kampaniyani yoqish\n"
        "/budget `ID` `summa` — Byudjet o'zgartirish\n"
        "/help — Yordam"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

# ===== /stats =====
async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    keyboard = [
        [InlineKeyboardButton("Bugun", callback_data="stats_today"),
         InlineKeyboardButton("Kecha", callback_data="stats_yesterday")],
        [InlineKeyboardButton("7 kun", callback_data="stats_last_7_days"),
         InlineKeyboardButton("30 kun", callback_data="stats_last_30_days")],
        [InlineKeyboardButton("Bu oy", callback_data="stats_this_month")]
    ]
    await update.message.reply_text(
        "📊 Qaysi davr uchun analitika?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset = query.data.replace("stats_", "")
    await query.edit_message_text("⏳ Yuklanmoqda...")
    fields = "spend,impressions,clicks,ctr,cpm,reach,frequency,actions"
    d = await fb_get(f"{AD_ACCOUNT}/insights", {
        "fields": fields,
        "date_preset": preset,
        "level": "account"
    })
    if "error" in d:
        await query.edit_message_text(f"❌ Xato: {d['error']['message']}")
        return
    rows = d.get("data", [])
    if not rows:
        await query.edit_message_text("📭 Bu davrda ma'lumot yo'q")
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
    leads = next((int(a["value"]) for a in actions if a["action_type"] in ["lead","onsite_conversion.lead_grouped"]), 0)
    cpl = f"${spend/leads:.2f}" if leads > 0 else "—"
    lead_rate = f"{leads/clicks*100:.1f}%" if clicks > 0 else "—"
    visit_rate = f"{clicks/impr*100:.2f}%" if impr > 0 else "—"
    preset_names = {
        "today":"Bugun","yesterday":"Kecha",
        "last_7_days":"Oxirgi 7 kun","last_30_days":"Oxirgi 30 kun","this_month":"Bu oy"
    }
    txt = (
        f"📊 *{preset_names.get(preset, preset)}*\n\n"
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

# ===== /campaigns =====
async def campaigns(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await update.message.reply_text("⏳ Kampaniyalar yuklanmoqda...")
    d = await fb_get(f"{AD_ACCOUNT}/campaigns", {
        "fields": "id,name,status,objective,daily_budget,lifetime_budget",
        "limit": "20"
    })
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
        status_icon = "🟢" if c["status"] == "ACTIVE" else "🔴"
        budget = ""
        if c.get("daily_budget"):
            budget = f"${int(c['daily_budget'])/100:.0f}/kun"
        elif c.get("lifetime_budget"):
            budget = f"${int(c['lifetime_budget'])/100:.0f} total"
        txt += f"{status_icon} *{c['name'][:35]}*\n`{c['id']}` | {budget}\n\n"
        action = "pause" if c["status"] == "ACTIVE" else "resume"
        label = "⏸ To'xtat" if c["status"] == "ACTIVE" else "▶️ Yoq"
        keyboard.append([InlineKeyboardButton(
            f"{label}: {c['name'][:20]}", callback_data=f"toggle_{c['id']}_{c['status']}"
        )])
    keyboard.append([InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_camps")])
    await update.message.reply_text(
        txt, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def toggle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "refresh_camps":
        await campaigns(query, ctx)
        return
    _, camp_id, current_status = query.data.split("_", 2)
    new_status = "PAUSED" if current_status == "ACTIVE" else "ACTIVE"
    d = await fb_post(camp_id, {"status": new_status})
    if "error" in d:
        await query.edit_message_text(f"❌ {d['error']['message']}")
    else:
        icon = "⏸" if new_status == "PAUSED" else "▶️"
        await query.edit_message_text(f"{icon} Kampaniya holati o'zgartirildi: *{new_status}*", parse_mode="Markdown")

# ===== /pause & /resume =====
async def pause_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if not ctx.args:
        await update.message.reply_text("Foydalanish: /pause `CAMPAIGN_ID`", parse_mode="Markdown")
        return
    cid = ctx.args[0]
    d = await fb_post(cid, {"status": "PAUSED"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"⏸ Kampaniya to'xtatildi: `{cid}`", parse_mode="Markdown")

async def resume_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if not ctx.args:
        await update.message.reply_text("Foydalanish: /resume `CAMPAIGN_ID`", parse_mode="Markdown")
        return
    cid = ctx.args[0]
    d = await fb_post(cid, {"status": "ACTIVE"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"▶️ Kampaniya yoqildi: `{cid}`", parse_mode="Markdown")

# ===== /budget =====
async def budget_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if len(ctx.args) < 2:
        await update.message.reply_text("Foydalanish: /budget `CAMPAIGN_ID` `summa`\nMasalan: /budget 123456 15", parse_mode="Markdown")
        return
    cid, amount = ctx.args[0], ctx.args[1]
    budget_cents = int(float(amount) * 100)
    d = await fb_post(cid, {"daily_budget": budget_cents})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
    else:
        await update.message.reply_text(f"💰 Byudjet o'zgartirildi: *${amount}/kun*", parse_mode="Markdown")

# ===== /forms =====
async def forms_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await update.message.reply_text("⏳ Formalar yuklanmoqda...")
    d = await fb_get(f"{PAGE_ID}/leadgen_forms", {"fields": "id,name,status,leads_count"})
    if "error" in d:
        await update.message.reply_text(f"❌ {d['error']['message']}")
        return
    forms = d.get("data", [])
    if not forms:
        await update.message.reply_text("📭 Lead formalar yo'q")
        return
    txt = "📋 *Lead Formalar:*\n\n"
    keyboard = []
    for f in forms:
        icon = "🟢" if f.get("status") == "ACTIVE" else "🟡"
        txt += f"{icon} *{f['name']}*\n`{f['id']}` | {f.get('leads_count',0)} lead\n\n"
        keyboard.append([InlineKeyboardButton(
            f"📋 Dublikat: {f['name'][:25]}", callback_data=f"dupform_{f['id']}_{f['name'][:20]}"
        )])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def dupform_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    form_id = parts[1]
    form_name = parts[2] if len(parts) > 2 else "Kopiya"
    d = await fb_post(f"{PAGE_ID}/leadgen_forms", {
        "clone_form_id": form_id,
        "name": form_name + " — Kopiya"
    })
    if "error" in d:
        await query.edit_message_text(f"❌ {d['error']['message']}")
    else:
        await query.edit_message_text(f"✅ Forma dublikat qilindi!\nYangi ID: `{d.get('id')}`", parse_mode="Markdown")

# ===== /newad conversation =====
async def newad_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    ctx.user_data.clear()
    await update.message.reply_text(
        "🚀 *Yangi reklama yaratish*\n\n"
        "1️⃣ Kampaniya nomini kiriting:\n_(masalan: Xavi CPA Iyun 2026)_",
        parse_mode="Markdown"
    )
    return S_NAME

async def get_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("📋 Leads (Ariza)", callback_data="obj_OUTCOME_LEADS")],
        [InlineKeyboardButton("🌐 Traffic", callback_data="obj_OUTCOME_TRAFFIC")],
        [InlineKeyboardButton("🛒 Sales", callback_data="obj_OUTCOME_SALES")],
        [InlineKeyboardButton("📣 Awareness", callback_data="obj_OUTCOME_AWARENESS")],
    ]
    await update.message.reply_text(
        "2️⃣ *Kampaniya maqsadi:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return S_OBJ

async def get_obj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["objective"] = query.data.replace("obj_", "")
    keyboard = [
        [InlineKeyboardButton("CBO — Kampaniya byudjeti", callback_data="budget_cbo")],
        [InlineKeyboardButton("ABO — Ad Set byudjeti", callback_data="budget_abo")],
    ]
    await query.edit_message_text(
        "3️⃣ *Byudjet strategiyasi:*\n\nCBO — Meta o'zi taqsimlaydi\nABO — Har ad set uchun alohida",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return S_BUDGET_TYPE

async def get_budget_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["budget_type"] = query.data.replace("budget_", "")
    await query.edit_message_text(
        "4️⃣ *Kunlik byudjet ($):*\n\n_(masalan: 10)_",
        parse_mode="Markdown"
    )
    return S_BUDGET

async def get_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["budget"] = float(update.message.text.strip().replace("$",""))
    except:
        await update.message.reply_text("❌ Son kiriting, masalan: 10")
        return S_BUDGET
    await update.message.reply_text(
        "5️⃣ *Auditoriya:*\n\n"
        "Formatda yozing:\n`yosh_dan-yosh_gacha, jins, mamlakat`\n\n"
        "Masalan: `18-45, hammasi, UZ`\n"
        "Yoki: `25-55, erkak, UZ KZ`\n\n"
        "_(jins: hammasi / erkak / ayol)_",
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
    countries = parts[2].upper().split() if len(parts) > 2 else ["UZ"]
    ctx.user_data["countries"] = countries

    if ctx.user_data.get("objective") == "OUTCOME_LEADS":
        keyboard = [
            [InlineKeyboardButton("📋 Momentli forma (Lead Form)", callback_data="conv_ON_AD")],
            [InlineKeyboardButton("🌐 Sayt", callback_data="conv_WEBSITE")],
            [InlineKeyboardButton("💬 Messenger", callback_data="conv_MESSENGER")],
            [InlineKeyboardButton("📱 WhatsApp", callback_data="conv_WHATSAPP")],
        ]
        await update.message.reply_text(
            "6️⃣ *Konversiya joyi:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return S_CONVLOC
    else:
        ctx.user_data["conv_loc"] = "WEBSITE"
        await update.message.reply_text("7️⃣ *Reklama matni (Primary text):*", parse_mode="Markdown")
        return S_TEXT

async def get_convloc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["conv_loc"] = query.data.replace("conv_", "")
    if ctx.user_data["conv_loc"] == "ON_AD":
        await query.edit_message_text("⏳ Lead formalar yuklanmoqda...")
        d = await fb_get(f"{PAGE_ID}/leadgen_forms", {"fields": "id,name,leads_count", "limit": "10"})
        if "error" in d or not d.get("data"):
            await query.edit_message_text("❌ Formalar topilmadi. /forms buyrug'i bilan tekshiring.")
            return ConversationHandler.END
        forms = d["data"]
        ctx.user_data["forms_list"] = forms
        keyboard = [[InlineKeyboardButton(
            f"{i+1}. {f['name'][:30]} ({f.get('leads_count',0)} lead)",
            callback_data=f"form_{f['id']}"
        )] for i, f in enumerate(forms)]
        await query.edit_message_text(
            "📋 *Lead formani tanlang:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return S_LEADFORM
    else:
        await query.edit_message_text("7️⃣ *Reklama matni (Primary text):*", parse_mode="Markdown")
        return S_TEXT

async def get_leadform(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["lead_form_id"] = query.data.replace("form_", "")
    await query.edit_message_text("7️⃣ *Reklama matni (Primary text):*", parse_mode="Markdown")
    return S_TEXT

async def get_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["text"] = update.message.text.strip()
    await update.message.reply_text("8️⃣ *Sarlavha (Headline):*\n_(masalan: Bepul konsultatsiya)_", parse_mode="Markdown")
    return S_HEADLINE

async def get_headline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["headline"] = update.message.text.strip()
    await update.message.reply_text(
        "9️⃣ *Rasm yuboring:*\n\n_(Rasm yubormasangiz, matnli reklama bo'ladi — /skip)_",
        parse_mode="Markdown"
    )
    return S_IMAGE

async def skip_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["img_hash"] = None
    return await show_confirm(update, ctx)

async def get_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Rasm yuklanmoqda...")
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document if update.message.document else None
    file_obj = photo or doc
    if not file_obj:
        await update.message.reply_text("❌ Rasm yuboring yoki /skip")
        return S_IMAGE
    try:
        tg_file = await file_obj.get_file()
        import io
        import base64
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        d = await fb_post(f"{AD_ACCOUNT}/adimages", {"bytes": b64, "name": "tg_upload"})
        if "error" in d:
            await update.message.reply_text(f"❌ Rasm xatosi: {d['error']['message']}")
            return S_IMAGE
        hash_val = list(d.get("images", {}).values())[0]["hash"]
        ctx.user_data["img_hash"] = hash_val
        await update.message.reply_text("✅ Rasm yuklandi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")
        ctx.user_data["img_hash"] = None
    return await show_confirm(update, ctx)

async def show_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.user_data
    obj_names = {
        "OUTCOME_LEADS":"Leads","OUTCOME_TRAFFIC":"Traffic",
        "OUTCOME_SALES":"Sales","OUTCOME_AWARENESS":"Awareness"
    }
    conv_names = {
        "ON_AD":"Momentli forma","WEBSITE":"Sayt",
        "MESSENGER":"Messenger","WHATSAPP":"WhatsApp"
    }
    txt = (
        "✅ *Tasdiqlash:*\n\n"
        f"📌 Nom: *{d.get('name')}*\n"
        f"🎯 Maqsad: *{obj_names.get(d.get('objective',''), d.get('objective',''))}*\n"
        f"💰 Byudjet: *${d.get('budget')}/kun* ({d.get('budget_type','cbo').upper()})\n"
        f"👥 Yosh: *{d.get('age_min')}-{d.get('age_max')}*\n"
        f"🌍 Mamlakat: *{' '.join(d.get('countries', ['UZ']))}*\n"
        f"📍 Konversiya: *{conv_names.get(d.get('conv_loc',''), d.get('conv_loc',''))}*\n"
        f"🖼 Rasm: *{'✅' if d.get('img_hash') else '❌ Yo\'q'}*\n\n"
        "Reklamani yoqamizmi?"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Ha, yoq!", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ Bekor", callback_data="confirm_no")]
    ]
    msg = update.message or update.callback_query.message
    await msg.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return S_CONFIRM

async def confirm_launch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_no":
        await query.edit_message_text("❌ Bekor qilindi. /newad bilan qayta boshlang.")
        return ConversationHandler.END

    await query.edit_message_text("🚀 Reklama yaratilmoqda...\n\n1/4 Kampaniya...")
    d = ctx.user_data
    T = FB_TOKEN
    AA = AD_ACCOUNT

    try:
        is_cbo = d.get("budget_type") == "cbo"
        budget_cents = int(d["budget"] * 100)
        camp_body = {
            "name": d["name"],
            "objective": d["objective"],
            "status": "ACTIVE",
            "special_ad_categories": []
        }
        if is_cbo:
            camp_body["daily_budget"] = budget_cents
            camp_body["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"

        camp = await fb_post(f"{AA}/campaigns", camp_body)
        if "error" in camp:
            raise Exception("Kampaniya: " + camp["error"]["message"])

        await query.edit_message_text("🚀 Reklama yaratilmoqda...\n\n✅ Kampaniya\n2/4 Ad Set...")

        gender = d.get("gender", 0)
        targeting = {
            "age_min": d.get("age_min", 18),
            "age_max": d.get("age_max", 65),
            "geo_locations": {"countries": d.get("countries", ["UZ"])}
        }
        if gender > 0:
            targeting["genders"] = [gender]

        opt_map = {
            "OUTCOME_LEADS": "LEAD_GENERATION",
            "OUTCOME_TRAFFIC": "LINK_CLICKS",
            "OUTCOME_SALES": "CONVERSIONS",
            "OUTCOME_AWARENESS": "REACH"
        }
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

        adset = await fb_post(f"{AA}/adsets", adset_body)
        if "error" in adset:
            raise Exception("AdSet: " + adset["error"]["message"])

        await query.edit_message_text("🚀 Reklama yaratilmoqda...\n\n✅ Kampaniya\n✅ Ad Set\n3/4 Creative...")

        link_data = {
            "message": d.get("text", ""),
            "name": d.get("headline", d["name"]),
            "call_to_action": {"type": "LEARN_MORE", "value": {}}
        }
        if conv_loc == "ON_AD" and d.get("lead_form_id"):
            link_data["call_to_action"] = {
                "type": "SIGN_UP",
                "value": {"lead_gen_form_id": d["lead_form_id"]}
            }
            link_data["link"] = "https://www.facebook.com/"
        else:
            link_data["link"] = "https://www.facebook.com/"

        if d.get("img_hash"):
            link_data["image_hash"] = d["img_hash"]

        creative_body = {
            "name": d["name"] + " — Creative",
            "object_story_spec": {
                "page_id": PAGE_ID,
                "link_data": link_data
            }
        }
        creative = await fb_post(f"{AA}/adcreatives", creative_body)
        if "error" in creative:
            raise Exception("Creative: " + creative["error"]["message"])

        await query.edit_message_text("🚀 Reklama yaratilmoqda...\n\n✅ Kampaniya\n✅ Ad Set\n✅ Creative\n4/4 Ad...")

        ad = await fb_post(f"{AA}/ads", {
            "name": d["name"] + " — Ad",
            "adset_id": adset["id"],
            "creative": {"creative_id": creative["id"]},
            "status": "ACTIVE"
        })
        if "error" in ad:
            raise Exception("Ad: " + ad["error"]["message"])

        txt = (
            "🎉 *Reklama muvaffaqiyatli yoqildi!*\n\n"
            f"📌 Nom: *{d['name']}*\n"
            f"🆔 Campaign: `{camp['id']}`\n"
            f"🆔 AdSet: `{adset['id']}`\n"
            f"🆔 Ad: `{ad['id']}`\n\n"
            f"💰 Byudjet: ${d['budget']}/kun\n"
            "📊 /stats buyrug'i bilan kuzating"
        )
        await query.edit_message_text(txt, parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ Xato: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi. /newad bilan qayta boshlang.")
    return ConversationHandler.END

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    txt = (
        "📖 *Yordam*\n\n"
        "*Reklama:*\n"
        "/newad — Yangi reklama (ketma-ket)\n"
        "/campaigns — Kampaniyalar ro'yxati\n"
        "/pause `ID` — To'xtatish\n"
        "/resume `ID` — Yoqish\n"
        "/budget `ID` `$` — Byudjet o'zgartirish\n\n"
        "*Analitika:*\n"
        "/stats — CTR, CPM, Lead, CPL va boshqalar\n\n"
        "*Lead Formalar:*\n"
        "/forms — Formalar ro'yxati + dublikat\n\n"
        "*Boshqa:*\n"
        "/cancel — Jarayonni bekor qilish\n"
        "/help — Shu yordam"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")

def main():
    app = Application.builder().token(TG_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("newad", newad_start)],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            S_OBJ: [CallbackQueryHandler(get_obj, pattern="^obj_")],
            S_BUDGET_TYPE: [CallbackQueryHandler(get_budget_type, pattern="^budget_")],
            S_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            S_AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_audience)],
            S_CONVLOC: [CallbackQueryHandler(get_convloc, pattern="^conv_")],
            S_LEADFORM: [CallbackQueryHandler(get_leadform, pattern="^form_")],
            S_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_text)],
            S_HEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_headline)],
            S_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, get_image),
                CommandHandler("skip", skip_image)
            ],
            S_CONFIRM: [CallbackQueryHandler(confirm_launch, pattern="^confirm_")]
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
