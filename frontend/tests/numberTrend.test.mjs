import test from 'node:test';
import assert from 'node:assert/strict';
import {trendHistory,trendRows} from '../src/utils/numberTrend.js';

test('trend excludes target/future draws and orders the visible history chronologically',()=>{
 const history=[{issue:'26117',front:[2],back:[2]},{issue:'26116',front:[2],back:[]},{issue:'26118',front:[2],back:[2]},{issue:'26115',front:[],back:[2]}];
 const visible=trendHistory(history,'26117');
 assert.deepEqual(visible.map(d=>d.issue),['26115','26116']);
 assert.deepEqual(trendHistory(history,'26117',1).map(d=>d.issue),['26116']);
 assert.equal(history[0].issue,'26117');
 const rows=trendRows(visible,{front:[2],back:[2,3]});
 assert.deepEqual(rows.map(r=>[r.zone,r.count,r.omission]),[['front',1,'0'],['back',1,'1'],['back',0,'≥2']]);
});
