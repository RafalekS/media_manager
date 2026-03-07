"""
Generic dynamic single-page HTML generator.

Works for any media type. Column layout is driven by the plugin's column definitions.
Data is embedded in the HTML — no CORS issues when opened via file://.
"""

import json
from pathlib import Path

from modules.core.utils import scan_organized_items, enrich_with_metadata
from modules.core.config_manager import LibraryConfig


class DynamicHTMLGenerator:

    def __init__(self, lib_config: LibraryConfig, plugin):
        self.lib_config = lib_config
        self.plugin = plugin

    def generate(self) -> bool:
        print(f'Generating {self.plugin.name} HTML database...')

        organized = scan_organized_items(str(self.lib_config.destination_base))
        if not organized:
            print('[ERROR] No organized items found.')
            return False

        enriched = enrich_with_metadata(organized, self.lib_config.metadata_file)

        flat = []
        for genre, items in enriched.items():
            for item in items:
                entry = {
                    'folder_name':   item['name'],
                    'display_name':  item.get('display_name', item['name']),
                    'genre':         item['genre'],
                    'year':          item.get('year', 'Unknown'),
                    'rating':        item.get('rating', 0),
                    'description':   item.get('description', 'No description available'),
                    'cover_url':     item.get('cover_url', ''),
                    'provider_url':  item.get('provider_url', ''),
                    'website_url':   item.get('website_url', ''),
                    'folder_path':   item['folder_path'].replace('\\', '/'),
                }
                flat.append(entry)

        flat.sort(key=lambda x: x['display_name'].lower())
        genres = sorted(enriched.keys())

        out_path = self.lib_config.html_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(self._build_html(flat, genres))

        print(f'[OK] HTML written to: {out_path}')
        print(f'[INFO] {len(flat)} items, {len(genres)} genres')
        return True

    # ── HTML template ─────────────────────────────────────────────────────

    def _build_html(self, items: list, genres: list) -> str:
        items_json = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
        genre_options = ''.join(f'<option value="{g}">{g}</option>' for g in genres)
        title = f'{self.plugin.name} Database'

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:'Segoe UI',sans-serif; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); min-height:100vh; padding:20px; }}
        .container {{ max-width:1600px; margin:0 auto; background:rgba(255,255,255,0.95); border-radius:15px; padding:30px; box-shadow:0 20px 40px rgba(0,0,0,0.1); }}
        .header {{ text-align:center; margin-bottom:30px; border-bottom:3px solid #667eea; padding-bottom:20px; }}
        .header h1 {{ color:#333; font-size:2.5em; margin-bottom:10px; }}
        .stats {{ color:#666; font-size:1.1em; }}
        .controls {{ display:flex; flex-wrap:wrap; gap:15px; margin-bottom:25px; padding:20px; background:#f8f9fa; border-radius:10px; }}
        .search-box, .filter-select {{ padding:10px 15px; border:2px solid #ddd; border-radius:8px; font-size:16px; }}
        .search-box {{ flex:1; min-width:250px; }}
        .filter-select {{ min-width:150px; }}
        .pagination {{ text-align:center; margin:25px 0; display:flex; justify-content:center; gap:10px; flex-wrap:wrap; }}
        .pagination button {{ padding:10px 15px; background:#667eea; color:white; border:none; border-radius:5px; cursor:pointer; }}
        .pagination button:disabled {{ background:#ccc; cursor:not-allowed; }}
        .pagination button.current {{ background:#764ba2; }}
        .items-table {{ width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; }}
        .items-table th {{ background:#667eea; color:white; padding:15px; cursor:pointer; user-select:none; }}
        .items-table th.sortable:after {{ content:' ↕'; opacity:.5; }}
        .items-table th.sorted-asc:after {{ content:' ↑'; opacity:1; }}
        .items-table th.sorted-desc:after {{ content:' ↓'; opacity:1; }}
        .items-table td {{ padding:12px 15px; border-bottom:1px solid #eee; }}
        .item-link {{ color:#667eea; text-decoration:none; font-weight:600; }}
        .genre-tag {{ background:#e3f2fd; color:#1976d2; padding:4px 8px; border-radius:4px; font-size:.85em; }}
        .cover {{ width:50px; height:70px; object-fit:cover; border-radius:4px; transition:transform .15s; }}
        .cover:hover {{ transform:scale(1.08); }}
        .cover-link {{ display:inline-block; }}
        .no-cover {{ width:50px; height:70px; background:#ddd; border-radius:4px; display:flex; align-items:center; justify-content:center; font-size:.7em; color:#999; text-align:center; }}
        .icon-links {{ display:flex; gap:6px; align-items:center; }}
        .icon-link {{ display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:6px; text-decoration:none; transition:opacity .15s; }}
        .icon-link:hover {{ opacity:.75; }}
        .icon-provider {{ background:#4f46e5; }}
        .icon-web {{ background:#0ea5e9; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="stats" id="statsDisplay">Loading...</div>
        </div>
        <div class="controls">
            <input type="text" class="search-box" placeholder="Search {self.plugin.name.lower()}..." id="searchBox">
            <select class="filter-select" id="genreFilter">
                <option value="">All Genres</option>
                {genre_options}
            </select>
            <select class="filter-select" id="perPageSelect">
                <option value="50" selected>50 per page</option>
                <option value="100">100 per page</option>
                <option value="all">Show All</option>
            </select>
        </div>
        <div class="pagination" id="topPagination"></div>
        <table class="items-table" id="itemsTable" style="display:none;">
            <thead>
                <tr>
                    <th>Cover</th>
                    <th class="sortable" data-sort="display_name">Name</th>
                    <th class="sortable" data-sort="genre">Genre</th>
                    <th class="sortable" data-sort="year">Year</th>
                    <th class="sortable" data-sort="rating">Rating</th>
                    <th>Description</th>
                    <th>Links</th>
                </tr>
            </thead>
            <tbody id="itemsTableBody"></tbody>
        </table>
        <div class="pagination" id="bottomPagination"></div>
    </div>
    <script>
        const ITEMS_DATA = {items_json};

        let allItems=[], filteredItems=[], currentPage=1, perPage=50;
        let sortState={{field:'display_name', dir:'asc'}};

        function saveState() {{
            try {{
                sessionStorage.setItem('mm_search', document.getElementById('searchBox').value);
                sessionStorage.setItem('mm_genre', document.getElementById('genreFilter').value);
                sessionStorage.setItem('mm_perpage', document.getElementById('perPageSelect').value);
            }} catch(e) {{}}
        }}

        function restoreState() {{
            try {{
                const s = sessionStorage.getItem('mm_search');
                const g = sessionStorage.getItem('mm_genre');
                const p = sessionStorage.getItem('mm_perpage');
                if (s) document.getElementById('searchBox').value = s;
                if (g) document.getElementById('genreFilter').value = g;
                if (p) {{
                    document.getElementById('perPageSelect').value = p;
                    perPage = p === 'all' ? 'all' : parseInt(p);
                }}
            }} catch(e) {{}}
        }}

        function init() {{
            allItems = ITEMS_DATA;
            filteredItems = [...allItems];
            restoreState();
            updateStats();
            applySort(sortState.field, false);
            applyFilter();
            document.getElementById('itemsTable').style.display = 'table';
        }}

        function updateStats() {{
            document.getElementById('statsDisplay').textContent =
                filteredItems.length + ' of ' + allItems.length + ' {self.plugin.name.lower()}';
        }}

        function applySort(field, toggle=true) {{
            if (toggle && sortState.field === field) {{
                sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
            }} else if (toggle) {{
                sortState.field = field; sortState.dir = 'asc';
            }}
            filteredItems.sort((a, b) => {{
                let av = a[field], bv = b[field];
                if (field === 'rating') {{ av = parseFloat(av)||0; bv = parseFloat(bv)||0; }}
                else if (field === 'year') {{ av = av==='Unknown'?9999:parseInt(av)||9999; bv = bv==='Unknown'?9999:parseInt(bv)||9999; }}
                else {{ av = String(av).toLowerCase(); bv = String(bv).toLowerCase(); }}
                if (av < bv) return sortState.dir==='asc' ? -1 : 1;
                if (av > bv) return sortState.dir==='asc' ? 1 : -1;
                return 0;
            }});
            document.querySelectorAll('th.sortable').forEach(th => {{
                th.className = 'sortable';
                if (th.dataset.sort === field)
                    th.classList.add(sortState.dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
            }});
            currentPage = 1;
            render();
        }}

        function applyFilter() {{
            const s = document.getElementById('searchBox').value.toLowerCase();
            const g = document.getElementById('genreFilter').value;
            filteredItems = allItems.filter(item => {{
                const ms = !s || item.display_name.toLowerCase().includes(s) ||
                           item.description.toLowerCase().includes(s);
                const mg = !g || item.genre === g;
                return ms && mg;
            }});
            saveState();
            updateStats();
            currentPage = 1;
            render();
        }}

        function render() {{
            const tbody = document.getElementById('itemsTableBody');
            tbody.innerHTML = '';
            const total = perPage === 'all' ? 1 : Math.ceil(filteredItems.length / perPage);
            const start = perPage === 'all' ? 0 : (currentPage - 1) * perPage;
            const end   = perPage === 'all' ? filteredItems.length : Math.min(start + perPage, filteredItems.length);
            const page  = filteredItems.slice(start, end);

            if (!page.length) {{
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;">No items found</td></tr>';
            }} else {{
                page.forEach(item => {{
                    const row = document.createElement('tr');

                    // Cover
                    const coverTd = document.createElement('td');
                    const imgHtml = item.cover_url
                        ? '<img src="' + item.cover_url + '" class="cover">'
                        : '<div class="no-cover">No Image</div>';
                    coverTd.innerHTML = item.provider_url
                        ? '<a href="' + item.provider_url + '" target="_blank" class="cover-link">' + imgHtml + '</a>'
                        : imgHtml;
                    row.appendChild(coverTd);

                    // Name
                    const nameTd = document.createElement('td');
                    nameTd.innerHTML = '<a href="file:///' + item.folder_path + '" class="item-link">' + item.display_name + '</a>';
                    row.appendChild(nameTd);

                    // Genre
                    const genreTd = document.createElement('td');
                    genreTd.innerHTML = '<span class="genre-tag">' + item.genre + '</span>';
                    row.appendChild(genreTd);

                    // Year
                    const yearTd = document.createElement('td');
                    yearTd.textContent = item.year;
                    row.appendChild(yearTd);

                    // Rating
                    const ratingTd = document.createElement('td');
                    const r = parseFloat(item.rating) || 0;
                    ratingTd.textContent = r > 0 ? r.toFixed(1) : 'N/A';
                    row.appendChild(ratingTd);

                    // Description
                    const descTd = document.createElement('td');
                    let desc = item.description || 'No description';
                    if (desc.length > 150) desc = desc.substring(0, 150) + '...';
                    descTd.textContent = desc;
                    row.appendChild(descTd);

                    // Links
                    const linksTd = document.createElement('td');
                    let links = '<div class="icon-links">';
                    if (item.provider_url) {{
                        links += '<a href="' + item.provider_url + '" target="_blank" class="icon-link icon-provider" title="Provider">' +
                            '<svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M3 3h18v18H3V3zm2 2v14h14V5H5zm2 2h10v2H7V7zm0 4h10v2H7v-2zm0 4h7v2H7v-2z"/></svg></a>';
                    }}
                    if (item.website_url) {{
                        links += '<a href="' + item.website_url + '" target="_blank" class="icon-link icon-web" title="Website">' +
                            '<svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg></a>';
                    }}
                    links += '</div>';
                    linksTd.innerHTML = links;
                    row.appendChild(linksTd);

                    tbody.appendChild(row);
                }});
            }}
            renderPagination(total);
        }}

        function renderPagination(total) {{
            let html = '';
            if (total > 1) {{
                html += '<button onclick="goPage(' + (currentPage-1) + ')" ' + (currentPage===1?'disabled':'') + '>&laquo;</button>';
                for (let i=1; i<=total; i++)
                    html += '<button onclick="goPage(' + i + ')" ' + (i===currentPage?'class="current"':'') + '>' + i + '</button>';
                html += '<button onclick="goPage(' + (currentPage+1) + ')" ' + (currentPage===total?'disabled':'') + '>&raquo;</button>';
            }}
            document.getElementById('topPagination').innerHTML = html;
            document.getElementById('bottomPagination').innerHTML = html;
        }}

        function goPage(p) {{
            const total = perPage==='all' ? 1 : Math.ceil(filteredItems.length/perPage);
            if (p < 1 || p > total) return;
            currentPage = p;
            render();
            window.scrollTo({{top:0, behavior:'smooth'}});
        }}

        document.getElementById('searchBox').addEventListener('input', applyFilter);
        document.getElementById('genreFilter').addEventListener('change', applyFilter);
        document.getElementById('perPageSelect').addEventListener('change', function() {{
            perPage = this.value === 'all' ? 'all' : parseInt(this.value);
            currentPage = 1; saveState(); render();
        }});
        document.querySelectorAll('th.sortable').forEach(th =>
            th.addEventListener('click', function() {{ applySort(this.dataset.sort, true); }})
        );

        init();
    </script>
</body>
</html>'''
