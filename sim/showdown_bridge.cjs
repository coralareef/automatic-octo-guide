#!/usr/bin/env node
'use strict';

const fs = require('fs');
const Sim = require('pokemon-showdown');
const {Teams, TeamValidator, BattleStream, Dex, toID} = Sim;

const HAZARD_MOVES = new Set(['stealthrock', 'spikes', 'toxicspikes', 'stickyweb']);
const REMOVAL_MOVES = new Set(['rapidspin', 'defog', 'tidyup', 'mortalspin']);
const RECOVERY_MOVES = new Set([
  'recover', 'roost', 'slackoff', 'softboiled', 'synthesis', 'moonlight',
  'morningsun', 'shoreup', 'milkdrink', 'strengthsap', 'wish', 'rest',
]);
const SETUP_MOVES = new Set([
  'swordsdance', 'nastyplot', 'dragondance', 'calmmind', 'bulkup', 'irondefense',
  'agility', 'quiverdance', 'shellsmash', 'coil', 'curse', 'tailglow',
]);
const PIVOT_MOVES = new Set(['uturn', 'voltswitch', 'flipturn', 'partingshot', 'chillyreception']);

function readInput() {
  const raw = fs.readFileSync(0, 'utf8').trim();
  return raw ? JSON.parse(raw) : {};
}

function validateTeamText(team, format) {
  if (typeof team !== 'string' || !team.trim()) {
    throw new Error('team must be a non-empty Showdown export/packed/JSON string');
  }
  const parsed = Teams.import(team);
  if (!parsed) throw new Error('could not parse team');
  const validator = new TeamValidator(format);
  const problems = validator.validateTeam(parsed) || [];
  return {
    valid: problems.length === 0,
    problems,
    parsed,
    packed: Teams.pack(parsed),
    export: Teams.export(parsed),
  };
}

function validate(input) {
  const format = input.format || 'gen9ou';
  const result = validateTeamText(input.team, format);
  return {
    format,
    valid: result.valid,
    problems: result.problems,
    packed: result.packed,
    export: result.export,
    pokemon: result.parsed.map(set => set.species),
  };
}

function otherSide(side) {
  return side === 'p1' ? 'p2' : 'p1';
}

function speciesFromDetails(details) {
  return String(details || '').split(',', 1)[0].trim();
}

function conditionFraction(condition) {
  const text = String(condition || '');
  if (text.endsWith(' fnt')) return 0;
  const match = text.match(/^(\d+)\/(\d+)/);
  if (!match) return 1;
  const max = Number(match[2]);
  return max > 0 ? Math.max(0, Math.min(1, Number(match[1]) / max)) : 1;
}

function hashNoise(text) {
  let hash = 2166136261 >>> 0;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash / 0x100000000;
}

function typeMultiplier(attackType, defenderSpecies) {
  if (!attackType || !defenderSpecies) return 1;
  const defender = Dex.species.get(defenderSpecies);
  if (!defender.exists) return 1;
  try {
    if (!Dex.getImmunity(attackType, defender)) return 0;
    return Math.pow(2, Dex.getEffectiveness(attackType, defender));
  } catch {
    return 1;
  }
}

function setForSpecies(parsedTeam, species) {
  const wanted = toID(species);
  return parsedTeam.find(set => toID(set.species) === wanted) || null;
}

function activePokemon(request) {
  const side = request.side && request.side.pokemon ? request.side.pokemon : [];
  return side.find(mon => mon.active) || side[0] || null;
}

function ownSpecies(request) {
  const mon = activePokemon(request);
  return mon ? speciesFromDetails(mon.details) : '';
}

function moveTypeStab(move, species, teraType) {
  const template = Dex.species.get(species);
  if (!template.exists || !move.type) return 1;
  const original = template.types.includes(move.type);
  const tera = teraType && teraType === move.type;
  if (tera && original) return 2;
  if (tera || original) return 1.5;
  return 1;
}

function offensiveMoveScore(moveInfo, own, opponent, ownMon, state, side) {
  const move = Dex.moves.get(moveInfo.id || moveInfo.move);
  if (!move.exists || move.category === 'Status') return null;

  let bp = Number(move.basePower || 0);
  if (bp <= 1) bp = move.ohko ? 140 : 70;
  const effectiveness = typeMultiplier(move.type, opponent);
  if (effectiveness === 0) return 0.5;
  const accuracy = move.accuracy === true ? 1 : Math.max(0.35, Number(move.accuracy || 100) / 100);
  const stab = moveTypeStab(move, own, state.teraType[side]);

  let statRatio = 1;
  const stats = ownMon && ownMon.stats ? ownMon.stats : null;
  const opp = Dex.species.get(opponent);
  if (stats && opp.exists) {
    const offense = move.category === 'Physical' ? Number(stats.atk || 100) : Number(stats.spa || 100);
    const defense = move.category === 'Physical' ? Number(opp.baseStats.def || 100) : Number(opp.baseStats.spd || 100);
    statRatio = Math.sqrt(Math.max(offense, 1) / Math.max(defense, 1));
  }

  let score = bp * effectiveness * stab * accuracy * statRatio;
  if (move.priority > 0) score *= 1 + 0.10 * move.priority;
  if (move.recoil) score *= 0.92;
  if (move.drain) score *= 1.08;
  if (PIVOT_MOVES.has(move.id)) score *= 1.10;
  return score;
}

