# Media Manager — TODO

## Status: Initial build complete — NOT YET TESTED

## Architecture
- Plugin-based: each media type (games/movies/books/comics/music) is a MediaPlugin subclass
- Provider-based: each API is a MetadataProvider subclass
- Per-library JSON config in config/libraries/
- GUI only (no CLI), PyQt6

## Pending: User Testing
- [ ] Launch `media_manager.py` — verify window opens, library switcher works
- [ ] Test library switching (games → movies → books etc.)
- [ ] Test Process page: Scan, Metadata, Organizer, HTML buttons
- [ ] Test Dashboard wizards (New Items, Refresh DB)
- [ ] Test Library browser page (table load, filter, sort, column resize)
- [ ] Test Failed Items dialog
- [ ] Test HTML Open button on dashboard
- [ ] Test theme switching

## Pending: API Keys
User must fill in `config/libraries/*.json` with real API keys:
- games.json    → igdb client_id/client_secret, rawg api_key
- movies.json   → tmdb api_key, omdb api_key
- books.json    → google_books api_key (optional)
- comics.json   → comic_vine api_key
- music.json    → no keys needed (MusicBrainz is open)

## Pending: Genre Files
Create per-library genre files if needed:
- config/libraries/games_genres.json
- config/libraries/movies_genres.json
- etc.

## Known Issues / To Investigate
- library_browser.py genre filter: uses mixed proxy+manual hide approach — may need cleanup after testing
- MusicBrainz cover art: slow (extra HTTP call per album) — may want to make optional

## Mistakes / Notes
- LibraryConfig originally took media_type only; updated to accept path-or-type
- GlobalConfig needed set_active_library() / set_theme() methods that auto-save
- base_metadata_processor.py was missing (workers imported it but it didn't exist)
