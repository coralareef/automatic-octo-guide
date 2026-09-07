#!/usr/bin/env node
'use strict';

const fs = require('fs');
const {Teams, TeamValidator} = require('pokemon-showdown');

function readInput() {
  const raw = fs.readFileSync(0, 'utf8').trim();
  return raw ? JSON.parse(raw) : {};
}

function validate(input) {
  const format = input.format || 'gen9ou';
  if (typeof input.team !== 'string' || !input.team.trim()) {
    throw new Error('team must be a non-empty Showdown export/packed/JSON string');
  }
  const parsed = Teams.import(input.team);
  if (!parsed) throw new Error('could not parse team');
  const validator = new TeamValidator(format);
  const problems = validator.validateTeam(parsed) || [];
  return {
    format,
    valid: problems.length === 0,
    problems,
    packed: Teams.pack(parsed),
    export: Teams.export(parsed),
    pokemon: parsed.map(set => set.species),
  };
}

function main() {
  const command = process.argv[2] || 'validate';
  try {
    const input = readInput();
    let output;
    if (command === 'validate') {
      output = validate(input);
    } else {
      throw new Error(`unknown command: ${command}`);
    }
    process.stdout.write(JSON.stringify(output));
  } catch (error) {
    process.stderr.write(String(error && error.stack ? error.stack : error));
    process.exitCode = 1;
  }
}

main();
