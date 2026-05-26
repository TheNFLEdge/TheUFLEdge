import os
import re
from bs4 import BeautifulSoup

ROOT_DIR = '.'
PAGES_DIR = 'pages'
ARCHIVE_FILE = os.path.join(PAGES_DIR, '26_UFLArch.htm')

WEEK_FILE_PATTERN = re.compile(r'UFLWk(\d+)\.htm$', re.IGNORECASE)
FINAL_WEEK_FILE_PATTERN = re.compile(r'UFLWk(\d+)F\.htm$', re.IGNORECASE)
ARCHIVE_LINK_PATTERNS = [
    re.compile(r'UFLWk(\d+)F\.htm', re.IGNORECASE),
    re.compile(r'UFL26-(\d+)\.htm', re.IGNORECASE),
    re.compile(r'UFLWk(\d+)\.htm', re.IGNORECASE),
]


def detect_active_week(root_dir=ROOT_DIR):
    """Detects the current active week from root templates and fallback pages."""
    weeks = []

    for name in os.listdir(root_dir):
        match = WEEK_FILE_PATTERN.match(name)
        if match:
            weeks.append(int(match.group(1)))

    if weeks:
        return max(weeks)

    if os.path.exists(PAGES_DIR):
        for name in os.listdir(PAGES_DIR):
            match = FINAL_WEEK_FILE_PATTERN.match(name)
            if match:
                weeks.append(int(match.group(1)))

    return max(weeks) if weeks else None


def find_final_page_for_week(week_num):
    """Returns the final page path for a given week if it exists."""
    if not os.path.exists(PAGES_DIR):
        return None

    for name in os.listdir(PAGES_DIR):
        match = FINAL_WEEK_FILE_PATTERN.match(name)
        if match and int(match.group(1)) == week_num:
            return os.path.join(PAGES_DIR, name)
    return None


def extract_score_pair(card, label):
    label_node = card.find(string=re.compile(fr'^{re.escape(label)}', re.IGNORECASE))
    if not label_node:
        return None, None, None

    label_td = label_node.find_parent('td')
    if not label_td or label_td.name != 'td':
        return None, None, None

    value_td = label_td.find_next_sibling('td')
    if not value_td:
        return None, None, None

    value_text = value_td.get_text(' ', strip=True)
    if not value_text:
        return None, None, value_text

    if 'TBD' in value_text.upper() or 'FINAL-SCORE' in value_text.upper():
        return None, None, value_text

    numbers = re.findall(r'-?\d+', value_text)
    if len(numbers) < 2:
        return None, None, value_text

    return int(numbers[0]), int(numbers[1]), value_text


def extract_spread(header_text):
    match = re.search(r'([+-]\d+\.?\d*)', header_text)
    return float(match.group(1)) if match else 0.0


def classify_card(card):
    proj_away, proj_home, proj_text = extract_score_pair(card, 'Projected Score')
    final_away, final_home, final_text = extract_score_pair(card, 'Final Score')

    if proj_away is None or proj_home is None:
        return None, f'Missing projected score: {proj_text}'
    if final_away is None or final_home is None:
        return None, f'Missing final score: {final_text}'

    proj_margin = proj_home - proj_away
    final_margin = final_home - final_away
    proj_winner = 'home' if proj_margin > 0 else 'away' if proj_margin < 0 else 'push'
    final_winner = 'home' if final_margin > 0 else 'away' if final_margin < 0 else 'push'

    header_tag = card.find('h4')
    spread = 0.0
    if header_tag:
        spread = extract_spread(header_tag.get_text(' ', strip=True))

    home_covers = (final_home - final_away + spread) > 0
    away_covers = not home_covers
    projected_cover = home_covers if proj_winner == 'home' else away_covers

    is_winner = (
        proj_winner != 'push'
        and final_winner == proj_winner
        and abs(final_margin) > abs(proj_margin)
    )

    if is_winner:
        return 'winner', None
    if projected_cover:
        return 'cover', None
    return 'loss', None


