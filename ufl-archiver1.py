import os
import re
from bs4 import BeautifulSoup

def parse_issue(html_path):
    """Parses a specific week file to compute stats."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    game_cards = soup.find_all("div", class_="game-card")
    winners = 0
    ats_winners = 0
    total_games = 0
    
    for card in game_cards:
        total_games += 1
        
        # Extract projected score
        proj_text = card.find(string=re.compile("Projected Score"))
        if not proj_text:
            continue
        proj_scores = proj_text.find_parent("td").find_next("td").text.strip()
        proj_home, proj_away = map(int, re.findall(r"\d+", proj_scores))
        
        # Extract final score
        final_text = card.find(string=re.compile("Final Score"))
        if not final_text:
            continue
        final_scores = final_text.find_parent("td").find_next("td").text.strip()
        final_nums = list(map(int, re.findall(r"\d+", final_scores)))
        if len(final_nums) < 2:
            continue
        final_home, final_away = final_nums[0], final_nums[1]
        
        # Determine projected winner
        proj_winner = "home" if proj_home > proj_away else "away"
        final_winner = "home" if final_home > final_away else "away"
        
        if proj_winner == final_winner:
            winners += 1
            
        # Extract spread from header
        header_tag = card.find("h4")
        if not header_tag:
            continue
        header = header_tag.text
        spread_match = re.search(r"([+-]\d+\.?\d*)", header)
        spread = float(spread_match.group(1)) if spread_match else 0.0
        
        # ATS logic
        margin = final_home - final_away
        proj_margin = proj_home - proj_away
        ats_correct = (margin + spread > 0) if proj_margin > 0 else (margin - spread < 0)
        if ats_correct:
            ats_winners += 1
            
    return winners, total_games - winners, ats_winners, total_games - ats_winners

def get_already_tabulated_weeks(archive_path):
    """Scans the archive file to check which weeks are already added."""
    if not os.path.exists(archive_path):
        return set()
        
    with open(archive_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    tabulated_weeks = set()
    # Looks for href patterns like UFL26-08.htm or UFL26-12.htm inside the table
    for link in soup.find_all("a", href=re.compile(r"UFL26-\d+\.htm")):
        match = re.search(r"UFL26-(\d+)\.htm", link["href"])
        if match:
            tabulated_weeks.add(int(match.group(1)))
            
    return tabulated_weeks

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

    # Find the position of the last closing table tag
    if "</table>" in content:
        parts = content.rsplit("</table>", 1)
        # Stitch it back together cleanly
        updated_content = parts[0] + new_row + "</table>" + parts[1]
        
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        print(f"✅ Successfully added Week #{issue_number} data into the archive table.")
    else:
        print(f"❌ Error: Could not locate a </table> tag inside {archive_path}")

def main():
    pages_dir = "pages"
    archive_file = os.path.join(pages_dir, "26_UFLArch.htm")
    
    # 1. Check existing entries in the archive
    tabulated_weeks = get_already_tabulated_weeks(archive_file)
    print(f"Currently tabulated weeks found in archive: {sorted(list(tabulated_weeks))}")
    
    # 2. Scan pages/ directory for week files (matching pattern like UFLWk8F.htm or UFLWk12F.htm)
    if not os.path.exists(pages_dir):
        print(f"Directory '{pages_dir}' not found.")
        return

    for file_name in os.listdir(pages_dir):
        match = re.match(r"UFLWk(\d+)F\.htm", file_name, re.IGNORECASE)
        if match:
            week_num = int(match.group(1))
            
            # 3. Check if this week is already handled
            if week_num in tabulated_weeks:
                print(f"Skipping {file_name}: Week {week_num} is already tabulated.")
                continue
                
            # 4. Parse missing week and update the archive document
            file_path = os.path.join(pages_dir, file_name)
            print(f"Processing new data from file: {file_path}...")
            
            try:
                w, l, ats_w, ats_l = parse_issue(file_path)
                append_to_archive_safely(archive_file, week_num, w, l, ats_w, ats_l)
            except Exception as e:
                print(f"❌ Failed to parse or save data for {file_name}: {e}")

if __name__ == "__main__":
    main()
