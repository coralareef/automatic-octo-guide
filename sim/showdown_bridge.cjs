#!/usr/bin/env node
'use strict';

const fs = require('fs');
const Sim = require('pokemon-showdown');
const {Teams, TeamValidator, BattleStream} = Sim;

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

async function simulateDefault(input) {
  const format = input.format || 'gen9ou';
  const p1 = validateTeamText(input.p1team, format);
  const p2 = validateTeamText(input.p2team, format);
  if (!p1.valid) throw new Error(`p1 illegal: ${p1.problems.join('; ')}`);
  if (!p2.valid) throw new Error(`p2 illegal: ${p2.problems.join('; ')}`);

  const stream = new BattleStream();
  const seed = input.seed || '1,2,3,4';
  const maxTurns = Number(input.maxTurns || 1000);
  let winner = null;
  let turns = 0;
  let requests = 0;

  stream.write(`>start ${JSON.stringify({formatid: format, seed})}`);
  stream.write(`>player p1 ${JSON.stringify({name: 'P1', team: p1.packed})}`);
  stream.write(`>player p2 ${JSON.stringify({name: 'P2', team: p2.packed})}`);

  for await (const output of stream) {
    const turnMatches = [...output.matchAll(/\|turn\|(\d+)/g)];
    for (const match of turnMatches) turns = Math.max(turns, Number(match[1]));

    const winMatch = output.match(/\|win\|([^\n]+)/);
    if (winMatch) winner = winMatch[1].trim();
    if (output.includes('|tie|')) winner = 'tie';

    if (turns > maxTurns) {
      stream.writeEnd();
      throw new Error(`battle exceeded maxTurns=${maxTurns}`);
    }

    if (output.includes('sideupdate\np1\n|request|')) {
      requests += 1;
      stream.write('>p1 default');
    }
    if (output.includes('sideupdate\np2\n|request|')) {
      requests += 1;
      stream.write('>p2 default');
    }

    if (winner) {
      stream.writeEnd();
      break;
    }
  }

  if (!winner) throw new Error('battle ended without a winner/tie message');
  return {format, winner, turns, requests, seed};
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
