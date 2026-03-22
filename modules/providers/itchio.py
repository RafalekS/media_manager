"""
itch.io provider (games supplement).
Docs: https://itch.io/docs/api/serverside
Auth: Bearer token in Authorization header.
Falls back to authenticated web search for adult games excluded from the public API.
Web search uses session cookie (itchio_token) for adult content visibility.
"""

import difflib
import re
import requests
from urllib.parse import unquote
from modules.core.base_metadata import MetadataProvider


class ItchIOProvider(MetadataProvider):
    """Supplemental games metadata from itch.io."""

    _API_URL = 'https://itch.io/api/1'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key        = api_config.get('itch_api_key', '')
        # URL-decode cookie — config stores it URL-encoded as copied from browser devtools
        raw_cookie           = api_config.get('itch_session_cookie', '')
        self._session_cookie = unquote(raw_cookie) if raw_cookie else ''

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str) -> list:
        if not self._api_key:
            return []
        results = self._api_search(query)
        if not results:
            results = self._web_search(query)
        return results

    def _api_search(self, query: str) -> list:
        try:
            r = requests.get(
                f'{self._API_URL}/{self._api_key}/search/games',
                params={'query': query},
                headers={'Authorization': f'Bearer {self._api_key}'},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('games') or []
        except Exception as e:
            print(f'[itch.io] API search error: {e}')
            return []

    def _web_search(self, query: str) -> list:
        """Authenticated web search for adult games excluded from the public API.
        Extracts all unique itch.io game URLs independently (no ID pairing),
        matches by URL slug, then fetches metadata via Open Graph tags.
        Searches page 1 and page 2 to improve coverage."""
        try:
            base_kwargs = {
                'headers': {'User-Agent': 'Mozilla/5.0 (compatible)'},
                'timeout': 15,
            }
            if self._session_cookie:
                base_kwargs['cookies'] = {'itchio_token': self._session_cookie}
            else:
                base_kwargs['headers']['Authorization'] = f'Bearer {self._api_key}'

            q_slug = query.lower().strip().replace(' ', '-')
            seen, urls = set(), []

            for page in (1, 2):
                params = {'q': query, 'page': page}
                r = requests.get('https://itch.io/search', params=params, **base_kwargs)
                r.raise_for_status()

                page_urls = []
                for url in re.findall(r'href="(https://[^"]+\.itch\.io/[^"#?]+)"', r.text):
                    url = url.rstrip('/')
                    parts = url.split('/')
                    if len(parts) == 4 and url not in seen:
                        seen.add(url)
                        page_urls.append(url)
                        urls.append(url)

                print(f'[itch.io] page {page}: {len(page_urls)} new game URLs')

                # Stop early if exact slug match found on this page
                if any(u.split('/')[-1].lower() == q_slug for u in page_urls):
                    break

            if not urls:
                print('[itch.io] web search: no game URLs found')
                return []

            print(f'[itch.io] web search: {len(urls)} total game URLs')

            best_url   = urls[0]
            best_slug  = urls[0].split('/')[-1].lower()
            best_score = -1.0

            for url in urls:
                slug = url.split('/')[-1].lower()
                if slug == q_slug:
                    best_url, best_slug, best_score = url, slug, 1.0
                    break
                score = difflib.SequenceMatcher(None, q_slug, slug).ratio()
                if score > best_score:
                    best_score = score
                    best_url, best_slug = url, slug

            print(f'[itch.io] best match: slug="{best_slug}" url={best_url} score={best_score:.2f}')

            if best_score < 0.6:
                print('[itch.io] score below threshold — no match')
                return []

            game = self._fetch_from_page(best_url)
            return [game] if game else []
        except Exception as e:
            print(f'[itch.io] web search error: {e}')
            return []

    def _fetch_from_page(self, game_url: str) -> dict | None:
        """Fetch game metadata from its itch.io page via Open Graph tags."""
        try:
            req_kwargs = {
                'headers': {'User-Agent': 'Mozilla/5.0 (compatible)'},
                'timeout': 10,
            }
            if self._session_cookie:
                req_kwargs['cookies'] = {'itchio_token': self._session_cookie}

            r = requests.get(game_url, **req_kwargs)
            r.raise_for_status()
            html = r.text

            def og(prop):
                m = re.search(
                    rf'<meta[^>]+property=["\']og:{prop}["\'][^>]+content=["\']([^"\']*)["\']',
                    html, re.IGNORECASE,
                )
                if not m:
                    m = re.search(
                        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']og:{prop}["\']',
                        html, re.IGNORECASE,
                    )
                return m.group(1).strip() if m else ''

            title       = og('title')
            description = og('description')
            image       = og('image')

            # Fallback title from <title> tag
            if not title:
                m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                title = m.group(1).split(' by ')[0].strip() if m else ''

            if not title:
                # Last resort: derive from slug
                slug  = game_url.split('/')[-1]
                title = slug.replace('-', ' ').title()

            return {
                'title':        title,
                'short_text':   description,
                'cover_url':    image,
                'url':          game_url,
                'published_at': '',
            }
        except Exception as e:
            print(f'[itch.io] page fetch error: {e}')
            return None

    def get_details(self, item_id) -> dict:
        return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        year = ''
        published = raw.get('published_at', '') or ''
        if published:
            year = published[:4]

        cover = raw.get('cover_url', '') or ''
        if cover.startswith('//'):
            cover = 'https:' + cover

        return {
            'name':         raw.get('title', ''),
            'year':         year,
            'rating':       '',
            'description':  raw.get('short_text', '') or '',
            'cover_url':    cover,
            'genre':        '',
            'genres':       [],
            'provider_url': raw.get('url', ''),
            'website_url':  raw.get('url', ''),
            'slug':         '',
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(self._pick_best_match(query, results, name_key='title'))

    def _pick_best_match(self, query: str, results: list, name_key: str = 'name') -> dict:
        q = query.lower().strip()
        for r in results:
            if r.get(name_key, '').lower().strip() == q:
                return r
        best = results[0]
        best_score = -1.0
        for r in results:
            name = r.get(name_key, '').lower().strip()
            score = difflib.SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best_score = score
                best = r
        return best
