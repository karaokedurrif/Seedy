#!/usr/bin/env python3
"""
Download all articles from carlosstro.com community to NAS.
Saves each article as a clean Markdown file.
"""
import requests, re, os, time, json, html
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
from pathlib import Path

BASE = "https://carlosstro.com"
NAS_PATH = Path(f"/run/user/{os.getuid()}/gvfs/smb-share:server=192.168.30.100,share=datos/Fran")
PROGRESS_FILE = "/tmp/stro_crawl_progress.json"

# ── Login ──
def login():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    s.cookies.set('wordpress_test_cookie', 'WP%20Cookie%20check')
    r = s.post(f"{BASE}/wp-login.php", data={
        'log': 'Fralf', 'pwd': 'epicondilitiS', 'wp-submit': 'Log In',
        'redirect_to': f'{BASE}/comunidad/', 'testcookie': '1',
    }, allow_redirects=True, timeout=15)
    if 'wp-login.php' not in r.url:
        print("✅ Login OK")
    else:
        print("❌ Login failed")
        raise SystemExit(1)
    return s

# ── Discover all article URLs ──
def discover_articles(s):
    """Find all article URLs by scanning listing pages and following links."""
    articles = set()
    visited_listings = set()
    
    SKIP_PATHS = frozenset([
        '/acceder/', '/checkout/', '/elige-tu-suscripcion/', '/aviso-legal/',
        '/politica-de-calidad-y-medio-ambiente/', '/politica-de-cookies-ue/',
        '/divulgacion-de-afiliados/', '/proteccion-de-datos/',
        '/preguntas-frecuentes-comunidad/', '/terminos-y-condiciones-de-uso/',
        '/dashboard/', '/recuperar-tu-contrasena/', '/muro-social/',
        '/grupos/', '/lo-que-usamos/', '/conocimiento/', '/articulos/',
        '/comunidad/', '/foros/', '/forum/',
    ])
    
    # Seed URLs - listing pages
    seed_pages = [
        f"{BASE}/comunidad/",
        f"{BASE}/articulos/",
        f"{BASE}/conocimiento/",
    ]
    
    # Also check paginated article listings
    for page_num in range(1, 20):
        seed_pages.append(f"{BASE}/articulos/page/{page_num}/")
        seed_pages.append(f"{BASE}/comunidad/page/{page_num}/")
    
    for listing_url in seed_pages:
        if listing_url in visited_listings:
            continue
        visited_listings.add(listing_url)
        
        try:
            r = s.get(listing_url, timeout=15)
            if r.status_code == 404:
                continue
            if "No tienes acceso" in r.text:
                continue
        except Exception:
            continue
        
        soup = BeautifulSoup(r.text, 'lxml')
        
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            full = urljoin(listing_url, href).split('#')[0].split('?')[0]
            parsed = urlparse(full)
            
            if 'carlosstro.com' not in parsed.netloc:
                continue
            if parsed.path.startswith('/wp-'):
                continue
            if parsed.path in SKIP_PATHS:
                continue
            if any(x in parsed.path for x in ['/categorias/', '/author/', '/tag/', '/page/', '/feed']):
                continue
            
            # Article paths: /slug/ with meaningful slugs
            path = parsed.path.rstrip('/')
            if path and path.count('/') == 1 and len(path) > 5:
                articles.add(full.rstrip('/') + '/')
            # Nested paths like /webinario/slug/
            elif path.count('/') == 2 and len(path) > 10:
                articles.add(full.rstrip('/') + '/')
        
        time.sleep(0.3)
    
    return articles

