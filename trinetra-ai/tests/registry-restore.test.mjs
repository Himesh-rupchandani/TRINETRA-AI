import { eq, includes, excludes, loadTs, readSource, suite, test } from './harness.mjs';
let response = { status:'success', message:'Restored entries only', total_cameras:31, added_count:26, cameras:[] };
let invalidations = 0;
const calls = [];
const { ingestService } = loadTs('src/services/ingestService.ts', {
  './api': {
    isMockMode:false, backendUrl:(path)=>path,
    get:async (path)=>{ calls.push(['get',path]); return response; },
    post:async (path)=>{ calls.push(['post',path]); return response; },
  },
  './adapters': { toCamera:(value)=>value, invalidateCameraDirectory:()=>{ invalidations++; } },
  '@/mocks/mockBackend': {},
});

suite('camera registry — restore metadata without synthetic activity');
test('restore uses the metadata-only endpoint and invalidates camera names after success',async()=>{
  calls.length=0; invalidations=0;
  response={status:'success',message:'Restored entries only',total_cameras:31,added_count:26,cameras:[]};
  const result=await ingestService.restoreCameraList();
  eq(result.added_count,26);
  eq(calls[0][0],'post');eq(calls[0][1],'/ingest/restore-camera-list');
  eq(calls.length,1);eq(invalidations,1);
});
test('failed catalogue sync does not pretend a new camera list exists',async()=>{
  invalidations=0;
  response={status:'warning',message:'Sign-in page, not JSON',total_cameras:5,synced_count:0,cameras:[]};
  const result=await ingestService.syncCatalogue();
  eq(result.status,'warning');eq(invalidations,0);
});
test('the UI shows restore/sync results instead of unconditionally reloading',()=>{
  const source=readSource('trinetra-ai/src/pages/Ingest.tsx');
  includes(source,'Restore 30-camera list');
  includes(source,"if (result.status === 'success') refreshCameras()");
  includes(source,'notice.message');
  excludes(source,'window.location.reload()');
});
