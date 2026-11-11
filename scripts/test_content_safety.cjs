'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {safeLocalPath,episodeScriptPath,trialInfo}=require('../dist/assets/content-safety.js');
for(const path of ['media/clip.mp4','media/web/clip-123.webp','archive/episodes/real-world/task/id/frames/0000.png'])assert.equal(safeLocalPath(path),path);
for(const path of ['https://example.test/a','//example.test/a','/data.js','../data.js','a/../data.js','a/%2e%2e/data.js','a/%252e%252e/data.js','a\\b','%2f%2fexample.test/a','javascript:alert(1)','data:text/html,x','a?view=1','a#x','a%00.png','a//b',null])assert.equal(safeLocalPath(path),'',String(path));
for(const path of ['episodes/id/data.js','episodes/real-world/task/id/data.js'])assert.equal(episodeScriptPath(path),path);
for(const path of ['assets/app.js','episodes/id/other.js','episodes/../data.js','https://example.test/episodes/id/data.js'])assert.equal(episodeScriptPath(path),'');
const documentType={createElement(tag){return {tag,children:[],append(...nodes){this.children.push(...nodes);},set innerHTML(value){throw Error('Dataset text must not be parsed as HTML');}};}};
const payload='<img src=x onerror=alert(1)>';
const node=trialInfo({scene:payload,turns:5,observations:6},'success',documentType);
assert.equal(node.children[0].textContent,'Scene '+payload);
assert.deepEqual(node.children.map(n=>n.tag),['b','span','span']);
assert.equal(node.children[2].textContent,'5 turns · 6 observations');
assert.equal(trialInfo({scene:1},'" onclick="x',documentType).children[1].className,'trial-outcome pending');
const app=fs.readFileSync('dist/assets/app.js','utf8'),archive=fs.readFileSync('dist/archive/app.js','utf8');
assert(app.includes('ShowcaseContent.trialInfo(episode, outcomeOf(episode))'));
assert(archive.indexOf('episodeScriptPath(item.data_file)')<archive.indexOf("document.createElement('script')"));
for(const [file,helper] of [['dist/index.html','assets/content-safety.js'],['dist/archive/index.html','../assets/content-safety.js']]){
 const html=fs.readFileSync(file,'utf8');assert(html.indexOf(helper)<html.indexOf('src="'+(file.includes('/archive/')?'':'assets/')+'app.js'));
}
console.log('PASS local paths, encoded traversal, remote script rejection, literal dataset text and frontend integration');