function statusMoveScore(moveInfo, request, state, side) {
  const move = Dex.moves.get(moveInfo.id || moveInfo.move);
  if (!move.exists || move.category !== 'Status') return null;
  const id = move.id;
  const ownMon = activePokemon(request);
  const hp = conditionFraction(ownMon && ownMon.condition);
  const boosts = state.boosts[side] || {};

  if (RECOVERY_MOVES.has(id) || move.heal) {
    const missing = 1 - hp;
    if (hp < 0.22) return 135;
    if (hp < 0.45) return 112;
    if (hp < 0.70) return 82;
    return 12 + 20 * missing;
  }
  if (HAZARD_MOVES.has(id)) {
    const existing = state.hazards[otherSide(side)].has(id);
    return existing ? 10 : state.turn <= 8 ? 105 : state.turn <= 20 ? 75 : 38;
  }
  if (REMOVAL_MOVES.has(id)) {
    return state.hazards[side].size ? 110 : 28;
  }
  if (SETUP_MOVES.has(id)) {
    const boostTotal = Object.values(boosts).reduce((acc, value) => acc + Math.max(Number(value || 0), 0), 0);
    if (hp < 0.38) return 18;
    return Math.max(20, 96 - 22 * boostTotal + 18 * (hp - 0.5));
  }
  if (id === 'substitute') return hp > 0.65 ? 66 : 18;
  if (id === 'protect' || id === 'detect') return 38;
  if (id === 'taunt' || id === 'encore') return 60;
  if (id === 'toxic' || id === 'willowisp' || id === 'thunderwave' || id === 'glare') return 64;
  if (id === 'trick' || id === 'switcheroo') return 60;
  if (id === 'leechseed') return 62;
  if (move.boosts || (move.self && move.self.boosts)) return hp > 0.5 ? 72 : 30;
  if (move.status || move.volatileStatus || move.sideCondition) return 52;
  return 35;
}

function candidateSetMoves(parsedTeam, species) {
  const set = setForSpecies(parsedTeam, species);
  return set && Array.isArray(set.moves) ? set.moves : [];
}

function switchScore(mon, parsedTeam, opponent, state, side) {
  const species = speciesFromDetails(mon.details);
  const hp = conditionFraction(mon.condition);
  if (!species || hp <= 0) return -Infinity;
  const template = Dex.species.get(species);
  if (!template.exists) return 20 * hp;

  let offense = 35;
  for (const moveName of candidateSetMoves(parsedTeam, species)) {
    const move = Dex.moves.get(moveName);
    if (!move.exists || move.category === 'Status') continue;
    let bp = Number(move.basePower || 0);
    if (bp <= 1) bp = move.ohko ? 140 : 70;
    offense = Math.max(offense, bp * typeMultiplier(move.type, opponent) * moveTypeStab(move, species, null));
  }

  const foe = Dex.species.get(opponent);
  let defense = 60;
  if (foe.exists) {
    let worst = 1;
    for (const foeType of foe.types) {
      worst = Math.max(worst, typeMultiplier(foeType, species));
    }
    defense = 85 / Math.max(worst, 0.5);
  }

  let hazardPenalty = 0;
  if (state.hazards[side].has('stealthrock')) {
    hazardPenalty += 18 * typeMultiplier('Rock', species);
  }
  if (state.hazards[side].has('spikes')) hazardPenalty += 10;
  return 0.52 * offense + 0.48 * defense + 35 * hp - hazardPenalty;
}

function chooseTeamPreview(request, parsedTeam, seedKey, state) {
  const pokemon = request.side && request.side.pokemon ? request.side.pokemon : [];
  if (!pokemon.length) return 'default';
  const scored = pokemon.map((mon, index) => {
    const species = speciesFromDetails(mon.details);
    const set = setForSpecies(parsedTeam, species);
    const moves = new Set((set && set.moves || []).map(toID));
    const template = Dex.species.get(species);
    let score = template.exists ? Number(template.baseStats.spe || 50) * 0.15 : 0;
    if ([...moves].some(move => HAZARD_MOVES.has(move))) score += 45;
    if ([...moves].some(move => PIVOT_MOVES.has(move))) score += 22;
    score += 0.01 * hashNoise(`${seedKey}|preview|${species}|${state.decisions}`);
    return {slot: index + 1, score};
  }).sort((a, b) => b.score - a.score);
  return `team ${scored.map(row => row.slot).join('')}`;
}

