from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands, tasks
from zoneinfo import ZoneInfo

from fff_scraper import FFFScraper, MatchInfo
from storage import load_state, save_state

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    CONFIG = json.load(f)

import os

TOKEN = os.getenv("TOKEN") or CONFIG["token"]
CHANNEL_NAME = CONFIG["channel_name"]
ANNOUNCE_EVERYONE = bool(CONFIG.get("announce_everyone", True))
TEAM_NAME = CONFIG["team_name"]
EMOJI = CONFIG.get("emoji", ":criquebeuf:")
MATCH_URL = CONFIG["match_url"]
LOGO_URL = CONFIG.get("logo_url")
CHECK_INTERVAL_MINUTES = int(CONFIG.get("check_interval_minutes", 15))
TZ = ZoneInfo(CONFIG.get("timezone", "Europe/Paris"))

scraper = FFFScraper(CONFIG.get("timezone", "Europe/Paris"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def format_dt_fr(kickoff: datetime) -> tuple[str, str]:
    weekdays = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    date_str = f"{weekdays[kickoff.weekday()]} {kickoff.day} {months[kickoff.month - 1]} {kickoff.year}"
    hour_str = kickoff.strftime("%Hh%M")
    return date_str, hour_str


def build_match_embed(match: MatchInfo, title: str, description: str | None = None) -> discord.Embed:
    kickoff = datetime.fromisoformat(match.kickoff_iso).astimezone(TZ)
    date_str, hour_str = format_dt_fr(kickoff)

    embed = discord.Embed(title=f"{title} {EMOJI}", color=0x2ECC71)
    if LOGO_URL:
        embed.set_thumbnail(url=LOGO_URL)

    embed.add_field(name="Match", value=f"{match.home_team} 🆚 {match.away_team}", inline=False)
    embed.add_field(name="📅 Date", value=date_str, inline=True)
    embed.add_field(name="⏲️ Heure", value=hour_str, inline=True)
    embed.add_field(name="🏆 Compétition", value=match.competition, inline=False)
    embed.add_field(name="📍 Stade", value=match.venue or "À confirmer", inline=False)
    embed.add_field(name="🏠 Adresse", value=match.address or "À confirmer", inline=False)
    embed.description = description or (
        "Venez supporter l'équipe ! 🔥\n"
        "Vos pronostics ? 😈\n\n"
        "**VICTOIRE ✅ DEFAITE ❌**"
    )
    return embed


async def get_target_channels() -> list[discord.TextChannel]:
    channels: list[discord.TextChannel] = []
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
        if channel is not None:
            channels.append(channel)
    return channels


async def announce_match(match: MatchInfo) -> None:
    channels = await get_target_channels()
    if not channels:
        return

    embed = build_match_embed(match, "⚽ PROCHAIN MATCH")
    content = "@everyone" if ANNOUNCE_EVERYONE else None

    for channel in channels:
        message = await channel.send(content=content, embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")


async def send_reminder(match: MatchInfo, label: str) -> None:
    channels = await get_target_channels()
    if not channels:
        return
    embed = build_match_embed(match, f"⏰ RAPPEL MATCH ({label})")
    content = "@everyone" if ANNOUNCE_EVERYONE else None
    for channel in channels:
        await channel.send(content=content, embed=embed)


async def send_result(match: MatchInfo) -> None:
    channels = await get_target_channels()
    if not channels:
        return

    our_score = match.home_score if match.home_team == TEAM_NAME else match.away_score
    opp_team = match.away_team if match.home_team == TEAM_NAME else match.home_team
    opp_score = match.away_score if match.home_team == TEAM_NAME else match.home_score

    embed = discord.Embed(title=f"⚽ RÉSULTAT DU MATCH {EMOJI}", color=0x3498DB)
    if LOGO_URL:
        embed.set_thumbnail(url=LOGO_URL)

    if our_score is not None and opp_score is not None:
        embed.add_field(name="Score", value=f"{TEAM_NAME} {our_score} - {opp_score} {opp_team}", inline=False)
        if our_score > opp_score:
            embed.add_field(name="Résultat", value="✅ Victoire", inline=False)
        elif our_score < opp_score:
            embed.add_field(name="Résultat", value="❌ Défaite", inline=False)
        else:
            embed.add_field(name="Résultat", value="🤝 Match nul", inline=False)
    else:
        embed.add_field(name="Score", value="Résultat non disponible pour le moment.", inline=False)

    our_scorers = [s for s in match.scorers if s.get("team") == TEAM_NAME]
    if our_scorers:
        lines = [f"⚽ {entry['scorer']} {entry['minute']}" for entry in our_scorers]
        embed.add_field(name="Buteurs", value="\n".join(lines), inline=False)
    else:
        embed.add_field(
            name="Buteurs",
            value="La FFF n'affiche pas de buteurs / minutes pour cette rencontre, ou ils ne sont pas encore publiés.",
            inline=False,
        )

    for channel in channels:
        await channel.send(embed=embed)


async def process_matches(force: bool = False) -> None:
    state = load_state()
    state.setdefault("matches", {})
    now = datetime.now(TZ)

    matches = scraper.get_team_matches(MATCH_URL, TEAM_NAME)
    if not matches:
        return

    for match in matches:
        record = state["matches"].setdefault(
            match.match_id,
            {
                "match_id": match.match_id,
                "match_url": match.match_url,
                "kickoff_iso": match.kickoff_iso,
                "announced": False,
                "reminder_24h": False,
                "reminder_2h": False,
                "result_sent": False,
            },
        )
        # refresh metadata
        record["match_url"] = match.match_url
        record["kickoff_iso"] = match.kickoff_iso

        kickoff = datetime.fromisoformat(match.kickoff_iso).astimezone(TZ)

        if kickoff >= now and not record["announced"]:
            await announce_match(match)
            record["announced"] = True

        if kickoff - timedelta(hours=24) <= now < kickoff and not record["reminder_24h"]:
            await send_reminder(match, "24H")
            record["reminder_24h"] = True

        if kickoff - timedelta(hours=2) <= now < kickoff and not record["reminder_2h"]:
            await send_reminder(match, "2H")
            record["reminder_2h"] = True

        if now >= kickoff + timedelta(hours=5) and not record["result_sent"]:
            refreshed = scraper.get_match_by_id(MATCH_URL, TEAM_NAME, match.match_id) or match
            await send_result(refreshed)
            record["result_sent"] = True

    save_state(state)


@bot.event
async def on_ready() -> None:
    print(f"Connecté en tant que {bot.user}")
    if not match_loop.is_running():
        match_loop.change_interval(minutes=CHECK_INTERVAL_MINUTES)
        match_loop.start()
    await process_matches(force=True)


@tasks.loop(minutes=15)
async def match_loop() -> None:
    try:
        await process_matches()
    except Exception as exc:
        print(f"Erreur dans match_loop: {exc}")


@bot.command(name="prochainmatch")
async def prochainmatch(ctx: commands.Context) -> None:
    match = scraper.get_next_match(MATCH_URL, TEAM_NAME)
    if match is None:
        await ctx.send("Aucun prochain match n'a été trouvé sur la page FFF.")
        return
    await ctx.send(embed=build_match_embed(match, "⚽ PROCHAIN MATCH"))


@bot.command(name="forcercheck")
@commands.has_permissions(administrator=True)
async def forcercheck(ctx: commands.Context) -> None:
    await ctx.send("Je lance une vérification immédiate.")
    await process_matches(force=True)


@forcercheck.error
async def forcercheck_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Il faut être administrateur pour utiliser cette commande.")
    else:
        await ctx.send("Impossible d'exécuter la commande.")

@bot.command(name="testmatch")
async def testmatch(ctx: commands.Context) -> None:

    embed = discord.Embed(
        title="⚽ PROCHAIN MATCH :criquebeuf:",
        color=0x2ecc71
    )

    embed.add_field(
        name="Match",
        value="AS CRIQUEBEUF FB 🆚 FC TEST",
        inline=False
    )

    embed.add_field(name="📅 Date", value="Dimanche 22 Mars")
    embed.add_field(name="⏲️ Heure", value="14H30")
    embed.add_field(name="📍 Stade", value="Stade Municipal")
    embed.add_field(name="🏠 Adresse", value="Criquebeuf-sur-Seine", inline=False)

    embed.description = """
Venez supporter l'équipe ! 🔥
Vos pronostics ? 😈

VICTOIRE ✅ DEFAITE ❌
"""

    message = await ctx.send("@everyone", embed=embed)

    await message.add_reaction("✅")
    await message.add_reaction("❌")

@bot.command(name="derniermatch")
async def derniermatch(ctx):

    match = scraper.get_last_match(MATCH_URL, TEAM_NAME)

    if match is None:
        await ctx.send("Impossible de trouver le dernier match.")
        return

    message = (
        f"⚽ DERNIER MATCH :criquebeuf:\n\n"
        f"{TEAM_NAME} {match['score']} {match['adversaire']}\n\n"
        f"⚽ Buteurs:\n{match['buteurs']}\n\n"
        f"📅 {match['date']}\n"
        f"📍 {match['stade']}"
    )

    await ctx.send(message)

@bot.command(name="classement")
async def classement(ctx):

    table = scraper.get_classement(MATCH_URL)

    if table is None:
        await ctx.send("Impossible de récupérer le classement.")
        return

    message = "🏆 CLASSEMENT DU CHAMPIONNAT\n\n"

    for team in table[:10]:
        message += f"{team['position']}. {team['team']} - {team['points']} pts\n"

    await ctx.send(message)


if __name__ == "__main__":
    bot.run(TOKEN)
