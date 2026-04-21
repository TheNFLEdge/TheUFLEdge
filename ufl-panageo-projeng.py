import json
import math
import os

# 1. PGVARS_Mapped to your repository variables)
P_M = {
    "1.0":  float(os.getenv('PG_PI0', 2.0)),
    "0.75": float(os.getenv('PG_PI7', 2.0)),
    "0.5":  float(os.getenv('PG_PPI5', 2.0)),
    "0.25": float(os.getenv('PG_PI2', 1.66)),
    "0.0":  float(os.getenv('PG_PI_X', 1.5))
}
M_D = float(os.getenv('PG_MD', 2.0))

def get_manual_pp4v(win_pct):
    wp = float(win_pct)
    if wp >= 0.8: return "1.0"
    if wp >= 0.6: return "0.75"
    if wp >= 0.4: return "0.5"
    if wp >= 0.2: return "0.25"
    return "0.0"

def c_pags(pf, pa, gp, pp4v, v_pf, v_pa, vgp):
    t_q = (pf / gp) / 4
    v_q = (v_pa / vgp) / 4
    p_c = P_M.get(str(pp4v), 1.0)
    b_v = (t_q + v_q) * p_c
    pp4v_f = float(pp4v)
    if pp4v_f >= 0.75: res = math.ceil(b_v + M_D)
    elif pp4v_f <= 0.25: res = math.floor(b_v - M_D)
    else: res = round(b_v)
    return res

if __name__ == "__main__":
    handoff_file = 'ufl_data_handoff.json'
    master_template = 'UFLWTmpl8.htm' 
    
    if not os.path.exists(handoff_file) or not os.path.exists(master_template):
        print("❌ Error: Missing Handoff JSON or Master Template HTML!")
        exit()

    with open(handoff_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    with open(master_template, 'r', encoding='utf-8') as f:
        final_html = f.read()
    
    stats = data['team_stats']
    week = data['target_week']
    
    # 2. GENERATE AND SLOT THE CARDS
    for index, m in enumerate(data['matchups']):
        a, h = m['away'], m['home']
        
        # Guard: Only project if data is complete
        if stats[a]['gp'] < 4 or stats[h]['gp'] < 4:
            final_html = final_html.replace(f"[SLOT_{index+1}]", f"<p>Data Pending for {a}@{h}</p>")
            continue

        # RUN SECRET SAUCE
        a_score = c_pags(stats[a]['pf_sum'], stats[a]['pa_sum'], 4, get_manual_pp4v(stats[a]['wins']/4), stats[h]['pf_sum'], stats[h]['pa_sum'], 4)
        h_score = c_pags(stats[h]['pf_sum'], stats[h]['pa_sum'], 4, get_manual_pp4v(stats[h]['wins']/4), stats[a]['pf_sum'], stats[a]['pa_sum'], 4)

        # BUILD FINISHED CARD HTML
        card_content = f"""
        <div class="game-card">
            <h4>{a} @ {h} {m['line']} {m['ou']}</h4>
            <table>
                <tr><td><b>Projected Score:</b></td><td>{a_score} – {h_score}</td></tr>
                <tr><td><b>Final Score:</b></td><td><!--FINAL-SCORE-{a}-{h}--></td></tr>
            </table>
        </div>"""

        # INJECT INTO SPECIFIC SLOT (Preserving your ad layout)
        final_html = final_html.replace(f"[SLOT_{index+1}]", card_content)

    # 3. UPDATE TRACKER TABLE & HEADER
    # Placeholder for ledger logic - hardcoded for now until we build the auto-tracker
    final_html = final_html.replace("[TOTAL_W_L]", "6 - 2")
    final_html = final_html.replace("[TOTAL_WIN_PCT]", "75")
    final_html = final_html.replace("[TOTAL_ATS_W_L]", "4 - 4")
    final_html = final_html.replace("[TOTAL_ATS_PCT]", "50")
    final_html = final_html.replace("UFL Week 3", f"UFL Week {week}")

    # 4. SAVE THE "LIVE" FRONT DOOR (Week 5)
    with open("UFLWTmp.htm", "w", encoding='utf-8') as f:
        f.write(final_html)
    
    # 5. SAVE THE "SNAPSHOT" FOR NEXT WEEK'S ARCHIVE PASS
    # This keeps the tags inside so the Archiver can find them later
    with open(f"UFLWk{week}.htm", "w", encoding='utf-8') as f:
        f.write(final_html)

    # 6. INITIALIZE THE "F" VERSION (The Skeleton for the Audit)
    completed_week = week - 1
    archive_skeleton = f"UFLWk{completed_week}F.htm"
    
    # Only copy the previous week's live file to the 'F' version if it exists
    prev_live_file = f"UFLWk{completed_week}.htm"
    if os.path.exists(prev_live_file):
        import shutil
        shutil.copy2(prev_live_file, archive_skeleton)
        print(f"📁 Archive Skeleton Created: {archive_skeleton} (Pending Audit)")
    
    print(f"🚀 Week {week} Projections are LIVE!")
