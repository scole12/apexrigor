/* NFL schedule display: no dependency on market availability or results. */
window.NFLBoard = (() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const timeET = value => {
    if (!value || !Number.isFinite(Date.parse(value))) return 'Time to be confirmed';
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
      timeZone:'America/New_York', weekday:'short', month:'short', day:'numeric',
      hour:'numeric', minute:'2-digit', hour12:true
    }).formatToParts(new Date(value)).map(p => [p.type, p.value]));
    return `${parts.weekday}, ${parts.month} ${parts.day} · ${parts.hour}:${parts.minute} ${parts.dayPeriod} ET`;
  };
  const short = value => String(value || '').replace('NFL_TEAM_', '').replace(/^LA$/, 'LAR');
  const order = {ATS:0, TOTALS:1, PROPS:2};
  function issuedPanel(p) {
    const label = p.display_market_label || (p.market === 'ATS' ? 'FULL-GAME ATS' : p.market === 'TOTALS' ? 'FULL-GAME TOTALS' : 'PLAYER PROP');
    const headline = p.display_selection || `${p.selection} ${p.line}`;
    const probability = p.issued_probability == null ? NaN : Number(p.issued_probability);
    const pct = Number.isFinite(probability) ? (probability * 100).toFixed(1) + '%' : 'N/A';
    const price = p.american_price == null ? '' : ` · PRICE ${Number(p.american_price) > 0 ? '+' : ''}${p.american_price}`;
    return `<section class="market-panel" data-market="${esc(p.market)}" data-position-state="SEALED"><div class="market-label">${esc(label)}</div><div class="market-panel-head"><span class="pick-headline">${esc(headline)}</span></div><div class="meta mono">APEX WIN PROBABILITY: ${esc(pct)} · Sportsbook: FanDuel${esc(price)}</div><div class="rationale-copy"><p>Line, price and probability as issued at SEALED T-2.</p></div></section>`;
  }
  function render(today, {picks = false} = {}) {
    if (!Array.isArray(today?.slate?.games)) throw new Error('Schedule unavailable');
    const games = today.slate.games.slice().sort((a, b) => String(a.kickoff_utc).localeCompare(String(b.kickoff_utc)) || String(a.game_id).localeCompare(String(b.game_id)));
    const positions = games.reduce((n, g) => n + (g.positions || []).length, 0);
    const reconciled = Number(today.position_count) === positions && today.public_issuance === (positions > 0);
    const blocked = String(today.scientific_release_state || '').startsWith('SCIENCE_BLOCKED');
    const template = document.getElementById('nfl-game-template').innerHTML;
    document.getElementById('slate-title').textContent = positions && reconciled ? 'NFL GAME BOARD' : 'UPCOMING NFL';
    document.getElementById('slate-meta').textContent = `${games.length} ${games.length === 1 ? 'GAME' : 'GAMES'} · ${reconciled ? positions + ' ISSUED POSITIONS' : 'PICKS STATUS UNAVAILABLE'}`;
    const shell = document.querySelector('.shell');
    shell.dataset.publicIssuance = String(reconciled && positions > 0);
    shell.dataset.picksState = positions && reconciled ? 'issued' : blocked ? 'science-blocked' : 'unissued';
    document.getElementById('games').innerHTML = games.map((game, index) => {
      const ps = reconciled ? (game.positions || []).slice().sort((a,b) => (order[a.market] ?? 9) - (order[b.market] ?? 9)) : [];
      const values = {
        ID:game.game_id, STATE:ps.length ? 'ISSUED' : 'UNISSUED', NUMBER:index === 0 ? 'NEXT' : `G${String(index + 1).padStart(2,'0')}`,
        ABBREVIATION:`${short(game.away_team_id)} @ ${short(game.home_team_id)}`, SEASON:game.season, WEEK:game.week, MATCHUP:game.matchup,
        SCHEDULE_STATE:game.status || 'SCHEDULED', KICKOFF:game.kickoff_et || game.kickoff_utc, TIME:timeET(game.kickoff_utc || game.kickoff_et),
        PREPARATION:ps.length ? `${ps.length} ISSUED POSITIONS` : 'PREPARE',
        DETAIL:!reconciled ? 'Picks are temporarily unavailable. The scheduled game remains on the board.' : ps.length ? (picks ? 'Selections as issued.' : 'Selections are available on the Picks board.') : 'No picks issued. Lines and prices will appear with issued selections.'
      };
      const milestones = [['NEXT_T3','DATA REPORT'],['NEXT_T2','PICKS REVIEW']].flatMap(([key,label]) => {
        const stage = today.next_up?.[key], at = stage?.at_et || stage?.at_utc;
        return at && stage.game_ids?.includes(game.game_id) ? [`<div><dt>${label} · ${esc(stage.state)}</dt><dd><time datetime="${esc(at)}">${esc(timeET(at))}</time></dd></div>`] : [];
      });
      const status = blocked && !ps.length ? '<p class="nfl-science mono">SCIENCE_BLOCKED · 0 ISSUED POSITIONS</p>' : '';
      values.MILESTONES = (milestones.length ? `<dl class="nfl-milestones mono">${milestones.join('')}</dl>` : '') + status;
      values.POSITIONS = picks && ps.length ? `<div class="market-grid${ps.length === 1 ? ' market-grid--single' : ''}">${ps.map(issuedPanel).join('')}</div>` : '';
      return template.replace(/\[\[([A-Z_]+)\]\]/g, (_, key) => ['MILESTONES','POSITIONS'].includes(key) ? values[key] : esc(values[key]));
    }).join('') || '<p class="nfl-schedule-note">The next NFL schedule has not been published yet. This board updates with the next scheduled slate.</p>';
    const board = document.querySelector('.nfl-board');
    board.dataset.generatedAt = today.generated_at_utc || '';
    board.dataset.refreshState = 'current';
    document.getElementById('nfl-refresh-status').textContent = `SCHEDULE UPDATED ${timeET(today.generated_at_utc)}`;
  }
  function mount(options) {
    return fetch('/data/nfl_today.json', {cache:'no-store'})
      .then(r => { if (!r.ok) throw new Error('Schedule refresh unavailable'); return r.json(); })
      .then(d => render(d, options))
      .catch(() => {
        const board = document.querySelector('.nfl-board');
        board.dataset.refreshState = 'published-snapshot';
        document.getElementById('nfl-refresh-status').textContent = `Showing the published schedule from ${timeET(board.dataset.generatedAt)}. Live refresh is temporarily unavailable.`;
      });
  }
  return {mount, render};
})();