# ── Convert HTML article to clean Markdown ──
def html_to_markdown(soup, url):
    """Extract article content and convert to readable Markdown."""
    # Title
    title = ""
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
    
    # Find main content area - Astra theme uses div.the-content
    content = None
    for selector in ['div.the-content', 'div.entry-content', 'div.post-content',
                     'div.page-content', 'article .entry-content']:
        content = soup.select_one(selector)
        if content and len(content.get_text(strip=True)) > 100:
            break
        content = None
    
    if not content:
        # Fallback: largest div with substantial text
        all_divs = soup.find_all('div')
        candidates = [(len(d.get_text(strip=True)), d) for d in all_divs
                      if len(d.get_text(strip=True)) > 500 and not d.find('header') and not d.find('nav')]
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            # Pick a reasonable sized one (not the whole page)
            for size, div in candidates:
                classes = ' '.join(div.get('class', []))
                if any(x in classes for x in ['content', 'post', 'entry', 'article']):
                    content = div
                    break
    
    if not content:
        return None, None
    
    # Remove unwanted elements
    for tag in content.find_all(['script', 'style', 'nav', 'footer', 'aside', 'iframe']):
        tag.decompose()
    for tag in content.find_all(attrs={'class': re.compile(r'share|social|related|sidebar|newsletter|subscribe|bp-activity|comment-form', re.I)}):
        tag.decompose()
    for tag in content.find_all(id=re.compile(r'comments|respond', re.I)):
        tag.decompose()
    
    lines = []
    lines.append(f"# {title}\n")
    lines.append(f"> Fuente: {url}")
    lines.append(f"> Descargado: {time.strftime('%Y-%m-%d')}\n")
    lines.append("---\n")
    
    def process_element(elem, depth=0):
        """Recursively process HTML elements to Markdown."""
        if isinstance(elem, str):
            text = elem.strip()
            if text:
                lines.append(text)
            return
        
        if elem.name in ['script', 'style', 'nav', 'footer', 'iframe']:
            return
        
        if elem.name in ['h1', 'h2']:
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n## {text}\n")
        elif elem.name == 'h3':
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n### {text}\n")
        elif elem.name in ['h4', 'h5', 'h6']:
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n#### {text}\n")
        elif elem.name == 'p':
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
        elif elem.name in ['ul', 'ol']:
            for li in elem.find_all('li', recursive=False):
                lines.append(f"- {li.get_text(strip=True)}")
            lines.append("")
        elif elem.name == 'blockquote':
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"\n> {text}\n")
        elif elem.name == 'figure':
            img = elem.find('img')
            caption = elem.find('figcaption')
            if img:
                src = img.get('data-src', img.get('src', ''))
                cap = caption.get_text(strip=True) if caption else img.get('alt', '')
                if src:
                    lines.append(f"\n![{cap}]({src})\n")
        elif elem.name == 'img':
            src = elem.get('data-src', elem.get('src', ''))
            alt = elem.get('alt', '')
            if src and not src.startswith('data:'):
                lines.append(f"\n![{alt}]({src})\n")
        elif elem.name == 'table':
            rows = elem.find_all('tr')
            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all(['th', 'td'])]
                lines.append('| ' + ' | '.join(cells) + ' |')
            lines.append("")
        elif elem.name in ['div', 'section', 'span', 'article', 'main']:
            # Recurse into container elements
            for child in elem.children:
                process_element(child, depth + 1)
        elif elem.name == 'br':
            lines.append("")
        elif elem.name == 'hr':
            lines.append("\n---\n")
        elif elem.name == 'a':
            href = elem.get('href', '')
            text = elem.get_text(strip=True)
            if text and href:
                lines.append(f"[{text}]({href})")
        elif elem.name in ['strong', 'b', 'em', 'i']:
            text = elem.get_text(strip=True)
            if text:
                lines.append(f"**{text}**" if elem.name in ['strong', 'b'] else f"*{text}*")
        else:
            # Generic: just get text
            text = elem.get_text(strip=True)
            if text and len(text) > 20:
                lines.append(f"\n{text}\n")
    
    # Process all children of the content div
    for child in content.children:
        process_element(child)
    
    md = '\n'.join(lines)
    # Clean up excessive newlines
    md = re.sub(r'\n{4,}', '\n\n\n', md)
    # Remove empty lines between list items
    md = re.sub(r'(^- .+)\n\n(^- )', r'\1\n\2', md, flags=re.MULTILINE)
    
    return title, md

# ── Safe filename ──
def safe_filename(title, url):
    """Create a safe filename from article title."""
    if not title:
        title = urlparse(url).path.strip('/').replace('/', '_')
    # Clean up
    name = re.sub(r'[<>:"/\\|?*]', '', title)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > 100:
        name = name[:100]
    return f"{name}.md"

# ── Main ──
def main():
    # Load progress
    done = set()
    if os.path.exists(PROGRESS_FILE):
        done = set(json.loads(open(PROGRESS_FILE).read()))
        print(f"Progreso anterior: {len(done)} artículos ya descargados")
    
    # Setup
    NAS_PATH.mkdir(parents=True, exist_ok=True)
    s = login()
    
    # Discover via WP REST API (gets ALL posts)
    print("\nDescubriendo artículos via WP REST API...")
    article_urls = set()
    page = 1
    while True:
        r = s.get(f"{BASE}/wp-json/wp/v2/posts?per_page=100&page={page}&status=publish", timeout=15)
        if r.status_code != 200:
            break
        posts = r.json()
        if not posts:
            break
        for p in posts:
            link = p.get('link', '')
            if link:
                article_urls.add(link.rstrip('/') + '/')
        page += 1
    
    # Also add URLs from crawl discovery
    crawl_urls = discover_articles(s)
    article_urls |= crawl_urls
    
    print(f"Artículos encontrados: {len(article_urls)} ({len(article_urls) - len(crawl_urls)} via API, {len(crawl_urls)} via crawl)")
    
    # Filter already done
    pending = sorted(article_urls - done)
    print(f"Pendientes: {len(pending)}")
    
    # Download each article
    saved = 0
    errors = 0
    for i, url in enumerate(pending):
        path = urlparse(url).path
        try:
            r = s.get(url, timeout=15)
            
            if r.status_code == 404:
                print(f"  [{i+1}/{len(pending)}] 404: {path}")
                done.add(url)
                continue
            
            if "No tienes acceso" in r.text:
                print(f"  [{i+1}/{len(pending)}] 🔒 Restringido: {path}")
                done.add(url)
                continue
            
            soup = BeautifulSoup(r.text, 'lxml')
            title, md = html_to_markdown(soup, url)
            
            if not md or len(md) < 100:
                print(f"  [{i+1}/{len(pending)}] ⏭ Sin contenido útil: {path}")
                done.add(url)
                continue
            
            filename = safe_filename(title, url)
            filepath = NAS_PATH / filename
            
            filepath.write_text(md, encoding='utf-8')
            saved += 1
            print(f"  [{i+1}/{len(pending)}] ✅ {filename} ({len(md)} chars)")
            
            done.add(url)
            
            # Save progress
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(list(done), f)
            
            time.sleep(0.5)  # Be polite
            
        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(pending)}] ❌ Error {path}: {e}")
    
    # Also save the HTML versions for completeness
    print(f"\n{'='*60}")
    print(f"✅ Descarga completada: {saved} artículos guardados en {NAS_PATH}")
    print(f"   Errores: {errors}")
    print(f"   Total en NAS:")
    for f in sorted(NAS_PATH.iterdir()):
        if f.is_file():
            print(f"   📄 {f.name} ({f.stat().st_size / 1024:.1f} KB)")

if __name__ == '__main__':
    main()
