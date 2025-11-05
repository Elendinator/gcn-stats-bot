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

# ---- GOOGLE SHEET SETUP ---- #
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import os, json
from oauth2client.service_account import ServiceAccountCredentials

google_creds = json.loads(os.getenv("GOOGLE_CREDS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open(SPREADSHEET_NAME).sheet1

print("🔍 Teste Google Sheets Zugriff...")

try:
    # Lese den Wert aus Zelle A1
    test_value = sheet.cell(1, 1).value
    print("✅ Erfolgreich verbunden! Zelle A1:", test_value)
except Exception as e:
    print("❌ Zugriff fehlgeschlagen:", e)

# ---- DISCORD BOT SETUP ---- #
intents = discord.Intents.default()
intents.message_content = True
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
