const path = require('path');
const fs = require('fs');
const axios = require('axios');

const ROOT_DIR = process.cwd();
const OUTPUT_DIR = path.join(ROOT_DIR, 'pages');
const FINAL_SUFFIX = 'F';

// ESPN UFL Scoreboard Endpoint
const ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/ufl/scoreboard?dates=2026&seasontype=2";

async function main() {
  console.log("📡 Fetching UFL scores from ESPN…");
  const resultsMap = await fetchESPNResults();
  if (!resultsMap) {
    console.error("❌ No results map generated. Aborting.");
    return;
  }

  // 1. READ ALL ROOT FILES
  const allRootFiles = fs.readdirSync(ROOT_DIR);
  
  // Filter weekly templates (e.g., UFLWk5.htm)
  const weeklyTemplates = allRootFiles.filter(file => /^UFLWk\d+\.htm$/i.test(file));

  // 2. PROCESS WEEKLY TEMPLATES (Modify root directly, then copy to pages/)
  for (const fileName of weeklyTemplates) {
    const rootPath = path.join(ROOT_DIR, fileName);
    
    // Process and overwrite the root file directly
    console.log(`📝 Updating root file: ${fileName}`);
    processAndSaveFile(rootPath, rootPath, resultsMap);

    // Prepare target path for pages/ directory (e.g., UFLWk5F.htm)
    const ext = path.extname(fileName);
    const base = path.basename(fileName, ext);
    const pagesTargetPath = path.join(OUTPUT_DIR, `${base}${FINAL_SUFFIX}${ext}`);

    // Copy the updated root file over to pages/
    console.log(`💾 Mirroring to pages folder: pages/${base}${FINAL_SUFFIX}${ext}`);
    ensureDirectoryExistence(pagesTargetPath);
    fs.copyFileSync(rootPath, pagesTargetPath);
  }

  // 3. PROCESS THE LIVE ROOT TEMP FILE (Modify root directly, NO COPY TO PAGES)
  const tmpFile = 'UFLWTmp.htm';
  if (allRootFiles.some(f => f.toLowerCase() === tmpFile.toLowerCase())) {
    const rootTmpPath = path.join(ROOT_DIR, tmpFile);
    
    // Process and overwrite root UFLWTmp.htm directly
    console.log(`🔥 Injecting scores directly into root front-page frame: ${tmpFile}`);
    processAndSaveFile(rootTmpPath, rootTmpPath, resultsMap);
  }
}

async function fetchESPNResults() {
  try {
    const { data } = await axios.get(ESPN_URL);
    const map = {};
    data.events.forEach(event => {
      const comp = event.competitions[0];
      const home = comp.competitors.find(c => c.homeAway === "home");
      const away = comp.competitors.find(c => c.homeAway === "away");
      const homeAbbr = home.team.abbreviation.toUpperCase();
      const awayAbbr = away.team.abbreviation.toUpperCase();
      const completed = event.status.type.completed === true;
      
      let scoreString = "TBD";
      let homeScore = 0;
      let awayScore = 0;
      
      if (completed) {
        homeScore = Number(home.score);
        awayScore = Number(away.score);
        scoreString = `${awayAbbr} ${awayScore} - ${homeAbbr} ${homeScore}`;
      }

      const key = `${awayAbbr}_${homeAbbr}`;
      const reverseKey = `${homeAbbr}_${awayAbbr}`;
      const gameData = { scoreString, completed, awayAbbr, homeAbbr, homeScore, awayScore };
      
      map[key] = gameData;
      map[reverseKey] = gameData;
    });
    return map;
  } catch (err) {
    console.error("❌ ESPN fetch failed:", err.message);
    return null;
  }
}

function processAndSaveFile(sourcePath, targetPath, resultsMap) {
  const content = fs.readFileSync(sourcePath, "utf8");
  const updated = injectScores(content, resultsMap);
  ensureDirectoryExistence(targetPath);
  fs.writeFileSync(targetPath, updated, "utf8");
}

function ensureDirectoryExistence(filePath) {
  const dirname = path.dirname(filePath);
  if (!fs.existsSync(dirname)) {
    fs.mkdirSync(dirname, { recursive: true });
  }
}

function injectScores(html, resultsMap) {
  let content = html;

  // SAFE REPLACEMENT: Only replaces raw HTML comments if game state is definitively completed
  content = content.replace(/<!--FINAL-SCORE-([A-Za-z]+)-([A-Za-z]+)-->/g, (match, away, home) => {
    const key = `${away.toUpperCase()}_${home.toUpperCase()}`;
    const gameData = resultsMap[key];
    if (gameData && gameData.completed) {
      return gameData.scoreString; // Swap comment out for actual final score string
    }
    return match; // Return exactly what was found (leave marker untouched)
  });

  // GAME CARD REPLACEMENT
  content = content.replace(
    /<div[^>]*class=["']game-card["'][^>]*>[\s\S]*?<\/div>/gi,
    block => updateGameCard(block, resultsMap)
  );
  
  return content;
}

function updateGameCard(block, resultsMap) {
  const commentMatch = /<!--FINAL-SCORE-([A-Za-z]+)-([A-Za-z]+)-->/i.exec(block);
  if (!commentMatch) return block;

  const away = commentMatch[1].toUpperCase();
  const home = commentMatch[2].toUpperCase();
  const gameData = resultsMap[`${away}_${home}`];

  // CRITICAL PROTECTION: Leave the game-card HTML alone unless game is completed
  if (!gameData || !gameData.completed) return block;

  // Update the baseline score row inside the block safely
  let updatedBlock = block.replace(
    /(<tr>\s*<td><b>Final Score:<\/b><\/td>)(<td[^>]*>)(?:<!--.*?-->)?([\s\S]*?)(<\/td>\s*<\/tr>)/i,
    (_, trOpen, tdOpen, oldValue, tdClose) => `${trOpen}${tdOpen}${gameData.scoreString}${tdClose}`
  );

  return updatedBlock;
}

main();


