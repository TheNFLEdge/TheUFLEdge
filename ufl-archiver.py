import os
import re
from bs4 import BeautifulSoup

def parse_issue(html_path):
    """Parses a specific week file to compute stats from game-card DIVs."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    game_cards = soup.find_all("div", class_="game-card")
    winners = 0
    ats_winners = 0
    total_games = 0
    
    for card in game_cards:
        total_games += 1
        
        # ==========================================
        # Extract Projected Score (with team abbr)
        # ==========================================
        # NEW FORMAT: "DC 26 – CLB 17"
        # OLD FORMAT: "26 – 17"
        proj_row = None
        for td in card.find_all("td"):
            if td.get_text(strip=True).startswith("Projected Score"):
                proj_row = td.find_next("td")
                break
        
        if not proj_row:
            continue
        
        proj_text = proj_row.get_text(strip=True)
        proj_nums = re.findall(r"\d+", proj_text)
        if len(proj_nums) < 2:
            continue
        proj_away, proj_home = int(proj_nums[0]), int(proj_nums[1])
        
        # ==========================================
        # Extract Final Score (with team abbr)
        # ==========================================
        # FORMAT: "DC 26 – CLB 17"
        final_row = None
        for td in card.find_all("td"):
            if td.get_text(strip=True).startswith("Final Score"):
                final_row = td.find_next("td")
                break
        
        if not final_row:
            continue
        
        final_text = final_row.get_text(strip=True)
        
        # Skip if still TBD or shows comment markers
        if "TBD" in final_text or "FINAL-SCORE" in final_text:
            continue
        
        final_nums = re.findall(r"\d+", final_text)
        if len(final_nums) < 2:
            continue
        final_away, final_home = int(final_nums[0]), int(final_nums[1])
        
        # ==========================================
        # Determine Straight-Up Winner
        # ==========================================
        proj_winner = "home" if proj_home > proj_away else "away"
        final_winner = "home" if final_home > final_away else "away"
        
        if proj_winner == final_winner:
            winners += 1
        
        # ==========================================
        # Determine ATS Winner (if spread exists)
        # ==========================================
        header_tag = card.find("h4")
        if header_tag:
            header = header_tag.get_text(strip=True)
            spread_match = re.search(r"([+-]\d+\.?\d*)", header)
            spread = float(spread_match.group(1)) if spread_match else 0.0
            
            # Apply spread to final home score and check if projection was correct
            adjusted_home = final_home - spread
            ats_correct = (adjusted_home > final_away)
            if ats_correct:
                ats_winners += 1
    
    losses = total_games - winners
    ats_losses = total_games - ats_winners
    return winners, losses, ats_winners, ats_losses


def get_already_tabulated_weeks(archive_path):
    """Scans the archive file to check which weeks are already added."""
    if not os.path.exists(archive_path):
        return set()
    
    try:
        with open(archive_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        
        tabulated_weeks = set()
        # Look for href patterns like UFL26-08.htm or UFL26-12.htm
        for link in soup.find_all("a", href=re.compile(r"UFL26-\d+\.htm")):
            match = re.search(r"UFL26-(\d+)\.htm", link["href"])
            if match:
                tabulated_weeks.add(int(match.group(1)))
        
        return tabulated_weeks
    except Exception as e:
        print(f"⚠️  Error reading archive: {e}")
        return set()


def append_to_archive_safely(archive_path, issue_number, w, l, ats_w, ats_l):
    """Inserts a new row inside the </table> tag to preserve layout structure."""
    win_pct = f"{(w / (w + l)) * 100:.2f}%" if (w + l) > 0 else "0.00%"
    ats_pct = f"{(ats_w / (ats_w + ats_l)) * 100:.2f}%" if (ats_w + ats_l) > 0 else "0.00%"
    
    new_row = f"""\t<tr>
\t\t<td><a href="UFL26-{issue_number:02d}.htm">Week #{issue_number}</a></td>
\t\t<td>{w}-{l}</td>
\t\t<td class="percent">{win_pct}</td>
\t\t<td>{ats_w}-{ats_l}</td>
\t\t<td class="percent">{ats_pct}</td>
\t</tr>\n"""

    with open(archive_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "</table>" in content:
        parts = content.rsplit("</table>", 1)
        updated_content = parts[0] + new_row + "</table>" + parts[1]
        
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print(f"✅ Successfully added Week #{issue_number} data into the archive table.")
    else:
        print(f"❌ Error: Could not locate a </table> tag inside {archive_path}")


def cleanup_root_template(week_num):
    """Removes the root UFLWk#.htm template file after archiving."""
    root_file = f"UFLWk{week_num}.htm"
    if os.path.exists(root_file):
        try:
            os.remove(root_file)
            print(f"🧹 Cleaned up: {root_file}")
        except Exception as e:
            print(f"⚠️  Could not remove {root_file}: {e}")


def main():
    pages_dir = "pages"
    archive_file = os.path.join(pages_dir, "26_UFLArch.htm")
    
    # 1. Check existing entries in the archive
    tabulated_weeks = get_already_tabulated_weeks(archive_file)
    print(f"📊 Currently tabulated weeks: {sorted(list(tabulated_weeks)) if tabulated_weeks else 'None'}")
    
    # 2. Scan pages/ directory for FINAL week files
    if not os.path.exists(pages_dir):
        print(f"❌ Directory '{pages_dir}' not found.")
        return

    for file_name in os.listdir(pages_dir):
        match = re.match(r"UFLWk(\d+)F\.htm", file_name, re.IGNORECASE)
        if match:
            week_num = int(match.group(1))
            
            # 3. Check if this week is already archived
            if week_num in tabulated_weeks:
                print(f"⏭️  Skipping {file_name}: Week {week_num} already archived.")
                continue
            
            # 4. Parse and tabulate the newly completed week
            file_path = os.path.join(pages_dir, file_name)
            print(f"📝 Processing: {file_path}")
            
            try:
                w, l, ats_w, ats_l = parse_issue(file_path)
                append_to_archive_safely(archive_file, week_num, w, l, ats_w, ats_l)
                
                # 5. Cleanup: Remove the root template file for this week
                cleanup_root_template(week_num)
                
            except Exception as e:
                print(f"❌ Failed to process {file_name}: {e}")


if __name__ == "__main__":
    main()
