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
    
    if (!weeklyTemplates.length && !allRootFiles.includes('UFLWTmp.htm')) {
        console.error("❌ No target files found in root directory.");
        return;
    }

    // 2. PROCESS WEEKLY TEMPLATES -> SAVES TO pages/UFLWk#F.htm
    for (const fileName of weeklyTemplates) {
        const sourcePath = path.join(ROOT_DIR, fileName);
        const ext = path.extname(fileName);
        const base = path.basename(fileName, ext);
        const targetPath = path.join(OUTPUT_DIR, `${base}${FINAL_SUFFIX}${ext}`);

        console.log(`📝 Processing template: ${fileName} -> pages/${base}${FINAL_SUFFIX}${ext}`);
        processAndSaveFile(sourcePath, targetPath, resultsMap);
    }

    // 3. PROCESS THE LIVE ROOT TEMP FILE -> OVERWRITES ROOT UFLWTmp.htm
    const tmpFile = 'UFLWTmp.htm';
    if (allRootFiles.some(f => f.toLowerCase() === tmpFile.toLowerCase())) {
        const tmpPath = path.join(ROOT_DIR, tmpFile);
        console.log(`🔥 Injecting scores directly into root front-page frame: ${tmpFile}`);
        processAndSaveFile(tmpPath, tmpPath, resultsMap); 
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
    
    const targetDir = path.dirname(targetPath);
    if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
    }
    
    fs.writeFileSync(targetPath, updated, "utf8");
}

function injectScores(html, resultsMap) {
    let content = html;

    // Fixed normalization logic just in case lowercase slips into comments
    content = content.replace(/<!--FINAL-SCORE-([A-Za-z]+)-([A-Za-z]+)-->/g, (match, away, home) => {
        const key = `${away.toUpperCase()}_${home.toUpperCase()}`;
        return resultsMap[key]?.scoreString || match;
    });

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

    if (!gameData || !gameData.completed) return block;

    // Update the baseline score row
    let updatedBlock = block.replace(
        /(<tr>\s*<td><b>Final Score:<\/b><\/td>)(<td[^>]*>)(?:<!--.*?-->)?([\s\S]*?)(<\/td>\s*<\/tr>)/i,
        (_, trOpen, tdOpen, oldValue, tdClose) => `${trOpen}${tdOpen}${gameData.scoreString}${tdClose}`
    );

    return updatedBlock;
}

main();