def parse_issue(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    game_cards = soup.find_all('div', class_='game-card')
    if not game_cards:
        raise ValueError(f'No game cards found in {html_path}')

    counts = {'winner': 0, 'cover': 0, 'loss': 0}
    errors = []

    for index, card in enumerate(game_cards, start=1):
        category, error = classify_card(card)
        if error:
            errors.append(f'Card #{index}: {error}')
            continue
        counts[category] += 1

    if errors:
        raise ValueError('Final scores are not fully populated: ' + '; '.join(errors))

    return counts['winner'], counts['cover'], counts['loss']


def parse_week_from_href(href):
    for pattern in ARCHIVE_LINK_PATTERNS:
        match = pattern.search(href)
        if match:
            return int(match.group(1))
    return None


def get_already_tabulated_weeks(archive_path):
    if not os.path.exists(archive_path):
        return set()

    with open(archive_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    weeks = set()
    for link in soup.find_all('a', href=True):
        week = parse_week_from_href(link['href'])
        if week is not None:
            weeks.add(week)
            continue
        match = re.search(r'Week\s*#(\d+)', link.get_text(strip=True), re.IGNORECASE)
        if match:
            weeks.add(int(match.group(1)))
    return weeks


def create_archive_row(issue_number, w, l, ats_w, ats_l):
    win_pct = f"{(w / (w + l)) * 100:.2f}%" if (w + l) > 0 else '0.00%'
    ats_pct = f"{(ats_w / (ats_w + ats_l)) * 100:.2f}%" if (ats_w + ats_l) > 0 else '0.00%'

    row_html = (
        f'<tr>'
        f'<td><a href="UFLWk{issue_number}F.htm">Week #{issue_number}</a></td>'
        f'<td>{w}-{l}</td>'
        f'<td class="percent">{win_pct}</td>'
        f'<td>{ats_w}-{ats_l}</td>'
        f'<td class="percent">{ats_pct}</td>'
        f'</tr>'
    )
    tr = BeautifulSoup(row_html, 'html.parser').tr
    # Decorate Winners cell when winners outnumber losses
    try:
        tds = tr.find_all('td')
        if len(tds) >= 2 and w > 0:
            existing = tds[1].get('class') or []
            # avoid duplicating the class
            if 'status-win' not in existing:
                tds[1]['class'] = existing + ['status-win']
    except Exception:
        pass

    return tr


def update_season_totals(table):
    rows = table.find_all('tr')
    totals_row = None
    winner_sum = loss_sum = cover_sum = ats_loss_sum = 0

    for tr in rows:
        if 'season-total' in (tr.get('class') or []):
            totals_row = tr
            continue
        if tr.find('th'):
            continue

        cells = tr.find_all('td')
        if len(cells) < 5:
            continue

        winner_nums = re.findall(r'(\d+)', cells[1].get_text(strip=True))
        ats_nums = re.findall(r'(\d+)', cells[3].get_text(strip=True))
        if len(winner_nums) == 2:
            winner_sum += int(winner_nums[0])
            loss_sum += int(winner_nums[1])
        if len(ats_nums) == 2:
            cover_sum += int(ats_nums[0])
            ats_loss_sum += int(ats_nums[1])

    if totals_row:
        cells = totals_row.find_all('td')
        if len(cells) >= 5:
            cells[1].string = f'{winner_sum}-{loss_sum}'
            cells[2].string = f'{(winner_sum / (winner_sum + loss_sum) * 100):.2f}%' if winner_sum + loss_sum > 0 else '0.00%'
            cells[3].string = f'{cover_sum}-{ats_loss_sum}'
            cells[4].string = f'{(cover_sum / (cover_sum + ats_loss_sum) * 100):.2f}%' if cover_sum + ats_loss_sum > 0 else '0.00%'


def upsert_archive_row(archive_path, issue_number, w, l, ats_w, ats_l):
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f'Archive file not found: {archive_path}')

    with open(archive_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    table = soup.find('table')
    if not table:
        raise ValueError(f'No table found in archive file: {archive_path}')

    new_row = create_archive_row(issue_number, w, l, ats_w, ats_l)
    seen_weeks = set()
    replacement_done = False
    rows_to_keep = []
    season_total_row = None

    for tr in table.find_all('tr'):
        if tr.find('th'):
            rows_to_keep.append(tr)
            continue

        if 'season-total' in (tr.get('class') or []):
            season_total_row = tr
            continue

        week = None
        link = tr.find('a', href=True)
        if link:
            week = parse_week_from_href(link['href'])
            if week is None:
                match = re.search(r'Week\s*#(\d+)', link.get_text(strip=True), re.IGNORECASE)
                week = int(match.group(1)) if match else None

        if week == issue_number:
            if not replacement_done:
                rows_to_keep.append(new_row)
                seen_weeks.add(issue_number)
                replacement_done = True
            continue

        if week is not None:
            if week in seen_weeks:
                continue
            seen_weeks.add(week)

        rows_to_keep.append(tr)

    if not replacement_done:
        if season_total_row:
            season_total_row.insert_before(new_row)
        else:
            rows_to_keep.append(new_row)

    table.clear()
    for tr in rows_to_keep:
        table.append(tr)
    if season_total_row:
        table.append(season_total_row)

    update_season_totals(table)

    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

    print(f'✅ Archive updated for Week #{issue_number} (W={w}, Cover={ats_w}, Loss={ats_l})')


def validate_final_page(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    game_cards = soup.find_all('div', class_='game-card')
    if not game_cards:
        raise ValueError(f'No game cards found in final week page: {html_path}')

    missing = []
    for index, card in enumerate(game_cards, start=1):
        _, _, final_text = extract_score_pair(card, 'Final Score')
        if final_text is None or 'TBD' in final_text.upper() or 'FINAL-SCORE' in final_text.upper():
            header = card.find('h4').get_text(' ', strip=True) if card.find('h4') else f'Card #{index}'
            missing.append(header)

    if missing:
        raise ValueError('Not all final scores are populated for current week. Incomplete cards: ' + '; '.join(missing))

    return True


def main():
    if not os.path.exists(PAGES_DIR):
        print(f"❌ Pages directory not found: {PAGES_DIR}")
        return

    active_week = detect_active_week(ROOT_DIR)
    if active_week is None:
        print('❌ Unable to determine active week from root or pages directory.')
        return

    print(f'📌 Active week detected: {active_week}')

    final_page = find_final_page_for_week(active_week)
    if not final_page:
        print(f'❌ Final page not found for week {active_week}. Expected under {PAGES_DIR}/UFLWk{active_week}F.htm')
        return

    print(f'🔎 Validating final scores in {final_page}...')
    try:
        validate_final_page(final_page)
    except Exception as e:
        print(f'❌ Validation failed: {e}')
        return

    print('✅ Final scores confirmed. Parsing final page...')
    try:
        winners, covers, losses = parse_issue(final_page)
    except Exception as e:
        print(f'❌ Failed to parse final page: {e}')
        return

    total_games = winners + covers + losses
    print(f'📊 Current week summary: Winner={winners}, Cover={covers}, Loss={losses}, Total={total_games}')

    existing_weeks = get_already_tabulated_weeks(ARCHIVE_FILE)
    print(f'📚 Weeks already tabulated in archive: {sorted(existing_weeks) if existing_weeks else []}')

    try:
        upsert_archive_row(
            ARCHIVE_FILE,
            active_week,
            winners,
            total_games - winners,
            covers,
            total_games - covers,
        )
    except Exception as e:
        print(f'❌ Failed to update archive file: {e}')
        return

    print('✅ Archiver completed successfully.')

if __name__ == '__main__':
    main()
