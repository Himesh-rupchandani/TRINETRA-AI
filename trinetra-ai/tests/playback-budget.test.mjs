import { deepEq, eq, includes, loadTs, ok, readSource, suite, test } from './harness.mjs';
const { FrameEncoder } = loadTs('src/services/frameEncoder.ts');
const { frameAdmissionDelay, nextSampleDelay, controlledMjpegUrl } = loadTs('src/lib/anprScheduling.ts');
const snapshot = (changes={}) => ({status:'SCANNING',pending:false,sample_interval_ms:1000,result_age_ms:10,...changes});
const video = () => ({readyState:4,paused:false,videoWidth:1920,videoHeight:1080,currentTime:12});

async function withGlobals(values, run) {
  const saved = Object.fromEntries(Object.keys(values).map(key=>[key,globalThis[key]]));
  Object.assign(globalThis,values);
  try { await run(); }
  finally { for(const [key,value] of Object.entries(saved)) { if(value===undefined)delete globalThis[key]; else globalThis[key]=value; } }
}

suite('playback budget — encode away from the player and apply backpressure');
test('busy, shared and memory-limited cameras skip JPEG capture',()=>{
  eq(frameAdmissionDelay(snapshot({pending:true}),'browser:one'),750);
  eq(frameAdmissionDelay(snapshot({source_id:'browser:other'}),'browser:one'),1500);
  eq(frameAdmissionDelay(snapshot({resource_budget:{allowed:false}}),'browser:one'),5000);
  eq(frameAdmissionDelay(snapshot({status:'UNAVAILABLE'}),'browser:one'),5000);
  eq(frameAdmissionDelay(snapshot(),'browser:one'),0);
});
test('dropped frames or expensive capture slow sampling, not playback or image quality',()=>{
  eq(nextSampleDelay(snapshot(),20,0,30),1000);
  eq(nextSampleDelay(snapshot(),150,0,30),2500);
  eq(nextSampleDelay(snapshot(),20,8,30),2500);
  eq(nextSampleDelay(snapshot({sample_interval_ms:6000}),150,0,30),6000);
});
test('worker encoding keeps 1280px detail and only one bitmap in flight',async()=>{
  let options, transfers=0, terminated=0;
  const worker={postMessage(message,list){transfers++;eq(list[0],message.bitmap);queueMicrotask(()=>this.onmessage?.({data:{id:message.id,blob:new Blob(['jpeg'])}}));},terminate(){terminated++;}};
  await withGlobals({OffscreenCanvas:class{}, createImageBitmap:async (_video,opts)=>{options=opts;return {width:1280,height:720,close(){}};}},async()=>{
    const encoder=new FrameEncoder(()=>worker);
    const first=encoder.capture(video());
    eq(await encoder.capture(video()),null,'overlapping captures are dropped');
    const result=await first;
    eq(result.mediaTime,12);ok(result.blob.size>0);
    deepEq(options,{resizeWidth:1280,resizeHeight:720,resizeQuality:'high'});
    eq(transfers,1);
    encoder.dispose();eq(terminated,1);
    eq(await encoder.capture(video()),null);
  });
});
test('closing during bitmap creation frees it and never sends a late frame',async()=>{
  let resolveBitmap, closed=0, transferred=0;
  const worker={postMessage(){transferred++;},terminate(){}};
  await withGlobals({OffscreenCanvas:class{}, createImageBitmap:()=>new Promise(resolve=>{resolveBitmap=resolve;})},async()=>{
    const encoder=new FrameEncoder(()=>worker);
    const capture=encoder.capture(video());encoder.dispose();
    resolveBitmap({width:1280,height:720,close(){closed++;}});
    eq(await capture,null);eq(closed,1);eq(transferred,0);
  });
});
test('older-browser fallback reuses canvas storage rather than reallocating each sample',async()=>{
  let width=0,height=0,resizes=0;
  const canvas={get width(){return width;},set width(v){width=v;resizes++;},get height(){return height;},set height(v){height=v;resizes++;},getContext(){return {drawImage(){}};},toBlob(callback,type,quality){eq(type,'image/jpeg');eq(quality,.9);queueMicrotask(()=>callback(new Blob(['jpeg'])));}};
  await withGlobals({OffscreenCanvas:undefined,createImageBitmap:undefined,document:{createElement:()=>canvas}},async()=>{
    const encoder=new FrameEncoder(()=>{throw new Error('worker should not be created');});
    const source=video();ok(await encoder.capture(source));source.currentTime++;
    ok(await encoder.capture(source));eq(resizes,2);
    encoder.dispose();eq(width,1);eq(height,1);
  });
});
test('MJPEG toggles are commands; they cannot change the video URL/restart a recording',()=>{
  eq(controlledMjpegUrl('https://backend.test/api/cameras/a/live/detect','view',true),'https://backend.test/api/cameras/a/live/detect?viewer_id=view&analysis=true');
  const source=readSource('trinetra-ai/src/components/camera/CameraPlayer.tsx');
  includes(source,'setViewDetection(camera.id, viewerId, aiBoxes, ++detectionSequence.current');
  includes(source,'managedMjpeg, camera.id, isMjpeg, viewerId]');
  const overlay=readSource('trinetra-ai/src/components/camera/DetectionOverlay.tsx');
  includes(overlay,'capture.dispose()');
  includes(overlay,'frameAdmissionDelay(preflight');
});
