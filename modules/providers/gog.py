"""
GOG provider (games supplement).
Search: GOGDB HTML scrape (gogdb.org) — no API key, good relevance.
Details: GOG v2 API (api.gog.com/v2/games/{id}) — no auth required.
No genres available from these endpoints — rely on primary provider for that.
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

_GOGDB_BASE = 'https://www.gogdb.org'
_GOG_V2     = 'https://api.gog.com/v2/games'


class GOGProvider(MetadataProvider):
    """Games metadata from GOG (via GOGDB search + GOG v2 API)."""

    def __init__(self, api_config: dict):
        super().__init__(api_config)

    def authenticate(self) -> bool:
        return True

    def search(self, query: str) -> list:
        url = f'{_GOGDB_BASE}/products?search={requests.utils.quote(query)}'
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f'[GOG] Search error: {e}')
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        results = []
        table = soup.select_one('#product-table')
        if not table:
            return []

        for row in table.select('tr')[1:]:
            link = row.select_one('a[href*="/product/"]')
            if not link:
                continue
            href = link.get('href', '')
            m = re.search(r'/product/(\d+)', href)
            if not m:
                continue
            prod_id = m.group(1)

            cells = row.select('td')
            name_cell = cells[2] if len(cells) > 2 else None
            type_cell = cells[3] if len(cells) > 3 else None
            name  = name_cell.get_text(strip=True) if name_cell else ''
            ptype = type_cell.get_text(strip=True) if type_cell else ''

            # Skip DLC, extras, demo — keep Game and Package
            if ptype.lower() in ('dlc', 'extra', 'demo'):
                continue

            img = row.select_one('img')
            cover = img.get('src', '') if img else ''
            # Ensure HTTPS
            if cover.startswith('//'):
                cover = 'https:' + cover

            results.append({
                'id':        prod_id,
                'name':      name,
                'type':      ptype,
                'cover_url': cover,
            })
            if len(results) >= 8:
                break

        return results

    def get_details(self, item_id) -> dict:
        try:
            r = requests.get(f'{_GOG_V2}/{item_id}', params={'locale': 'en-US'},
                             headers=_HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[GOG] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        # Search stubs have 'name' but no 'description' — fetch v2 details
        if 'id' in raw and '_links' not in raw and '_embedded' not in raw:
            details = self.get_details(raw['id'])
            if details:
                details['_search_cover'] = raw.get('cover_url', '')
                raw = details

        # v2 API structure
        embedded = raw.get('_embedded', {})
        product  = embedded.get('product', {})
        links    = raw.get('_links', {})

        title = product.get('title', '') or ''
        if not title:
            title = raw.get('name', '')

        release_raw = product.get('globalReleaseDate', '') or ''
        year = release_raw[:4] if release_raw and release_raw[:4].isdigit() else ''

        store_url = links.get('store', {}).get('href', '') or ''

        # Cover: prefer boxArtImage (vertical box art), fall back to search thumbnail
        cover_url = links.get('boxArtImage', {}).get('href', '') or ''
        if not cover_url:
            cover_url = raw.get('_search_cover', '')

        # Description: strip HTML tags
        desc_html = raw.get('description', '') or raw.get('overview', '') or ''
        desc = re.sub(r'<[^>]+>', ' ', desc_html).strip()
        desc = re.sub(r'\s{2,}', ' ', desc)

        return {
            'name':         title,
            'year':         year,
            'rating':       '',
            'description':  desc,
            'cover_url':    cover_url,
            'genre':        '',
            'genres':       [],
            'provider_url': store_url,
            'website_url':  store_url,
            'slug':         '',
        }

    def search_and_extract(self, query: str) -> dict | None:
        results = self.search(query)
        if not results:
            return None
        details = self.get_details(results[0]['id'])
        if details:
            details['_search_cover'] = results[0].get('cover_url', '')
            return self.extract(details)
        return self.extract(results[0])
