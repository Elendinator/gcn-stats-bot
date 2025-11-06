import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio

# ---- KONFIGURATION ---- #
import os
TOKEN = os.getenv("DISCORD_TOKEN")
SPREADSHEET_NAME = "GCN_Stats"
ALLOWED_CHANNEL_ID = 1435544801431781549  # Channel-ID (#spiel-statistik), wo der Bot auf Links reagieren soll

# ---- GOOGLE SHEET SETUP (Railway fix for real newlines) ---- #
import os, json, gspread
from google.oauth2.service_account import Credentials

print("🚀 DEBUG: DISCORD_TOKEN gefunden:", bool(TOKEN))
print("🚀 DEBUG: GOOGLE_CREDS vorhanden:", bool(os.getenv("GOOGLE_CREDS")))
raw_creds = os.getenv("GOOGLE_CREDS")
print("🚀 DEBUG: Länge GOOGLE_CREDS:", len(raw_creds or "0"))

scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

try:
    # 🧩 Falls echte Zeilenumbrüche im Key sind → zu \n umwandeln
    fixed_creds = raw_creds.replace("\n", "\\n")

    google_creds = json.loads(fixed_creds)
    creds = Credentials.from_service_account_info(google_creds, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).sheet1

    print("🔍 Teste Google Sheets Zugriff...")
    test_value = sheet.cell(1, 1).value
    print("✅ Erfolgreich verbunden! Zelle A1:", test_value)

except Exception as e:
    print("❌ Zugriff auf Google Sheets fehlgeschlagen:", e)


# ---- Google Credentials laden ---- #
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

try:
    google_creds = json.loads(os.getenv("GOOGLE_CREDS"))
    creds = Credentials.from_service_account_info(google_creds, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).sheet1
    print("🔍 Teste Google Sheets Zugriff...")

    # Test: Lese Zelle A1
    test_value = sheet.cell(1, 1).value
    print("✅ Erfolgreich verbunden! Zelle A1:", test_value)

except Exception as e:
    print("❌ Zugriff auf Google Sheets fehlgeschlagen:", e)

# ---- DISCORD BOT SETUP ---- #
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # <-- nötig für Rollen & Member Events
intents.presences = True  # <-- falls du Online-Status brauchst

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- STATISTIKAUSLESUNG ---- #
def extract_stats_from_link(link, team_color):
    """Liest HLL Stats von einer Webadresse aus (sohhllbr-stats-Seite)."""
    response = requests.get(link)
    soup = BeautifulSoup(response.text, "html.parser")

    players = []
    table_rows = soup.find_all("tr")
    for row in table_rows:
        cols = [col.text.strip() for col in row.find_all("td")]
        if len(cols) > 5:
            name = cols[1]
            kills = cols[2]
            deaths = cols[3]
            kd = cols[4]
            players.append((name, kills, deaths, kd))
    return players

# ---- DISCORD BEFEHL ---- #
@bot.command()
async def match(ctx):
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        return await ctx.send("❌ Dieser Befehl ist hier nicht erlaubt!")

    await ctx.send("Bitte sende den Match-Link 📎:")
    try:
        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=60)
        link = msg.content
        await ctx.send("Welche Teamfarbe hattest du? (🔵 Blau / 🔴 Rot)")
        color_msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30)
        team_color = color_msg.content.lower()

        await ctx.send("📊 Lese Statistik aus...")
        players = extract_stats_from_link(link, team_color)

        await ctx.send(f"✅ {len(players)} Spieler gefunden – speichere Daten in Google Sheet...")
        for name, kills, deaths, kd in players:
            sheet.append_row([name, kills, deaths, kd])

        await ctx.send("💾 Statistik erfolgreich gespeichert!")

    except asyncio.TimeoutError:
        await ctx.send("⏰ Zeit abgelaufen. Bitte starte den Befehl erneut mit !match")

@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user}")

bot.run(TOKEN)
