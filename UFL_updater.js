const path = require('path');
const fs = require('fs');
const axios = require('axios');

const PAGES_DIR = process.cwd();
const OUTPUT_DIR = path.join(process.cwd(), 'pages');

const INPUT_FILE_REGEX = /^UFLWk(\d+)\.htm$/i;
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

    console.log("📘 Score map keys:", Object.keys(resultsMap));

    const pageFiles = fs.readdirSync(PAGES_DIR)
        .filter(file => INPUT_FILE_REGEX.test(file) && !file.match(/F\.htm$/i));

    if (!pageFiles.length) {
        console.error("❌ No UFLWk#.htm template files found.");
        return;
    }

    for (const fileName of pageFiles) {
        await processPageFile(fileName, resultsMap);
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

            if (completed) {
                const hScore = Number(home.score);
                const aScore = Number(away.score);
                scoreString = `${awayAbbr} ${aScore} - ${homeAbbr} ${hScore}`;
            }

            const key = `${awayAbbr}_${homeAbbr}`;
            const reverseKey = `${homeAbbr}_${awayAbbr}`;

            map[key] = { scoreString, completed, awayAbbr, homeAbbr };
            map[reverseKey] = { scoreString, completed, awayAbbr, homeAbbr };
        });

        return map;

    } catch (err) {
        console.error("❌ ESPN fetch failed:", err.message);
        return null;
    }
}

async function processPageFile(fileName, resultsMap) {
    const sourcePath = path.join(PAGES_DIR, fileName);

    const ext = path.extname(fileName);
    const base = path.basename(fileName, ext);
    const targetPath = path.join(OUTPUT_DIR, `${base}${FINAL_SUFFIX}${ext}`);

    console.log(`📝 Updating: ${fileName}`);

    const content = fs.readFileSync(sourcePath, "utf8");

    if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    }

    const updated = injectScores(content, resultsMap);

    fs.writeFileSync(targetPath, updated, "utf8");

    console.log(`✅ Wrote: pages/${base}${FINAL_SUFFIX}${ext}`);
}

function injectScores(html, resultsMap) {
    let content = html;

    // Replace HTML comment markers like <!--FINAL-SCORE-ORL-DAL-->
    content = content.replace(/<!--FINAL-SCORE-([A-Z]+)-([A-Z]+)-->/g,
        (match, away, home) => {
            const key = `${away}_${home}`;
            return resultsMap[key]?.scoreString || match;
        }
    );

    // Update game-card blocks
    content = content.replace(
        /<div[^>]*class=["']game-card["'][^>]*>[\s\S]*?<\/div>/gi,
        block => updateGameCard(block, resultsMap)
    );

    return content;
}

function updateGameCard(block, resultsMap) {
    // Extract comment marker teams
    const commentMatch = /<!--FINAL-SCORE-([A-Z]+)-([A-Z]+)-->/i.exec(block);
    if (!commentMatch) return block;

    const away = commentMatch[1];
    const home = commentMatch[2];

    const gameData =
        resultsMap[`${away}_${home}`] ||
        resultsMap[`${home}_${away}`];

    if (!gameData || !gameData.completed) return block;

    const scoreString = gameData.scoreString;

    // Replace Final Score row
    return block.replace(
        /(<tr>\s*<td><b>Final Score:<\/b><\/td>)(<td[^>]*>)(?:<!--.*?-->)?([\s\S]*?)(<\/td>\s*<\/tr>)/i,
        (_, trOpen, tdOpen, oldValue, tdClose) =>
            `${trOpen}${tdOpen}${scoreString}${tdClose}`
    );
}

main();
