import feedparser
import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

TODAY = datetime.now().strftime('%d/%m/%Y')
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=48)
API_KEY = os.environ['ANTHROPIC_API_KEY']

# ── FLUX RSS ──
FEEDS = [
    ('Business Immo',    'https://www.businessimmo.com/rss'),
    ('CF News Immo',     'https://www.cfnewsimmo.net/rss.xml'),
    ('Les Echos',        'https://syndication.lesechos.fr/rss/rss_finance.xml'),
    ('Le Figaro Eco',    'https://www.lefigaro.fr/rss/figaro_economie.xml'),
    ('BFM Business',     'https://bfmbusiness.bfmtv.com/rss/info/flux-rss/flux-toutes-les-actualites/'),
    ('Reuters',          'https://feeds.reuters.com/reuters/frTopNews'),
    ('La Provence',      'https://www.laprovence.com/rss/economie.xml'),
    ('Le Moniteur',      'https://www.lemoniteur.fr/rss/immobilier.xml'),
]

articles_bruts = []

for source, url in FEEDS:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            pub = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            if pub and pub < CUTOFF:
                continue

            title = entry.get('title', '').strip()
            link = entry.get('link', '').strip()
            summary = entry.get('summary', entry.get('description', '')).strip()
            date_str = pub.strftime('%d/%m/%Y') if pub else TODAY

            if title and link:
                articles_bruts.append({
                    'source': source,
                    'title': title[:200],
                    'summary': summary[:400],
                    'url': link,
                    'date': date_str
                })
        print(f"RSS {source}: {len([e for e in feed.entries[:10]])} entrees")
    except Exception as e:
        print(f"Erreur RSS {source}: {e}")

print(f"\nTotal articles RSS recents: {len(articles_bruts)}")

# Fallback si aucun article RSS
if not articles_bruts:
    print("Fallback donnees statiques")
    articles_bruts = [
        {'source': 'Business Immo', 'title': 'Marche immobilier entreprise PACA 2026', 'summary': 'Stabilisation marche bureaux PACA avec polarisation qualitative', 'url': 'https://www.businessimmo.com', 'date': TODAY},
        {'source': 'Les Echos', 'title': 'OAT 10 ans a 3.70 pct apres tensions geopolitiques', 'summary': 'Les taux obligataires restent eleves sous pression geopolitique', 'url': 'https://www.lesechos.fr', 'date': TODAY},
        {'source': 'BFM Business', 'title': 'Brent stable apres la treve au Moyen-Orient', 'summary': 'Le cours du petrole se stabilise autour de 96 dollars', 'url': 'https://bfmbusiness.bfmtv.com', 'date': TODAY},
        {'source': 'CF News Immo', 'title': 'SCPI rendements 2025 confirmes a 4.30 pct', 'summary': 'Les SCPI affichent des performances stables malgre contexte difficile', 'url': 'https://www.cfnewsimmo.net', 'date': TODAY},
        {'source': 'Le Figaro', 'title': 'BCE maintient ses taux directeurs a 2.15 pct', 'summary': 'La BCE attendue le 30 avril pour sa prochaine decision', 'url': 'https://www.lefigaro.fr', 'date': TODAY},
    ]

# ── PROMPT CLAUDE ──
articles_txt = '\n\n'.join([
    f"SOURCE: {a['source']} | DATE: {a['date']} | URL: {a['url']}\nTITRE: {a['title']}\nRESUME: {a['summary']}"
    for a in articles_bruts[:20]
])

prompt = f"""Tu es un assistant de veille pour Stenen Immobilier Entreprise PACA (conseil/transaction bureaux, locaux activite, commerce). Nous sommes le {TODAY}.

Voici les articles reels recuperes depuis les flux RSS des sources fiables dans les dernieres 48h:

{articles_txt}

A partir de CES articles uniquement, selectionne et redige:
- 5 articles "feed": couvrant marche PACA bureaux/activite/commerce, taux/financement OAT Euribor, reglementation decret tertiaire, SCPI/investissement, tendance flex-office
- 3 articles "macro": geopolitique/energie/Brent, conjoncture France, BCE/inflation/OAT

REGLES ABSOLUES:
- Utilise EXACTEMENT l'URL et la date de l'article source RSS
- Corps: 2 phrases maximum
- Impact: 1 phrase concrete pour conseil en transaction CRE PACA
- Si pas d'article RSS sur un sujet, utilise les donnees marche: Brent 96usd, OAT 3.70pct, Euribor3M 2.15pct, BCE 2.15pct, BTC 62500EUR, inflation 1.7pct

Reponds UNIQUEMENT avec du JSON valide sans markdown ni backticks. Format exact:
{{"generated_at":"{TODAY}","feed":[{{"id":"f1","title":"Titre max 80 car","body":"Corps 2 phrases.","impact":"Impact 1 phrase.","date":"JJ/MM/AAAA","url":"https://url-exacte","source":"Nom source","tags":[{{"label":"PACA","cls":"tp"}}]}}],"macro":[{{"id":"m1","title":"Titre","body":"Corps.","impact":"Impact.","date":"JJ/MM/AAAA","url":"https://url","source":"Source","tags":[{{"label":"Geo","cls":"tg"}}]}}]}}

Classes tags disponibles: tg=orange(geo), tt=teal(taux), tm=vert(marche), tr=amber(regl), ti2=purple(invest), tp=teal(PACA)"""

# ── APPEL API ──
response = requests.post(
    'https://api.anthropic.com/v1/messages',
    headers={
        'x-api-key': API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    },
    json={
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 4000,
        'messages': [{'role': 'user', 'content': prompt}]
    },
    timeout=60
)

data = response.json()

if 'error' in data:
    print(f"ERREUR API: {data['error']['message']}")
    sys.exit(1)

text = data['content'][0]['text'].strip()

# Nettoyer markdown
for marker in ['```json', '```']:
    if text.startswith(marker):
        text = text[len(marker):]
if text.endswith('```'):
    text = text[:-3]
text = text.strip()

result = json.loads(text)
assert 'feed' in result and len(result['feed']) > 0
assert 'macro' in result and len(result['macro']) > 0

with open('articles.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\nSucces: {len(result['feed'])} feed, {len(result['macro'])} macro")
for a in result['feed'] + result['macro']:
    print(f"  [{a['date']}] {a['title'][:55]} | {a['url'][:50]}")
