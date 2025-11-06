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

from urllib.parse import urlparse
import re

def get_api_url_from_link(user_url: str):
    """
    Erkennt Domain + Match-ID aus einem beliebigen HLL-Statistik-Link
    und gibt den passenden API-Endpunkt zurück.
    Funktioniert mit hll-pnx.de, hlladmin.com, bakercompany.gg usw.
    """
    parsed = urlparse(user_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    match = re.search(r"/games/(\d+)", parsed.path)
    if not match:
        raise ValueError("❌ Keine Match-ID im Link gefunden.")
    match_id = match.group(1)
    api_url = f"{base_url}/get_map_scoreboard?map_id={match_id}"
    return api_url


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

# ---- DISCORD BEFEHL ---- #

import csv
import io

@bot.command()
@commands.has_any_role(1433041166135201882, 1433041166135201887)
async def stats(ctx):
    await ctx.send("📎 Bitte sende den Link zur Spielstatistik (z. B. https://stats.hll-pnx.de/games/560)")

    def check_link(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # --- Warte auf Link ---
    link_msg = await bot.wait_for("message", check=check_link)
    user_link = link_msg.content.strip()

    # --- Frage Teamfarbe ab ---
    await ctx.send("🎨 Welche Farbe hatte euer Team? (rot oder blau)")
    color_msg = await bot.wait_for("message", check=check_link)
    team_color = color_msg.content.strip().lower()

    await ctx.send("⏳ Verarbeite Matchdaten...")

    try:
        # Match-ID extrahieren
        import re
        match = re.search(r"/games/(\d+)", user_link)
        if not match:
            await ctx.send("❌ Kein gültiger Match-Link gefunden.")
            return

        match_id = match.group(1)
        csv_url = f"https://stats.hll-pnx.de/export_game_csv/{match_id}"

        # CSV laden
        response = requests.get(csv_url)
        response.raise_for_status()

        csv_content = response.content.decode("utf-8")
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        print("📄 CSV geladen, Spalten:", rows[0])

        # In Google Sheet schreiben
        header = rows[0]
        data = rows[1:]

        sheet.clear()
        sheet.append_row(header)
        for row in data:
            sheet.append_row(row)

        # Embed-Antwort im Discord
        import discord
        embed = discord.Embed(
            title="📊 Matchdaten eingetragen",
            description=f"Spiel erfolgreich verarbeitet.\n[🔗 Zur Statistik]({user_link})",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Teamfarbe", value=team_color.capitalize(), inline=True)
        embed.add_field(name="Spieler gespeichert", value=str(len(data)), inline=True)
        embed.set_footer(text="GCN StatsBot")

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Fehler beim Verarbeiten der Daten: `{e}`")
        print("❌ Fehler:", e)


bot.run(TOKEN)
