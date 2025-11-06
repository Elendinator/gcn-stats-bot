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

import discord
from discord.ext import commands
import aiohttp
from bs4 import BeautifulSoup
import datetime

# Admin Rollen
ADMIN_ROLES = [1433041166135201882, 1433041166135201887]

@bot.command(name="stats")
@commands.has_any_role(*ADMIN_ROLES)
async def fetch_stats(ctx):
    await ctx.send("📎 Bitte sende den Link zur Spielstatistik (z. B. `https://stats.hll-pnx.de/games/560`)")

    def check_link(m):
        return m.author == ctx.author and m.channel == ctx.channel and "https://stats.hll-pnx.de/games/" in m.content

    try:
        msg = await bot.wait_for("message", check=check_link, timeout=120)
        match_url = msg.content.strip()
    except:
        return await ctx.send("❌ Zeit abgelaufen. Bitte gib den Befehl erneut ein.")

    await ctx.send("🎨 Welche Farbe hatte euer Team? (rot oder blau)")

    def check_color(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["rot", "blau"]

    try:
        color_msg = await bot.wait_for("message", check=check_color, timeout=60)
        team_color = color_msg.content.lower()
    except:
        return await ctx.send("❌ Keine Farbe angegeben. Bitte versuche es erneut.")

    await ctx.send("🔄 Verarbeite Matchdaten...")

    async with aiohttp.ClientSession() as session:
        async with session.get(match_url) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")

    # 🧩 Grunddaten ermitteln
    try:
        match_id = match_url.split("/")[-1]
        teams = [t.text.strip() for t in soup.select(".team-name")]
        winner = soup.select_one(".winner-team").text.strip() if soup.select_one(".winner-team") else "Unbekannt"
        duration = soup.select_one(".match-duration").text.strip() if soup.select_one(".match-duration") else "Unbekannt"
    except Exception as e:
        return await ctx.send(f"❌ Fehler beim Auslesen der Matchdaten: {e}")

        # 🧩 Teamtabellen auslesen (robuste Variante)
    team_tables = soup.select("div.team-table")
    if not team_tables:
        return await ctx.send("❌ Keine Teamtabellen auf der Seite gefunden. Bitte prüfe den Link.")

    # Teamnamen extrahieren
    all_team_names = [t.text.strip() for t in soup.select(".team-name")]
    if len(all_team_names) < 2:
        all_team_names = ["Team Blau", "Team Rot"]

    # Teamzuordnung
    if team_color == "blau":
        team_index = 0
        our_team_name = all_team_names[0]
        enemy_team_name = all_team_names[1]
    else:
        team_index = 1
        our_team_name = all_team_names[1]
        enemy_team_name = all_team_names[0]

    try:
        team_table = team_tables[team_index]
        rows = team_table.select("tbody tr")
    except Exception as e:
        return await ctx.send(f"❌ Fehler beim Lesen der Teamdaten: {e}")

    if not rows:
        return await ctx.send("❌ Konnte keine Spielerzeilen finden — möglicherweise wurde das Match nicht korrekt geladen.")

    data_to_write = []
    for row in rows:
        cols = [c.text.strip() for c in row.select("td")]
        if len(cols) < 5:
            continue

        player = cols[0]
        kills = cols[1]
        deaths = cols[2]
        kd = cols[3]
        killstreak = cols[4]

        data_to_write.append([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            match_id,
            our_team_name,
            team_color,
            enemy_team_name,
            winner,
            duration,
            player,
            kills,
            deaths,
            kd,
            killstreak,
            match_url
        ])

    # 🧾 In Google Sheet schreiben
    try:
        sheet.append_rows(data_to_write, value_input_option="RAW")
        await ctx.send(f"✅ {len(data_to_write)} Spielerstatistiken erfolgreich in **GCN_Stats** gespeichert!")
    except Exception as e:
        return await ctx.send(f"❌ Fehler beim Schreiben in Google Sheets: {e}")

    # 🏆 Embed erstellen
    sorted_players = sorted(data_to_write, key=lambda x: int(x[8]) if x[8].isdigit() else 0, reverse=True)
    top3 = sorted_players[:3]
    top3_text = "\n".join([
        f"**{i+1}. {p[7]}** — {p[8]} K / {p[9]} D (KD {p[10]}, Serie {p[11]})"
        for i, p in enumerate(top3)
    ])

    embed = discord.Embed(
        title=f"📊 Match-Auswertung #{match_id}",
        description=f"🏆 **Gewinner:** {winner}\n🕓 **Dauer:** {duration}\n🎨 **Teamfarbe:** {team_color.capitalize()}",
        color=discord.Color.blue() if team_color == "blau" else discord.Color.red()
    )
    embed.add_field(name="Top 3 Spieler", value=top3_text, inline=False)
    embed.add_field(name="🔗 Vollständige Statistik", value=f"[Zur Website]({match_url})", inline=False)
    embed.set_footer(text=f"Erstellt am {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    await ctx.send(embed=embed)

@fetch_stats.error
async def stats_error(ctx, error):
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl zu verwenden.")
    else:
        await ctx.send(f"❌ Fehler: {error}")


bot.run(TOKEN)
