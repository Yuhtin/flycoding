import test from 'node:test';
import assert from 'node:assert/strict';
import * as p from '../src/flycodex/web/presentation.mjs';

test('projection translates exact known messages and preserves unknown and originals', () => {
  const entries = [{original: 'Olá', english: 'Hello'}];
  const event = {type:'item.completed',item:{type:'agent_message',text:'Olá'}};
  const before = JSON.stringify(event);
  assert.deepEqual(p.translate('Olá', entries), {text:'Hello', translated:true});
  assert.deepEqual(p.translate('Unmatched', entries), {text:'Unmatched', translated:false});
  assert.match(p.readableEvent(event, '', entries), /English translation.*Hello/s);
  assert.equal(JSON.stringify(event), before);
  assert.equal(p.translatePrompt('Corrija a função de desconto, preservando os testes.').text, 'Fix the discount function while preserving the tests.');
});

test('event coalescing and prior evaluation do not mutate records', () => {
  const events = [{type:'item.started', item:{id:'cmd',type:'command_execution',command:'python /private/work/test.py',exit_code:null}}, {type:'item.completed',item:{id:'cmd',type:'command_execution',command:'python /private/work/test.py',aggregated_output:'ok',exit_code:0}}, {type:'turn.completed'}];
  const before = JSON.stringify(events);
  const result = p.coalesceItemEvents(events);
  assert.equal(result.length, 2);
  assert.match(p.readableEvent(result[0], '/private/work'), /python test.py.*ok.*exit 0/s);
  assert.equal(JSON.stringify(events), before);
  const baseline = {passed:1,total:5};
  const evaluated = {passed:5,total:5};
  const a = {baseline, turns:[{evaluation:evaluated},{}]};
  assert.equal(p.evaluationForTurn(a,a.turns[1]), evaluated);
  assert.equal(p.evaluationForTurn(a,a.turns[0],false), baseline);
});

test('condensed replay is deterministic, pausable, resettable, and history cancels it', () => {
  const entries = Array.from({length:9},(_,i)=>({key:`a:${i}`,turn:{events:[{}, {}, {}, {}]}}));
  const before = JSON.stringify(entries);
  const replay = p.createReplay(entries);
  assert.equal(replay.frame().active,false);
  replay.play();
  assert.equal(replay.frame().duration,54000);
  assert.equal(replay.frame().phase,'working');
  assert.equal(replay.frame().completed,0);
  replay.advance(4200);
  assert.equal(replay.frame().phase,'feedback');
  assert.equal(replay.frame().completed,1);
  replay.pause(); replay.advance(6000);
  assert.equal(replay.frame().elapsed,4200);
  replay.play(); replay.advance(1800);
  assert.equal(replay.frame().index,1);
  replay.reset();
  assert.equal(replay.frame().elapsed,0);
  assert.equal(replay.frame().playing,false);
  replay.play(); replay.advance(54000);
  assert.equal(replay.frame().phase,'complete');
  assert.equal(replay.frame().completed,9);
  assert.equal(replay.frame().playing,false);
  replay.select('a:2');
  assert.equal(replay.frame().active,false);
  assert.equal(replay.frame().selection,'a:2');
  assert.equal(JSON.stringify(entries),before);
});
