// 1. MUST BE AT THE VERY TOP: Force-loads the .env file from the execution root
const path = require('path');
require('dotenv').config({ path: path.join(process.cwd(), '.env') });

const axios = require('axios');
const fs = require('fs');

// 2. Strict directory routing: Read templates from root, write finals to pages/
const PAGES_DIR = process.cwd();
const OUTPUT_DIR = path.join(process.cwd(), 'pages');

const INPUT_FILE_REGEX = /^UFLWk(\d+)\.htm$/i;
const FINAL_SUFFIX = 'F';

const TEAM_ABBR_MAP = {
  'BIRMINGHAM STALLIONS': 'BHAM',
  'MICHIGAN PANTHERS': 'MICH',
  'MEMPHIS SHOWBOATS': 'MEM',
  'HOUSTON ROUGHNECKS': 'HOU',
  'HOUSTON GAMBLERS': 'HOU',
  'ARLINGTON RENEGADES': 'DAL',
  'DALLAS RENEGADES': 'DAL',
  'DC DEFENDERS': 'DC',
  'D.C. DEFENDERS': 'DC',
  'SAN ANTONIO BRAHMAS': 'SA',
  'ST. LOUIS BATTLEHAWKS': 'STL',
  'ST LOUIS BATTLEHAWKS': 'STL',
  'LOUISVILLE KINGS': 'LOU',
  'COLUMBUS AVIATORS': 'CLB',
  'ORLANDO STORM': 'ORL'
};

async function main() {
  console.log('🔄 Loading live score streams from The Odds API...');
  const scoresFeed = await fetchOddsApiScores();

  // HARDENING 1: Process does not exit with code 1 if the API is blank (e.g. past 3-day limit)
  if (!scoresFeed || !scoresFeed.length) {
    console.warn('⚠️ No tracking elements returned from API (likely past 3-day window limit). Proceeding without fresh feed data.');
  }

  // Scan the root directory for active unfinalized templates (e.g., UFLWk8.htm)
  const pageFiles = fs.readdirSync(PAGES_DIR)
    .filter(file => INPUT_FILE_REGEX.test(file) && !file.match(/F\.htm$/i));

  if (!pageFiles.length) {
    console.error(`📁 No UFLWk#.htm template files found in root directory: ${PAGES_DIR}`);
    process.exit(1);
  }

  // Map API elements if present, fallback to empty mapping matrix if missing
  const masterResultsMap = scoresFeed ? buildMasterAbbreviationResults(scoresFeed) : {};

  for (const fileName of pageFiles) {
    await processPageFile(fileName, masterResultsMap);
  }
}

async function fetchOddsApiScores() {
  const oddsKey = process.env.ODDS_API_KEY;
  if (!oddsKey) {
    console.error('❌ Missing ODDS_API_KEY inside your local .env configuration file.');
    return null;
  }

            // FIXED ENDPOINT: Uses the official sports scores payload key for UFL football
  const targetUrl = `https://api.the-odds-api.com/v4/sports/americanfootball_ufl/scores/?apiKey=${oddsKey}&daysFrom=3`;


  try {
    console.log('📡 Requesting verified live data stream from endpoint...');
    const response = await axios.get(targetUrl);
    return Array.isArray(response.data) ? response.data : (response.data.data || []);
  } catch (error) {
    console.warn('⚠️ API connection handshake failed:', error.message);
    return null;
  }
}

function buildMasterAbbreviationResults(scoresFeed) {
  const map = {};

  scoresFeed.forEach(game => {
    const rawAwayName = String(game.away_team).toUpperCase();
    const rawHomeName = String(game.home_team).toUpperCase();

    const awayAbbr = TEAM_ABBR_MAP[rawAwayName] || TEAM_ABBR_MAP[rawAwayName.replace(/[\.]/g, '')] || rawAwayName.split(' ').pop();
    const homeAbbr = TEAM_ABBR_MAP[rawHomeName] || TEAM_ABBR_MAP[rawHomeName.replace(/[\.]/g, '')] || rawHomeName.split(' ').pop();

    const isCompleted = game.completed || false;
    const isLive = !isCompleted && Array.isArray(game.scores) && game.scores.length > 0;
    
    let homeScore = 0;
    let awayScore = 0;

    if ((isCompleted || isLive) && Array.isArray(game.scores)) {
      const hScoreObj = game.scores.find(s => String(s.name).toUpperCase() === rawHomeName);
      const aScoreObj = game.scores.find(s => String(s.name).toUpperCase() === rawAwayName);
      homeScore = hScoreObj ? Number(hScoreObj.score) : 0;
      awayScore = aScoreObj ? Number(aScoreObj.score) : 0;
    }

    let actualWinner = 'push';
    if (isCompleted) {
      if (homeScore > awayScore) actualWinner = homeAbbr;
      else if (awayScore > homeScore) actualWinner = awayAbbr;
    }

    let scoreString = 'TBD';
    if (isCompleted) {
      scoreString = `${awayAbbr} ${awayScore} - ${homeAbbr} ${homeScore}`;
    } else if (isLive) {
      scoreString = `${awayAbbr} ${awayScore} - ${homeAbbr} ${homeScore} (LIVE)`;
    }
    
    const key = `${awayAbbr}_${homeAbbr}`;
    const reverseKey = `${homeAbbr}_${awayAbbr}`;

    map[key] = {
      scoreString,
      isCompleted,
      isLive,
      actualWinner,
      awayAbbr,
      homeAbbr
    };
    map[reverseKey] = { ...map[key] };
  });

  return map;
}

