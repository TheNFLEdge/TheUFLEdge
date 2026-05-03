import json
import os
import shutil
import re
from datetime import datetime

# ==========================================
# CONFIGURATION & FILE PATHS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE_CANDIDATES = [
    'ufl_data_handoff.json',
    'ufl_datahandoff.json',
    'ufl_data-handoff.json',
]
ACTIVE_FRAME = os.path.join(BASE_DIR, 'UFLWTmp.htm')
ARCHIVE_INDEX = os.path.join(BASE_DIR, 'ufl26_archive.htm')
HANDOVER_HOUR = 7


def find_data_file():
    for filename in DATA_FILE_CANDIDATES:
        path = os.path.join(BASE_DIR, filename)
        if os.path.exists(path):
            return path
    return None


def get_current_data():
    data_path = find_data_file()
    if not data_path:
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def parse_int(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def parse_float(value):
    if value is None:
        return None
    if isinstance(value, float):
        return value
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def is_final_status(status):
    if not status:
        return False
    text = str(status).upper()
    return 'FINAL' in text or text in ('F', 'FT')


def normalize_game(game):
    return {
        'away': game.get('away'),
        'home': game.get('home'),
        'status': game.get('status') or game.get('statusLine') or '',
        'away_score': game.get('away_score') or game.get('awayScore') or game.get('awayPoints'),
        'home_score': game.get('home_score') or game.get('homeScore') or game.get('homePoints'),
        'proj_away_score': game.get('proj_away_score') or game.get('projAwayScore'),
        'proj_home_score': game.get('proj_home_score') or game.get('projHomeScore'),
        'spread': game.get('spread') or game.get('line') or 0,
        'score': game.get('score'),
    }


def normalize_games(data):
    if isinstance(data.get('games'), list):
        return [normalize_game(game) for game in data.get('games', [])]
    if isinstance(data.get('matchups'), list):
        return [normalize_game(game) for game in data.get('matchups', [])]
    return []


def get_published_week(data):
    week = data.get('week') or data.get('target_week')
    try:
        return int(week)
    except (TypeError, ValueError):
        return 0


def detect_current_week():
    """
    Detect the actual current week by checking which week file exists and is incomplete.
    This prevents DataGen from prematurely advancing the week before all games are final.
    Search backwards from a reasonable max (e.g., 20) to find the most recent incomplete week.
    """
    for week_num in range(20, 0, -1):
        week_file = os.path.join(BASE_DIR, f"UFLWk{week_num}.htm")
        final_file = os.path.join(BASE_DIR, f"UFLWk{week_num}F.htm")
        
        # If the F file exists, this week is sealed - skip it
        if os.path.exists(final_file):
            continue
        
        # If the week file exists but no F file, this is the current incomplete week
        if os.path.exists(week_file):
            return week_num
    
    # Fallback: return what's in the handoff
    data = get_current_data()
    return get_published_week(data) if data else 0


def get_completed_week(data):
    if 'week' in data and data.get('week') is not None:
        return get_published_week(data)
    published = get_published_week(data)
    return max(1, published - 1) if published else 0


def render_score_text(game):
    away_score = parse_int(game.get('away_score'))
    home_score = parse_int(game.get('home_score'))
    if away_score is not None and home_score is not None:
        return f"{away_score} - {home_score}"
    if game.get('score'):
        return str(game['score'])
    return 'FINAL'


def replace_placeholders(html, game):
    away = game.get('away')
    home = game.get('home')
    if not away or not home:
        return html, False

    score_text = render_score_text(game)
    updated = False

    for tag in [
        f"<!--FINAL-SCORE-{away}-{home}-->",
        f"<!--FINAL-SCORE-{home}-{away}-->",
    ]:
        if tag in html:
            html = html.replace(tag, score_text)
            updated = True

    return html, updated


def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


def run_live_score_update():
    """
    Update live scores from the handoff JSON into UFLWTmp.htm and UFLWk{week}.htm.
    """
    if not os.path.exists(ACTIVE_FRAME):
        return

    data = get_current_data()
    if not data:
        return

    with open(ACTIVE_FRAME, 'r', encoding='utf-8') as f:
        html = f.read()

    updated = False
    all_final = True
    for game in normalize_games(data):
        if is_final_status(game.get('status')):
            html, changed = replace_placeholders(html, game)
            updated = updated or changed
        else:
            all_final = False

    if updated:
        with open(ACTIVE_FRAME, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[{datetime.now()}] {ACTIVE_FRAME} scores updated.")

    # Detect the actual current week (not trusting the potentially stale handoff)
    current_week = detect_current_week()
    if current_week:
        week_file = os.path.join(BASE_DIR, f"UFLWk{current_week}.htm")
        write_file(week_file, html)
        print(f"[{datetime.now()}] {week_file} scores updated.")

        # Only seal the week and advance if all games are final
        if all_final:
            final_week_file = os.path.join(BASE_DIR, f"UFLWk{current_week}F.htm")
            write_file(final_week_file, html)
            print(f"[{datetime.now()}] All week {current_week} games final. Sealed to {final_week_file}.")
            
            # Calculate and record weekly results
            su_w, su_l, ats_w, ats_l = calculate_weekly_records(data)
            update_archive_page(current_week, su_w, su_l, ats_w, ats_l)
        else:
            print(f"[{datetime.now()}] Week {current_week} still has games in progress. Waiting for all finals before archiving.")


def calculate_weekly_records(data):
    su_w = su_l = ats_w = ats_l = 0

    for game in normalize_games(data):
        if not is_final_status(game.get('status')):
            continue

        actual_home = parse_int(game.get('home_score'))
        actual_away = parse_int(game.get('away_score'))
        proj_home = parse_int(game.get('proj_home_score'))
        proj_away = parse_int(game.get('proj_away_score'))
        spread = parse_float(game.get('spread')) or 0.0

        if actual_home is None or actual_away is None or proj_home is None or proj_away is None:
            continue
        if actual_home == actual_away:
            continue

        act_winner = 'home' if actual_home > actual_away else 'away'
        proj_winner = 'home' if proj_home > proj_away else 'away'
        if act_winner == proj_winner:
            su_w += 1
        else:
            su_l += 1

        ats_margin = (actual_home + spread) - actual_away
        act_cover = 'home' if ats_margin > 0 else 'away'
        if proj_winner == act_cover:
            ats_w += 1
        else:
            ats_l += 1

    return su_w, su_l, ats_w, ats_l


def update_archive_page(week_no, su_w, su_l, ats_w, ats_l):
    if not os.path.exists(ARCHIVE_INDEX):
        print(f"Archive index not found: {ARCHIVE_INDEX}")
        return

    with open(ARCHIVE_INDEX, 'r', encoding='utf-8') as f:
        content = f.read()

    def get_total(tid):
        m = re.search(rf'id="{tid}">(\d+)</td>', content)
        return int(m.group(1)) if m else 0

    new_t_su_w = get_total('total-su-w') + su_w
    new_t_su_l = get_total('total-su-l') + su_l
    new_t_ats_w = get_total('total-ats-w') + ats_w
    new_t_ats_l = get_total('total-ats-l') + ats_l

    def pct(w, l):
        return f"{(w/(w+l)*100):.1f}%" if (w+l) > 0 else '0.0%'

    new_row = f'''
            <tr>
                <td><a href="UFLWk{week_no}F.htm" target="_blank">Week {week_no}</a></td>
                <td class="win">{su_w}</td><td class="loss">{su_l}</td><td class="pct-cell">{pct(su_w, su_l)}</td>
                <td class="win">{ats_w}</td><td class="loss">{ats_l}</td><td class="pct-cell">{pct(ats_w, ats_l)}</td>
            </tr>'''

    new_totals = f'''
            <tr class="totals-row">
                <td>2026 SEASON TOTALS</td>
                <td id="total-su-w">{new_t_su_w}</td><td id="total-su-l">{new_t_su_l}</td><td class="pct-cell">{pct(new_t_su_w, new_t_su_l)}</td>
                <td id="total-ats-w">{new_t_ats_w}</td><td id="total-ats-l">{new_t_ats_l}</td><td class="pct-cell">{pct(new_t_ats_w, new_t_ats_l)}</td>
            </tr>'''

    updated = content.replace('<!-- INSERT_NEW_ROW -->', f'<!-- INSERT_NEW_ROW -->\n{new_row}')
    updated = re.sub(r'<tr class="totals-row">.*?</tr>', new_totals, updated, flags=re.DOTALL)

    with open(ARCHIVE_INDEX, 'w', encoding='utf-8') as f:
        f.write(updated)
    print(f"Archive {ARCHIVE_INDEX} updated successfully.")


def run_tuesday_rotation():
    """
    Tuesday rotation: Process final scores and seal the week if complete.
    """
    run_live_score_update()




def main():
    now = datetime.now()
    day = now.weekday()
    hour = now.hour

    if day in [4, 5, 6]:
        run_live_score_update()
    elif day == 0 and hour == 2:
        run_live_score_update()
    elif day == 1 and hour >= HANDOVER_HOUR:
        run_tuesday_rotation()


if __name__ == '__main__':
    main()
