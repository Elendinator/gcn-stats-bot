import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import aiohttp
import datetime

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

async def parse_match_page(match_url: str, team_color: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(match_url) as response:
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("Keine Tabellen auf der Seite gefunden.")

    def has_headers(table, headers):
        found = [th.text.strip().lower() for th in table.select("th")]
        return all(any(h in f for f in found) for h in headers)

    stat_tables = [t for t in tables if has_headers(t, ["player", "kills", "deaths"])]

    if not stat_tables:
        raise ValueError("Keine Teamstatistik-Tabellen gefunden.")

    team_names = [el.text.strip() for el in soup.select(".team-name, .text-uppercase")]
    if len(team_names) < 2:
        team_names = ["Team Blau", "Team Rot"]

    if team_color.lower() == "blau":
        our_team = team_names[0]
        table = stat_tables[0]
    else:
        our_team = team_names[-1]
        table = stat_tables[-1]

    rows = table.select("tr")[1:]
    player_data = []
    for row in rows:
        cols = [c.text.strip() for c in row.select("td")]
        if len(cols) < 5:
            continue
        player_data.append({
            "player": cols[0],
            "kills": cols[1],
            "deaths": cols[2],
            "kd": cols[3],
            "killstreak": cols[4]
        })

    info = soup.find("div", class_="match-header")
    winner = "Unbekannt"
    duration = "?"
    if info:
        text = info.get_text(" ", strip=True)
        if "Winner" in text:
            winner = text.split("Winner")[1].split()[0]
        if "Duration" in text:
            duration = text.split("Duration")[1].split()[0]

    return {
        "team": our_team,
        "winner": winner,
        "duration": duration,
        "players": player_data
    }



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
@commands.has_any_role(1433041166135201882, 1433041166135201887)
async def stats(ctx):
    await ctx.send("📎 Bitte sende den Link zur Spielstatistik (z. B. https://stats.hll-pnx.de/games/560)")
    
    def check_link(m):
        return m.author == ctx.author and m.channel == ctx.channel

    link_msg = await bot.wait_for("message", check=check_link)
    match_url = link_msg.content.strip()

    await ctx.send("🎨 Welche Farbe hatte euer Team? (rot oder blau)")

    def check_color(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["rot", "blau"]

    color_msg = await bot.wait_for("message", check=check_color)
    team_color = color_msg.content.lower()

    try:
        await ctx.send("⏳ Verarbeite Matchdaten...")
        data = await parse_match_page(match_url, team_color)

        for p in data["players"]:
            sheet.append_row([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data["team"],
                team_color,
                p["player"],
                p["kills"],
                p["deaths"],
                p["kd"],
                p["killstreak"],
                data["winner"],
                data["duration"],
                match_url
            ])

        embed = discord.Embed(
            title=f"📊 Matchauswertung – {data['team']}",
            description=f"**Gewinner:** {data['winner']}\n**Dauer:** {data['duration']}\n[📎 Vollständige Statistik]({match_url})",
            color=discord.Color.blue() if team_color == "blau" else discord.Color.red()
        )

        top3 = sorted(data["players"], key=lambda x: float(x['kills']), reverse=True)[:3]
        for i, player in enumerate(top3, start=1):
            embed.add_field(
                name=f"#{i} {player['player']}",
                value=f"💀 {player['kills']} | ☠️ {player['deaths']} | 🎯 {player['kd']} | 🔥 {player['killstreak']}",
                inline=False
            )

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Fehler beim Verarbeiten: {e}")



bot.run(TOKEN)
