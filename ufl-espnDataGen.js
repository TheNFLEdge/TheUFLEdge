const axios = require('axios');
const fs = require('fs');

const HANDOFF_FILE = 'ufl_data_handoff.json';
const HTML_OUTPUT = 'UFLWTmp.htm';

async function runScraper() {
    console.log(`🚀 Scraper Active: Harvesting UFL Data & Building Skeleton...`);
    
    try {
        const url = `https://site.api.espn.com/apis/site/v2/sports/football/ufl/scoreboard?dates=2026&seasontype=2`;
        const { data } = await axios.get(url);

        let maxCompletedWeek = 0;
        let completedEvents = [];

        // 1. Sort completed games to build the Rolling Sums
        data.events.forEach(event => {
            if (event.status.type.completed) {
                if (event.week.number > maxCompletedWeek) maxCompletedWeek = event.week.number;
                completedEvents.push(event);
            }
        });

        const sums = calculateRollingSums(completedEvents);
        const nextWeek = maxCompletedWeek + 1;
        let upcomingMatchups = [];
        let htmlSkeleton = '';

// 2. Identify Next Week's Matchups & Betting Lines
data.events.forEach((event, index) => {
    if (event.week.number === nextWeek && event.status.type.state === 'pre') {
        const game = event.competitions[0];
        const home = game.competitors.find(c => c.homeAway === 'home');
        const away = game.competitors.find(c => c.homeAway === 'away');
        
        const hAbbr = home.team.abbreviation;
        const aAbbr = away.team.abbreviation;
        const rawOdds = game.odds?.[0]?.details || "TBD";
        const total = game.odds?.[0]?.overUnder ? `(${game.odds[0].overUnder})` : "";

        let cleanLine = rawOdds;

        if (rawOdds !== "TBD") {
            if (rawOdds.includes(aAbbr)) {
                // CASE 1: Away team is favorite (DAL -5.5) -> Convert to Home Dog (+5.5)
                cleanLine = rawOdds.replace(aAbbr, "").replace("-", "+").trim();
            } else {
                // CASE 2: Home team is favorite (BHAM -2.5) -> Strip duplicate name
                cleanLine = rawOdds.replace(hAbbr, "").trim();
            }
        }

        upcomingMatchups.push({
            away: aAbbr,
            home: hAbbr,
            line: cleanLine,
            ou: total
        });

        htmlSkeleton += `
<!-- ========================= -->
<!-- GAME CARD ${index + 1} -->
<!-- ========================= -->
<div class="game-card">
    <h4>${aAbbr} @ ${hAbbr} ${cleanLine} ${total}</h4>
    <table>
        <tr><td><b>Projected Score:</b></td><td>[PROJ_SCORE_${aAbbr}_${hAbbr}]</td></tr>
         <tr><td><b>Final Score:</b></td><td>[FINAL_SCORE_${aAbbr}_${hAbbr}]</td></tr>
    </table>
</div>\n`;
    }
});

        // 3. Save the JSON Handoff for the Engine
        const handoff = {
            target_week: nextWeek,
            matchups: upcomingMatchups,
            team_stats: sums
        };

        fs.writeFileSync(HANDOFF_FILE, JSON.stringify(handoff, null, 2));
        fs.writeFileSync(HTML_OUTPUT, htmlSkeleton);

        console.log(`✅ Handoff JSON ready: ${HANDOFF_FILE}`);
        console.log(`✅ HTML Skeleton ready: ${HTML_OUTPUT}`);
        console.log(`📊 Current Week: ${maxCompletedWeek} | Next Week: ${nextWeek}`);

    } catch (err) {
        console.error(`❌ Scraper Failed: ${err.message}`);
    }
}

function calculateRollingSums(events) {
    const teams = {};
    events.forEach(event => {
        const game = event.competitions[0];
        const h = game.competitors.find(c => c.homeAway === 'home');
        const a = game.competitors.find(c => c.homeAway === 'away');

        [h, a].forEach((t, i) => {
            const opp = i === 0 ? a : h;
            const name = t.team.abbreviation;
            const pf = parseInt(t.score);
            const pa = parseInt(opp.score);
            const res = pf > pa ? 'W' : 'L';

            if (!teams[name]) teams[name] = [];
            teams[name].push({ pf, pa, win: res === 'W' ? 1 : 0 });
            
            // BO: Capture the actual results of the game that just finished
            teams[name].latest_pf = pf;
            teams[name].latest_pa = pa;

        });
    });

    const matrix = {};
    for (const name in teams) {
        const last4 = teams[name].slice(-4);
        const totals = last4.reduce((acc, g) => {
            acc.pf += g.pf; acc.pa += g.pa; acc.w += g.win; return acc;
        }, { pf: 0, pa: 0, w: 0 });
          matrix[name] = { 
            pf_sum: totals.pf, 
            pa_sum: totals.pa, 
            wins: totals.w, 
            gp: last4.length,
            // BO: These fields allow the Engine to write the "Final Score" on the card
            last_pf: teams[name].latest_pf,
            last_pa: teams[name].latest_pa
        };
    }

    return matrix;
}

runScraper();
