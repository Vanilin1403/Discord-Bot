import os
import random
import json
import discord
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
from discord.ext import commands

# CONFIG
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel("gemini-2.5-flash-lite")
media_model = genai.GenerativeModel("gemini-2.5-pro")

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

# MEMORY
MEMORY_FILE = "memory.json"
SHORT_MEMORY_LIMIT = 12
MEMORY_LIMIT = 800

conversation_history = {}
conversation_summary = {}
short_memory = {}
user_profiles = {}

# Emojis
EMOTION_EMOJIS = {
    "Pleading": "🥺",
    "anger": "💢",
    "sadness": "😭",
    "broken": "💔",
    "agree": "✅",
    "disagree": "❌"
}

EMOJI_POOL = ["🥺", "💢", "😭", "💔", "✅", "❌"]

# UTIL
def load_memory():
    global conversation_history, conversation_summary, short_memory, user_profiles
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            conversation_history = data.get("history", {})
            conversation_summary = data.get("summary", {})
            short_memory = data.get("short_memory", {})
            user_profiles = data.get("users", {})
    else:
        conversation_history = {}
        conversation_summary = {}
        short_memory = {}
        user_profiles = {}

def save_memory():
    data = {
        "history": conversation_history,
        "summary": conversation_summary,
        "short_memory": short_memory,
        "users": user_profiles
    }
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def set_user_role(user_id: int, role: str):
    uid = str(user_id)
    if uid not in user_profiles:
        user_profiles[uid] = {"id": uid, "name": "Unknown", "role": role}
    else:
        user_profiles[uid]["role"] = role
    save_memory()

def get_user_profile(user: discord.User) -> str:
    uid = str(user.id)
    if uid not in user_profiles:
        user_profiles[uid] = {"id": uid, "name": user.name, "role": ""}
        save_memory()
    profile = user_profiles[uid]
    role_text = f"Role: {profile['role']}." if profile.get("role") else ""
    return f"user {profile['name']} (ID: {profile['id']}) participates in the chat. {role_text}"

# REPLY
async def generate_reply(content: str, channel_id: str, last_author: discord.User) -> str:
    role_text = get_user_profile(last_author)
    short_context = "\n".join(short_memory.get(channel_id, []))
    history = conversation_history.get(channel_id, [])
    summary = conversation_summary.get(channel_id, "We oly get started.")

    prompt = f"""
Personality:
Your Prompt here

{role_text}

Short-term memory:
{short_context}

Context of past messages (resume):
{summary}

History:
{chr(10).join(history)}

Last message from user {last_author.name} (ID: {last_author.id}):
"{content}"
Answer casually:
"""
    try:
        response = await asyncio.to_thread(text_model.generate_content, [prompt])
        text = response.text.strip()
        return text
    except Exception as e:
        print(f"[REPLY ERROR]: {e}")
        return "I'm tired🥱 Let's talk later?"

# MEDIA
async def analyze_media(attachment: discord.Attachment) -> str:
    try:
        data = await attachment.read()
        response = await asyncio.to_thread(
            media_model.generate_content,
            [
                {
                    "inline_data": {
                        "mime_type": attachment.content_type,
                        "data": data
                    }
                },
                {"text": "React to the content of the photo/gif/video."}
            ]
        )
        return response.text.strip()
    except Exception as e:
        print(f"[MEDIA ERROR]: {e}")
        return "What did you say?"

async def react_to_action(attachment: discord.Attachment) -> str | None:
    try:
        data = await attachment.read()
        response = await asyncio.to_thread(
            media_model.generate_content,
            [
                {
                    "inline_data": {
                        "mime_type": attachment.content_type,
                        "data": data
                    }
                },
                {"text": "If the image shows an action being done to another person, react as if it were done to you."}
            ]
        )
        desc = response.text.strip().lower()
        if "No" in desc:
            return None
        reply = await asyncio.to_thread(
            text_model.generate_content,
            [f"The image/video shows the action: {desc}. Answer as if it were done to you. Briefly."]
        )
        return reply.text.strip()
    except Exception as e:
        print(f"[ACTION ERROR]: {e}")
        return None

