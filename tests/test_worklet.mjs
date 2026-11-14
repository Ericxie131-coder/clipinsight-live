import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const messages=[];
let Capture;
class AudioWorkletProcessor { constructor(){this.port={onmessage:null,postMessage:x=>messages.push(x)};} }
const scope=vm.createContext({AudioWorkletProcessor,Int16Array,Math,registerProcessor:(name,klass)=>{Capture=klass;}});
vm.runInContext(fs.readFileSync(new URL('../web/pcm-worklet.js',import.meta.url),'utf8'),scope);
const capture=new Capture();
capture.process([[new Float32Array(1600).fill(.5)]]);
capture.process([[new Float32Array(7).fill(.25)]]);
assert.equal(messages.length,1);
capture.port.onmessage({data:{type:'flush'}});
assert.equal(messages[1].byteLength,14,'seven remaining samples must be sent');
assert.equal(messages[2].type,'flushed','ack must follow the tail');
assert.equal(new Int16Array(messages[0])[0],16384);
capture.process([[new Float32Array(1600).fill(.5)]]);
assert.equal(messages.length,3,'no audio after EOF');
console.log('PCM tail flushing and EOF ordering passed');