function chooseForcedSwitch(request, parsedTeam, state, side, seedKey) {
  const pokemon = request.side && request.side.pokemon ? request.side.pokemon : [];
  const opponent = state.active[otherSide(side)] || '';
  const choices = [];
  for (let i = 0; i < pokemon.length; i++) {
    const mon = pokemon[i];
    if (mon.active || String(mon.condition || '').endsWith(' fnt')) continue;
    let score = switchScore(mon, parsedTeam, opponent, state, side);
    score += 0.001 * hashNoise(`${seedKey}|force|${i}|${state.decisions}`);
    choices.push({slot: i + 1, score});
  }
  choices.sort((a, b) => b.score - a.score);
  return choices.length ? `switch ${choices[0].slot}` : 'default';
}

function chooseHeuristic(request, parsedTeam, state, side, seedKey) {
  state.decisions += 1;
  if (request.wait) return null;
  if (request.teamPreview) return chooseTeamPreview(request, parsedTeam, seedKey, state);
  if (request.forceSwitch) return chooseForcedSwitch(request, parsedTeam, state, side, seedKey);
  if (!request.active || !request.active.length) return 'default';

  const activeReq = request.active[0];
  const pokemon = request.side && request.side.pokemon ? request.side.pokemon : [];
  const ownMon = activePokemon(request);
  const own = ownSpecies(request);
  const opponent = state.active[otherSide(side)] || '';
  const hp = conditionFraction(ownMon && ownMon.condition);
  const legalMoves = [];

  for (let i = 0; i < (activeReq.moves || []).length; i++) {
    const info = activeReq.moves[i];
    if (info.disabled) continue;
    const damage = offensiveMoveScore(info, own, opponent, ownMon, state, side);
    const status = statusMoveScore(info, request, state, side);
    let score = damage !== null ? damage : status !== null ? status : 1;
    score += 0.001 * hashNoise(`${seedKey}|move|${i}|${state.decisions}`);
    legalMoves.push({slot: i + 1, score, info, move: Dex.moves.get(info.id || info.move)});
  }
  legalMoves.sort((a, b) => b.score - a.score);
  const bestMove = legalMoves[0] || null;

  const switches = [];
  if (!activeReq.trapped) {
    for (let i = 0; i < pokemon.length; i++) {
      const mon = pokemon[i];
      if (mon.active || String(mon.condition || '').endsWith(' fnt')) continue;
      let score = switchScore(mon, parsedTeam, opponent, state, side) - 38;
      score += 0.001 * hashNoise(`${seedKey}|switch|${i}|${state.decisions}`);
      switches.push({slot: i + 1, score});
    }
    switches.sort((a, b) => b.score - a.score);
  }

  const bestSwitch = switches[0] || null;
  const shouldSwitch = bestSwitch && (
    !bestMove ||
    (hp < 0.24 && bestSwitch.score > 48) ||
    (bestMove.score < 48 && bestSwitch.score > bestMove.score + 24)
  );
  if (shouldSwitch) return `switch ${bestSwitch.slot}`;
  if (!bestMove) return bestSwitch ? `switch ${bestSwitch.slot}` : 'default';

  let choice = `move ${bestMove.slot}`;
  const canTera = !!activeReq.canTerastallize;
  if (canTera && bestMove.move && bestMove.move.category !== 'Status') {
    const teraType = String(activeReq.canTerastallize || '');
    const teraSynergy = teraType && bestMove.move.type === teraType;
    if ((teraSynergy && bestMove.score >= 125 && hp >= 0.35) || bestMove.score >= 210) {
      choice += ' terastallize';
    }
  }
  return choice;
}

