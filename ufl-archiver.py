import json
import os
import shutil
import re
from datetime import datetime

# ==========================================
# CONFIGURATION & UPDATED PATHS
# ==========================================
DATA_FILE = 'pages/ufl_datahandoff.json'      # Now in pages folder
ACTIVE_FRAME = 'pages/UFLWTmp.htm'            # Now in pages folder
ARCHIVE_INDEX = 'ufl26_archive.htm'           # Lives in root
PROJ_ENGINE = 'ufl-panageo-projeng.py'        # Root script
HANDOVER_HOUR = 7

def get_current_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {DATA_FILE}: {e}")
        return None

def run_live_score_update():
    if not os.path.exists(ACTIVE_FRAME): 
        print(f"Warning: {ACTIVE_FRAME} not found.")
        return
    data = get_current_data()
    if not data: return
    
    with open(ACTIVE_FRAME, 'r') as f:
        html = f.read()

    updated = False
    for game in data.get('games', []):
        if game.get('status') == 'FINAL':
            # Updated to match your placeholder style
            tag = f"<!--FINAL-SCORE-{game['home']}-{game['away']}-->"
            score_text = f"{game['home_score']} - {game['away_score']}"
            if tag in html:
                html = html.replace(tag, score_text)
                updated = True
    
    if updated:
        with open(ACTIVE_FRAME, 'w') as f:
            f.write(html)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {ACTIVE_FRAME} scores updated.")

def calculate_weekly_records(data):
    su_w, su_l = 0, 0
    ats_w, ats_l = 0, 0
    
    for game in data.get('games', []):
        # Ensure we only calculate for completed games
        if game.get('status') == 'FINAL':
            # Straight Up (Winners)
            act_winner = "home" if game['home_score'] > game['away_score'] else "away"
            proj_winner = "home" if game['proj_home_score'] > game['proj_away_score'] else "away"
            if act_winner == proj_winner: su_w += 1
            else: su_l += 1
            
            # Against the Spread (ATS)
            # Formula: (Home Score + Spread) vs Away Score
            ats_margin = (game['home_score'] + game['spread']) - game['away_score']
            act_cover = "home" if ats_margin > 0 else "away"
            if proj_winner == act_cover: ats_w += 1
            else: ats_l += 1
    return su_w, su_l, ats_w, ats_l

def update_archive_page(week_no, su_w, su_l, ats_w, ats_l):
    if not os.path.exists(ARCHIVE_INDEX): 
        print(f"Error: {ARCHIVE_INDEX} not found in root.")
        return

    with open(ARCHIVE_INDEX, 'r') as f:
        content = f.read()

    # Scrape totals - Fixed with Raw String (rf) to solve \d warning
    def get_total(tid):
        m = re.search(rf'id="{tid}">(\d+)</td>', content)
        return int(m.group(1)) if m else 0

    new_t_su_w = get_total("total-su-w") + su_w
    new_t_su_l = get_total("total-su-l") + su_l
    new_t_ats_w = get_total("total-ats-w") + ats_w
    new_t_ats_l = get_total("total-ats-l") + ats_l

    def pct(w, l): return f"{(w/(w+l)*100):.1f}%" if (w+l)>0 else "0.0%"

    # Link updated to point to pages/ subfolder
    new_row = f'''
            <tr>
                <td><a href="pages/UFLWk{week_no}F.htm" target="_blank">Week {week_no}</a></td>
                <td class="win">{su_w}</td><td class="loss">{su_l}</td><td class="pct-cell">{pct(su_w, su_l)}</td>
                <td class="win">{ats_w}</td><td class="loss">{ats_l}</td><td class="pct-cell">{pct(ats_w, ats_l)}</td>
            </tr>'''

    new_totals = f'''
            <tr class="totals-row">
                <td>2026 SEASON TOTALS</td>
                <td id="total-su-w">{new_t_su_w}</td><td id="total-su-l">{new_t_su_l}</td><td class="pct-cell">{pct(new_t_su_w, new_t_su_l)}</td>
                <td id="total-ats-w">{new_t_ats_w}</td><td id="total-ats-l">{new_t_ats_l}</td><td class="pct-cell">{pct(new_t_ats_w, new_t_ats_l)}</td>
            </tr>'''

    # Chronological: Appends above the marker (Top-to-Bottom)
    updated = content.replace("<!-- INSERT_NEW_ROW -->", f"{new_row}\n<!-- INSERT_NEW_ROW -->")
    updated = re.sub(r'<tr class="totals-row">.*?</tr>', new_totals, updated, flags=re.DOTALL)

    with open(ARCHIVE_INDEX, 'w') as f:
        f.write(updated)
    print(f"Archive {ARCHIVE_INDEX} updated.")

def run_tuesday_rotation():
    data = get_current_data()
    if not data: return
    week_no = data.get('week', 0)
    su_w, su_l, ats_w, ats_l = calculate_weekly_records(data)
    
    # 1. Archive current frame into pages/ folder
    final_file = f"pages/UFLWk{week_no}F.htm"
    shutil.copy(ACTIVE_FRAME, final_file)
    print(f"Archived final edition to {final_file}")
    
    # 2. Update the root archive index
    update_archive_page(week_no, su_w, su_l, ats_w, ats_l)
    
    # 3. Trigger Proj Engine in root
    print("Triggering Proj Engine for new betting lines...")
    os.system(f"python {PROJ_ENGINE}")

def main():
    now = datetime.now()
    day = now.weekday()
    hour = now.hour

    print(f"Heartbeat: {now.strftime('%A %H:%M:%S')}")

    # Fri (4), Sat (5), Sun (6)
    if day in [4, 5, 6]:
        run_live_score_update()
    # Mon 2AM
    elif day == 0 and hour == 2:
        run_live_score_update()
    # Tue 9AM+
    elif day == 1 and hour >= HANDOVER_HOUR:
        run_tuesday_rotation()
    else:
        # For testing: run live update if you run it manually mid-week
        run_live_score_update()

if __name__ == "__main__":
    main()