# EMOTIONS
async def detect_emotion(message: discord.Message) -> str:
    content = message.content or ""
    attachments = message.attachments
    attachment_info = " ".join([f"[{att.filename}]" for att in attachments]) if attachments else ""
    prompt = f"""
Identify the emotion in the message:
"{content} {attachment_info}"
Choose one word:
Pleading, anger, sadness, broken, agree, disagree.
"""
    try:
        response = await asyncio.to_thread(text_model.generate_content, [prompt])
        emotion = response.text.strip().lower()
        return emotion if emotion in EMOTION_EMOJIS else "Pleading"
    except Exception as e:
        print(f"[EMOTION ERROR]: {e}")
        return "broken"

# COMMANDS
@bot.tree.command(name="clear", description="Clears the bot's memory in this chat.")
async def clear_command(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    conversation_history.pop(channel_id, None)
    conversation_summary.pop(channel_id, None)
    short_memory.pop(channel_id, None)
    save_memory()
    await interaction.response.send_message("Memory cleared! Ready for use <3")

@bot.tree.command(name="memory", description="Shows what the bot remembers in this chat.")
async def memory_command(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    history = conversation_history.get(channel_id, [])
    summary = conversation_summary.get(channel_id, "No resume.")
    short = short_memory.get(channel_id, [])

    text = (
        f"** Short-term memory (latest {len(short)}):**\n"
        + "\n".join(short[-SHORT_MEMORY_LIMIT:]) + "\n\n"
        f"** Resume:**\n{summary}\n\n"
        f"** History (latest {len(history)}):**\n"
        + "\n".join(history[-10:])
    )
    if len(text) > 1900:
        text = text[:1900] + "...\n(cropped)"
    await interaction.response.send_message(text)

# EVENTS
@bot.event
async def on_ready():
    load_memory()
    await bot.tree.sync()
    print(f"The bot is enabled as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    if message.author.id == bot.user.id:
        return

    channel_id = str(message.channel.id)
    conversation_history.setdefault(channel_id, [])
    conversation_summary.setdefault(channel_id, "The dialogue has just begun.")
    short_memory.setdefault(channel_id, [])

    media_texts = []
    for att in message.attachments:
        desc = await analyze_media(att)
        media_texts.append(f"(attached media: {desc})")
        action_reply = await react_to_action(att)
        if action_reply:
            await message.reply(action_reply)
            return

    history_entry = f"{message.author.name}: \"{message.content}\" {' '.join(media_texts)}"
    conversation_history[channel_id].append(history_entry)
    short_memory[channel_id].append(history_entry)
    if len(short_memory[channel_id]) > SHORT_MEMORY_LIMIT:
        short_memory[channel_id] = short_memory[channel_id][-SHORT_MEMORY_LIMIT:]

    if len(conversation_history[channel_id]) > MEMORY_LIMIT:
        old_msgs = "\n".join(conversation_history[channel_id][:-MEMORY_LIMIT])
        try:
            summary_resp = await asyncio.to_thread(
                text_model.generate_content,
                [f"Give a brief summary of this chat:\n{old_msgs}"]
            )
            conversation_summary[channel_id] = summary_resp.text.strip()
        except Exception:
            pass
        conversation_history[channel_id] = conversation_history[channel_id][-MEMORY_LIMIT:]

    save_memory()

    if bot.user in message.mentions:
        async with message.channel.typing():
            reply = await generate_reply(message.content, channel_id, message.author)
        await message.reply(reply)
        return

    if random.randint(1, 40) == 1:
        async with message.channel.typing():
            reply = await generate_reply(message.content, channel_id, message.author)
            await message.reply(reply)

    if random.randint(1, 25) == 1:
        emotion = await detect_emotion(message)
        emoji = random.choice(EMOJI_POOL)
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
