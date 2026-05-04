"""
LaunchBox GamesDB provider (games supplement — HTML scraper).
Site: https://gamesdb.launchbox-app.com
No API / no key required.
Search URL: /games/results/{query}
Detail URL: /games/details/{id}-{slug}
Note: HTML scraping — may break if site layout changes.
"""

import re
import requests
from bs4 import BeautifulSoup
from modules.core.base_metadata import MetadataProvider


_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/124.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

_BASE = 'https://gamesdb.launchbox-app.com'


class LaunchBoxProvider(MetadataProvider):
    """Games metadata scraped from LaunchBox GamesDB (no API key required)."""

    def __init__(self, api_config: dict):
        super().__init__(api_config)

    def authenticate(self) -> bool:
        return True  # no auth needed

    def search(self, query: str) -> list:
        """Returns list of dicts with at minimum: id, name, url."""
        url = f'{_BASE}/games/results/{requests.utils.quote(query)}'
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f'[LaunchBox] Search request error: {e}')
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        results = []

        # Result rows: <tr> inside table with class 'table' or similar
        for row in soup.select('table tr'):
            link = row.find('a', href=re.compile(r'/games/details/'))
            if not link:
                continue
            href  = link.get('href', '')
            name  = link.get_text(strip=True)
            # Extract ID from URL: /games/details/12345-game-title
            m = re.search(r'/games/details/(\d+)', href)
            if not m:
                continue
            results.append({
                'id':   m.group(1),
                'name': name,
                'url':  _BASE + href if href.startswith('/') else href,
            })
            if len(results) >= 5:
                break

        return results

    def get_details(self, item_id) -> dict:
        """item_id is either a numeric ID string or a full detail URL."""
        if str(item_id).startswith('http'):
            url = item_id
        else:
            # We need the slug too — search results include the full url
            # If called with just ID, construct a best-guess URL
            url = f'{_BASE}/games/details/{item_id}'
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f'[LaunchBox] Details request error: {e}')
            return {}

        soup = BeautifulSoup(r.text, 'html.parser')
        data = {'_url': url}

        # Title
        h1 = soup.find('h1')
        if h1:
            data['title'] = h1.get_text(strip=True)

        # Detail table rows: <th>Label</th><td>Value</td>
        for row in soup.select('table.table-bordered tr, table tr'):
            th = row.find('th')
            td = row.find('td')
            if not th or not td:
                continue
            label = th.get_text(strip=True).lower()
            value = td.get_text(separator=' ', strip=True)

            if 'release' in label or 'year' in label or 'date' in label:
                m = re.search(r'\b(19\d{2}|20\d{2})\b', value)
                if m:
                    data['year'] = m.group(1)
            elif 'genre' in label:
                data['genre'] = value
            elif 'rating' in label and 'community' in label:
                m = re.search(r'[\d.]+', value)
                if m:
                    data['rating'] = m.group()
            elif 'platform' in label:
                data['platform'] = value
            elif 'developer' in label:
                data['developer'] = value
            elif 'publisher' in label:
                data['publisher'] = value
            elif 'max player' in label or 'players' in label:
                data['max_players'] = value

        # Description / overview
        for sel in ('.game-overview', '#overview', '.overview', '[itemprop="description"]'):
            el = soup.select_one(sel)
            if el:
                data['description'] = el.get_text(separator='\n', strip=True)
                break

        # Cover image
        for sel in ('.game-image img', '.cover img', 'img[src*="images/box"]', 'img[src*="cover"]'):
            img = soup.select_one(sel)
            if img and img.get('src'):
                src = img['src']
                data['cover_url'] = src if src.startswith('http') else _BASE + src
                break

        return data

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genre_str = raw.get('genre', '')
        genres    = [g.strip() for g in re.split(r'[,;/]', genre_str) if g.strip()] if genre_str else []
        genre     = genres[0] if genres else ''

        url = raw.get('_url', '') or raw.get('url', '')

        return {
            'name':         raw.get('title', '') or raw.get('name', ''),
            'year':         raw.get('year', ''),
            'rating':       raw.get('rating', ''),
            'description':  raw.get('description', ''),
            'cover_url':    raw.get('cover_url', ''),
            'genre':        genre,
            'genres':       genres,
            'provider_url': url,
            'website_url':  '',
            'slug':         '',
        }

    def search_and_extract(self, query: str) -> dict | None:
        results = self.search(query)
        if not results:
            return None
        details = self.get_details(results[0]['url'])
        if not details:
            # Fall back to extracting partial data from search result
            return self.extract(results[0])
        return self.extract(details)
