import assert from 'node:assert/strict';
import test from 'node:test';
import {postParts,postRow,replyRow,wantRow} from '../web 7M/src/components/forum.js';

test('old body-only posts become readable titles without losing long text',()=>{
  assert.deepEqual(postParts('摄影入门互助\n周末一起练习'),{title:'摄影入门互助',body:'周末一起练习'});
  const text='长'.repeat(100);assert.equal(postParts(text).body,text);
});
test('post titles and summaries escape markup; unavailable metrics are never invented',()=>{
  const html=postRow({id:1,user_id:2,nickname:'<img onerror=x>',body:'<script>bad</script>\n正文',topic:'交换人生',created:1,replies:3});
  assert.match(html,/#forum-post\/1/);assert.match(html,/3 回复/);
  assert.doesNotMatch(html,/<script>|<img onerror|浏览|认证|置顶/);
});
test('replies preserve target attribution and have native collapse controls',()=>{
  const html=replyRow({id:9,user_id:2,nickname:'同学',parent_nickname:'<b>甲</b>',body:'真实回复',created:1},21);
  assert.match(html,/<details[^>]*open/);assert.match(html,/21 楼/);
  assert.match(html,/&lt;b&gt;甲&lt;\/b&gt;/);assert.match(html,/forum-target-reply/);
});
test('wants retain matching and friend-request actions without pretending to have replies',()=>{
  const html=wantRow({id:1,user_id:3,nickname:'同学',keyword:'数据结构',budget:5000,matches:[{}],created:1,status:'open'},2);
  assert.match(html,/want-respond/);assert.match(html,/forum-want\/1/);
  assert.doesNotMatch(html,/回复|浏览/);
});