function updateHeuristicState(output, state) {
  const lines = String(output || '').split('\n');
  for (const line of lines) {
    let match = line.match(/^\|(switch|drag|replace|detailschange)\|(p[12])a:[^|]*\|([^|]+)/);
    if (match) {
      state.active[match[2]] = speciesFromDetails(match[3]);
      continue;
    }
    match = line.match(/^\|turn\|(\d+)/);
    if (match) {
      state.turn = Math.max(state.turn, Number(match[1]));
      continue;
    }
    match = line.match(/^\|-terastallize\|(p[12])a:[^|]*\|([^|]+)/);
    if (match) {
      state.teraType[match[1]] = match[2].trim();
      continue;
    }
    match = line.match(/^\|-(boost|unboost)\|(p[12])a:[^|]*\|([^|]+)\|(-?\d+)/);
    if (match) {
      const sign = match[1] === 'boost' ? 1 : -1;
      const side = match[2];
      const stat = match[3];
      state.boosts[side][stat] = Math.max(-6, Math.min(6, (state.boosts[side][stat] || 0) + sign * Number(match[4])));
      continue;
    }
    match = line.match(/^\|-clearboost\|(p[12])a:/);
    if (match) {
      state.boosts[match[1]] = {};
      continue;
    }
    match = line.match(/^\|-sidestart\|(p[12]):[^|]*\|(?:move: )?([^|]+)/);
    if (match) {
      const id = toID(match[2]);
      if (HAZARD_MOVES.has(id)) state.hazards[match[1]].add(id);
      continue;
    }
    match = line.match(/^\|-sideend\|(p[12]):[^|]*\|(?:move: )?([^|]+)/);
    if (match) {
      state.hazards[match[1]].delete(toID(match[2]));
    }
  }
}

function requestFromOutput(output) {
  const match = String(output).match(/^sideupdate\n(p[12])\n\|request\|([^\n]*)/s);
  if (!match) return null;
  return {side: match[1], request: JSON.parse(match[2])};
}

function sideErrorFromOutput(output) {
  const match = String(output).match(/^sideupdate\n(p[12])\n\|error\|/s);
  return match ? match[1] : null;
}

async function runBattle(input, policy) {
  const format = input.format || 'gen9ou';
  const p1 = validateTeamText(input.p1team, format);
  const p2 = validateTeamText(input.p2team, format);
  if (!p1.valid) throw new Error(`p1 illegal: ${p1.problems.join('; ')}`);
  if (!p2.valid) throw new Error(`p2 illegal: ${p2.problems.join('; ')}`);

  const stream = new BattleStream();
  const seed = String(input.seed || '1,2,3,4');
  const maxTurns = Number(input.maxTurns || 1000);
  let winner = null;
  let turns = 0;
  let requests = 0;
  let errors = 0;
  const state = {
    turn: 0,
    decisions: 0,
    active: {p1: '', p2: ''},
    teraType: {p1: '', p2: ''},
    boosts: {p1: {}, p2: {}},
    hazards: {p1: new Set(), p2: new Set()},
  };
  const teams = {p1: p1.parsed, p2: p2.parsed};

  stream.write(`>start ${JSON.stringify({formatid: format, seed})}`);
  stream.write(`>player p1 ${JSON.stringify({name: 'P1', team: p1.packed})}`);
  stream.write(`>player p2 ${JSON.stringify({name: 'P2', team: p2.packed})}`);

  for await (const output of stream) {
    updateHeuristicState(output, state);
    const turnMatches = [...output.matchAll(/\|turn\|(\d+)/g)];
    for (const match of turnMatches) turns = Math.max(turns, Number(match[1]));

    const winMatch = output.match(/\|win\|([^\n]+)/);
    if (winMatch) winner = winMatch[1].trim();
    if (output.includes('|tie|')) winner = 'tie';

    if (turns > maxTurns) {
      stream.writeEnd();
      throw new Error(`battle exceeded maxTurns=${maxTurns}`);
    }

    const req = requestFromOutput(output);
    if (req) {
      requests += 1;
      let choice = 'default';
      if (policy === 'heuristic') {
        choice = chooseHeuristic(req.request, teams[req.side], state, req.side, `${seed}|${req.side}`) || 'default';
      }
      stream.write(`>${req.side} ${choice}`);
    } else {
      const errorSide = sideErrorFromOutput(output);
      if (errorSide) {
        errors += 1;
        stream.write(`>${errorSide} default`);
      }
    }

    if (winner) {
      stream.writeEnd();
      break;
    }
  }

  if (!winner) throw new Error('battle ended without a winner/tie message');
  return {format, winner, turns, requests, seed, policy, errors};
}

async function simulateDefault(input) {
  return runBattle(input, 'default');
}

async function simulateHeuristic(input) {
  return runBattle(input, 'heuristic');
}

async function main() {
  const command = process.argv[2] || 'validate';
  try {
    const input = readInput();
    let output;
    if (command === 'validate') {
      output = validate(input);
    } else if (command === 'simulate-default') {
      output = await simulateDefault(input);
    } else if (command === 'simulate-heuristic') {
      output = await simulateHeuristic(input);
    } else {
      throw new Error(`unknown command: ${command}`);
    }
    process.stdout.write(JSON.stringify(output));
  } catch (error) {
    process.stderr.write(String(error && error.stack ? error.stack : error));
    process.exitCode = 1;
  }
}

void main();