async function processPageFile(fileName, masterResultsMap) {
  const sourcePath = path.join(PAGES_DIR, fileName);
  
  const ext = path.extname(fileName);
  const base = path.basename(fileName, ext);
  const targetPath = path.join(OUTPUT_DIR, `${base}${FINAL_SUFFIX}${ext}`);

  // HARDENING 2: If an early iteration output file already exists in the /pages/ directory, 
  // read that instead of resetting to raw template file state.
  let content;
  if (fs.existsSync(targetPath)) {
    console.log(`♻️ Found existing target file. Running in incremental update mode: pages/${base}${FINAL_SUFFIX}${ext}`);
    content = fs.readFileSync(targetPath, 'utf8');
  } else {
    console.log(`🔍 Scanning raw root template content: ${fileName}`);
    content = fs.readFileSync(sourcePath, 'utf8');
  }

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const updatedContent = injectScoresAndDecorations(content, masterResultsMap);

  fs.writeFileSync(targetPath, updatedContent, 'utf8');
  console.log(`✅ Final edition written to: pages/${base}${FINAL_SUFFIX}${ext}`);
}

function injectScoresAndDecorations(html, resultsMap) {
  let content = html;

  // 1. Process inline text tag replacements [FINAL_SCORE_MICH_BHAM] if they are currently TBD
  content = content.replace(/\[FINAL_SCORE_([A-Z]+)_([A-Z]+)\]/g, (match, away, home) => {
    const freshData = resultsMap[`${away}_${home}`];
    return freshData?.scoreString || match; 
  });

  // 2. Process Game Cards with incremental state isolation guards
  content = content.replace(/<div[^>]*class=["']game-card["'][^>]*>[\s\S]*?<\/div>/gi, (block) => {
    // HARDENING check: If the final score block is already decorated or filled with numbers, skip updates entirely
    if (block.includes('class="status-win"') || /<td><b>Final Score:<\/b><\/td><td[^>]*>\s*[A-Z]{2,4}\s+\d+/i.test(block)) {
      return block; // Returns block completely untouched preserving early execution results
    }

    const projectedMatch = /<td><b>Projected Score:<\/b><\/td><td>\s*([A-Z]{2,4})\s+(\d+)\s*[–-]\s*([A-Z]{2,4})\s+(\d+)\s*<\/td>/i.exec(block);
    if (!projectedMatch) return block;

    const projTeamA = projectedMatch[1].toUpperCase();
    const projScoreA = Number(projectedMatch[2]);
    const projTeamB = projectedMatch[3].toUpperCase();
    const projScoreB = Number(projectedMatch[4]);

    const gameData = resultsMap[`${projTeamA}_${projTeamB}`] || resultsMap[`${projTeamB}_${projTeamA}`];
    
    // If the game data is completely missing or still unplayed (TBD), keep current block state
    if (!gameData || (!gameData.isCompleted && !gameData.isLive)) return block;

    let projectedWinner = 'push';
    if (projScoreA > projScoreB) projectedWinner = projTeamA;
    else if (projScoreB > projScoreA) projectedWinner = projTeamB;

    const isPredictionCorrect = gameData.isCompleted && (projectedWinner === gameData.actualWinner) && (gameData.actualWinner !== 'push');
    let updatedBlock = block;

    if (isPredictionCorrect) {
      updatedBlock = updatedBlock.replace(
        /(<tr>\s*<td><b>Final Score:<\/b><\/td>)(<td[^>]*>)([\s\S]*?)(<\/td>\s*<\/tr>)/i,
        (_, trOpen, oldTdOpen, existingValue, tdClose) => `${trOpen}<td class="status-win">${gameData.scoreString}${tdClose}`
      );
    } else {
      updatedBlock = updatedBlock.replace(
        /(<tr>\s*<td><b>Final Score:<\/b><\/td>)(<td[^>]*>)([\s\S]*?)(<\/td>\s*<\/tr>)/i,
        (_, trOpen, oldTdOpen, existingValue, tdClose) => `${trOpen}${oldTdOpen}${gameData.scoreString}${tdClose}`
      );
    }

    return updatedBlock;
  });

  return content;
}

main().catch(error => {
  console.error('❌ Script execution failed:', error);
  process.exit(1);
});
