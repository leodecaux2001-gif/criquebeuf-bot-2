from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}

FRENCH_MONTHS = {
    "jan": 1,
    "janv": 1,
    "fév": 2,
    "fev": 2,
    "fév.": 2,
    "fev.": 2,
    "mar": 3,
    "avr": 4,
    "mai": 5,
    "jun": 6,
    "juin": 6,
    "jui": 7,
    "juil": 7,
    "aoû": 8,
    "aou": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12,
    "dec": 12,
}

DATE_RE = re.compile(
    r"^(?:lun|mar|mer|jeu|ven|sam|dim)\s+(\d{1,2})\s+([A-Za-zéûôàèùç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})$",
    re.IGNORECASE,
)

SCORE_RE = re.compile(r"^(\d+)\s+(\d+)$")
TIME_ONLY_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
GOAL_EVENT_RE = re.compile(r"But pour\s+(.+?)\s+inscrit par\s+(.+)$", re.IGNORECASE)


@dataclass
class MatchInfo:
    match_id: str
    match_url: str
    kickoff_iso: str
    competition: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    venue: str | None
    address: str | None
    scorers: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class FFFScraper:
    def __init__(self, timezone_name: str = "Europe/Paris") -> None:
        self.tz = ZoneInfo(timezone_name)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _clean_lines(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines()]
        return [line for line in lines if line]

    def _parse_french_datetime(self, value: str) -> datetime | None:
        m = DATE_RE.match(value.strip())
        if not m:
            return None
        day = int(m.group(1))
        month_label = m.group(2).lower().replace(".", "")[:4]
        month = FRENCH_MONTHS.get(month_label)
        if month is None:
            month = FRENCH_MONTHS.get(month_label[:3])
        if month is None:
            return None
        year = int(m.group(3))
        hour = int(m.group(4))
        minute = int(m.group(5))
        return datetime(year, month, day, hour, minute, tzinfo=self.tz)

    def extract_match_links(self, calendar_url: str) -> list[str]:
        soup = self._get_soup(calendar_url)
        links: list[str] = []
        seen: set[str] = set()
        for anchor in soup.select('a[href*="/competition/match/"]'):
            href = anchor.get("href")
            if not href:
                continue
            absolute = urljoin(calendar_url, href)
            if absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
        return links

    def parse_match_page(self, match_url: str, team_name: str) -> MatchInfo | None:
        soup = self._get_soup(match_url)
        text = soup.get_text("\n", strip=True)
        lines = self._clean_lines(text)

        kickoff = None
        for line in lines[:20]:
            kickoff = self._parse_french_datetime(line)
            if kickoff:
                break
        if kickoff is None:
            return None

        # find first two occurrences around the header matching team-like lines
        home_team = None
        away_team = None
        competition = None
        home_score = None
        away_score = None

        for idx, line in enumerate(lines[:50]):
            if line == "Le match" and idx >= 1:
                # usually the competition is a few lines above the teams header; continue scanning anyway
                pass

        # competition = first non-empty line after kickoff which is not 'Image'
        kickoff_index = next((i for i, line in enumerate(lines) if self._parse_french_datetime(line)), 0)
        for line in lines[kickoff_index + 1 : kickoff_index + 8]:
            if line.lower() not in {"image", "recherche mes favoris", "le match", "statistiques", "autres matchs", "classement détaillé", "vidéos"}:
                competition = line
                break

        # header block: kickoff, competition, home, score/time, away
        scan = lines[kickoff_index + 1 : kickoff_index + 20]
        filtered = [x for x in scan if x.lower() not in {"image", "recherche mes favoris", "le match", "statistiques", "autres matchs", "classement détaillé", "vidéos"}]
        if len(filtered) >= 4:
            # [competition, home, score/time, away, ...]
            competition = filtered[0]
            home_team = filtered[1]
            middle = filtered[2]
            away_team = filtered[3]
            score_match = SCORE_RE.match(middle)
            if score_match:
                home_score = int(score_match.group(1))
                away_score = int(score_match.group(2))

        if not home_team or not away_team:
            return None
        if team_name not in {home_team, away_team}:
            return None

        venue = None
        address = None
        for idx, line in enumerate(lines):
            if line.lower() == "lieu de la rencontre":
                if idx + 1 < len(lines):
                    venue = lines[idx + 1]
                address_parts: list[str] = []
                for extra in lines[idx + 2 : idx + 6]:
                    if extra.lower() in {"voir sur la carte", "résumé", "composition", "le match"}:
                        break
                    address_parts.append(extra)
                if address_parts:
                    address = " ".join(address_parts)
                break

        scorers: list[dict] = []
        in_summary = False
        last_minute: str | None = None
        for line in lines:
            lower = line.lower()
            if lower == "résumé":
                in_summary = True
                continue
            if in_summary and lower in {"composition", "autres matchs", "classement", "classement détaillé"}:
                break
            if not in_summary:
                continue

            if re.match(r"^\d{1,3}[’']$", line):
                last_minute = line.replace("'", "’")
                continue

            goal_match = GOAL_EVENT_RE.search(line)
            if goal_match and last_minute:
                event_team = goal_match.group(1).strip()
                scorer = goal_match.group(2).strip()
                scorers.append(
                    {
                        "minute": last_minute,
                        "team": event_team,
                        "scorer": scorer,
                    }
                )
                last_minute = None

        match_id_match = re.search(r"/competition/match/(\d+)-", match_url)
        match_id = match_id_match.group(1) if match_id_match else f"{kickoff.isoformat()}::{home_team}::{away_team}"

        return MatchInfo(
            match_id=match_id,
            match_url=match_url,
            kickoff_iso=kickoff.isoformat(),
            competition=competition or "Compétition",
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            venue=venue,
            address=address,
            scorers=scorers,
        )

    def get_team_matches(self, calendar_url: str, team_name: str) -> list[MatchInfo]:
        matches: list[MatchInfo] = []
        for link in self.extract_match_links(calendar_url):
            try:
                match = self.parse_match_page(link, team_name)
                if match:
                    matches.append(match)
            except Exception:
                continue
        matches.sort(key=lambda m: m.kickoff_iso)
        return matches

    def get_next_match(self, calendar_url: str, team_name: str) -> MatchInfo | None:
        now = datetime.now(self.tz)
        matches = self.get_team_matches(calendar_url, team_name)
        upcoming = [m for m in matches if datetime.fromisoformat(m.kickoff_iso) >= now]
        return upcoming[0] if upcoming else None

    def get_match_by_id(self, calendar_url: str, team_name: str, match_id: str) -> MatchInfo | None:
        for match in self.get_team_matches(calendar_url, team_name):
            if match.match_id == match_id:
                return match
        return None
