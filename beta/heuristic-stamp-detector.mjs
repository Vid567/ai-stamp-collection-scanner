import { regionsToPhysicalStampGroups } from './detection-result.mjs';
const MAX_SIDE=1000,MAX_REGIONS=120;
function colourDistance(a,b){const dr=a[0]-b[0],dg=a[1]-b[1],db=a[2]-b[2];return Math.sqrt(dr*dr+dg*dg+db*db)}

// Real photos are almost never lit perfectly evenly: phone-camera shots of an album page
// commonly have a soft light/shadow gradient or lens vignetting across the frame. A single
// global "page background colour" can't tell that gradient apart from a genuine stamp, so it
// used to flood large parts of the photo as false foreground (and, worse, chain-connect real
// stamps to that false region so they got discarded together as "too big to be a stamp").
// Estimating the background *locally* (a heavily blurred copy of the photo) fixes that: it
// tracks the gradient but washes out anything stamp-sized, so real detail still stands out.
function localBackgroundField(sourceCanvas,w,h){
  const sw=Math.max(8,Math.round(w/18)),sh=Math.max(8,Math.round(h/18));
  const small=document.createElement('canvas');small.width=sw;small.height=sh;
  const sctx=small.getContext('2d',{willReadFrequently:true});
  sctx.imageSmoothingEnabled=true;sctx.imageSmoothingQuality='high';
  sctx.drawImage(sourceCanvas,0,0,sw,sh);
  const big=document.createElement('canvas');big.width=w;big.height=h;
  const bctx=big.getContext('2d',{willReadFrequently:true});
  bctx.imageSmoothingEnabled=true;bctx.imageSmoothingQuality='high';
  bctx.drawImage(small,0,0,w,h);
  return bctx.getImageData(0,0,w,h).data;
}
function buildMask(sourceCanvas,im,w,h){
  const d=im.data,bgField=localBackgroundField(sourceCanvas,w,h),m=new Uint8Array(w*h),dist=new Float32Array(w*h);
  let sum=0;
  for(let p=0;p<w*h;p++){const i=p*4,dd=colourDistance([d[i],d[i+1],d[i+2]],[bgField[i],bgField[i+1],bgField[i+2]]);dist[p]=dd;sum+=dd}
  const th=Math.max(22,Math.min(60,sum/(w*h)*1.6));
  for(let p=0;p<w*h;p++){const i=p*4,r=d[i],g=d[i+1],b=d[i+2],mx=Math.max(r,g,b),mn=Math.min(r,g,b),sat=mx?(mx-mn)/mx:0;m[p]=(dist[p]>th||(sat>.18&&dist[p]>th*.55))?1:0}
  return m;
}
function makeGrid(mask,w,h,cell=3,ratio=.15){const gw=Math.ceil(w/cell),gh=Math.ceil(h/cell),g=new Uint8Array(gw*gh);for(let gy=0;gy<gh;gy++)for(let gx=0;gx<gw;gx++){let a=0,n=0;for(let y=gy*cell;y<Math.min(h,(gy+1)*cell);y++)for(let x=gx*cell;x<Math.min(w,(gx+1)*cell);x++){a+=mask[y*w+x];n++}g[gy*gw+gx]=a/Math.max(1,n)>ratio?1:0}return{grid:g,cell,gw,gh}}
// Lenient pass: only drops single-cell noise specks. Deliberately does NOT reject boxes by
// size/aspect yet, because a whole row of pre-printed album slots is one connected component
// at this stage (their frame lines touch) and must survive to be split apart below — filtering
// too early is what silently dropped genuine stamps whenever they shared a border with an
// empty slot next to them.
function componentsRaw(grid,cell,gw,gh,w,h){const seen=new Uint8Array(grid.length),out=[],stack=[];for(let sy=0;sy<gh;sy++)for(let sx=0;sx<gw;sx++){let s=sy*gw+sx;if(!grid[s]||seen[s])continue;let x0=sx,x1=sx,y0=sy,y1=sy,c=0;seen[s]=1;stack.push(s);while(stack.length){const p=stack.pop(),x=p%gw,y=Math.floor(p/gw);c++;x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);for(const[dx,dy]of[[1,0],[-1,0],[0,1],[0,-1]]){const nx=x+dx,ny=y+dy;if(nx<0||nx>=gw||ny<0||ny>=gh)continue;const np=ny*gw+nx;if(grid[np]&&!seen[np]){seen[np]=1;stack.push(np)}}}if(c<3)continue;const bw=(x1-x0+1)*cell,bh=(y1-y0+1)*cell;out.push({x:x0*cell,y:y0*cell,width:Math.min(w-x0*cell,bw),height:Math.min(h-y0*cell,bh)})}return out}
function boxDensity(grid,cell,gw,gh,box){const gx0=Math.max(0,Math.floor(box.x/cell)),gx1=Math.min(gw-1,Math.ceil((box.x+box.width)/cell)-1),gy0=Math.max(0,Math.floor(box.y/cell)),gy1=Math.min(gh-1,Math.ceil((box.y+box.height)/cell)-1);let filled=0,total=0;for(let gy=gy0;gy<=gy1;gy++)for(let gx=gx0;gx<=gx1;gx++){total++;if(grid[gy*gw+gx])filled++}return total?filled/total:0}
function intersection(a,b){const x1=Math.max(a.x,b.x),y1=Math.max(a.y,b.y),x2=Math.min(a.x+a.width,b.x+b.width),y2=Math.min(a.y+a.height,b.y+b.height);return Math.max(0,x2-x1)*Math.max(0,y2-y1)}
function iou(a,b){const i=intersection(a,b);return i/Math.max(1,a.width*a.height+b.width*b.height-i)}
function overlap(a,b){return intersection(a,b)/Math.max(1,Math.min(a.width*a.height,b.width*b.height))}
function dedupe(boxes){const sorted=[...boxes].sort((a,b)=>(b.density||0)-(a.density||0)),kept=[];for(const b of sorted){if(kept.some(k=>iou(b,k)>.30||overlap(b,k)>.72))continue;kept.push(b)}return kept.sort((a,b)=>a.y-b.y||a.x-b.x)}
function median(v){const a=[...v].filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return 0;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2}
function projection(mask,w,h,box,axis){const x0=Math.max(0,Math.floor(box.x)),x1=Math.min(w,Math.ceil(box.x+box.width)),y0=Math.max(0,Math.floor(box.y)),y1=Math.min(h,Math.ceil(box.y+box.height)),len=axis==='x'?x1-x0:y1-y0,p=new Array(len).fill(0);if(axis==='x'){for(let x=x0;x<x1;x++)for(let y=y0;y<y1;y++)p[x-x0]+=mask[y*w+x]}else{for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++)p[y-y0]+=mask[y*w+x]}return p}
function smooth(v,r=2){return v.map((_,i)=>{let s=0,n=0;for(let j=Math.max(0,i-r);j<=Math.min(v.length-1,i+r);j++){s+=v[j];n++}return s/n})}
function valleyCuts(v,expected){const s=smooth(v,2),mx=Math.max(1,...s),minGap=Math.max(5,Math.floor(v.length/(expected+1)*.42)),c=[];for(let i=Math.floor(v.length*.08);i<Math.ceil(v.length*.92);i++){if(s[i]<=mx*.20&&s[i]<=s[i-1]&&s[i]<=s[i+1]&&(!c.length||i-c[c.length-1]>=minGap))c.push(i)}if(c.length<=expected-1)return c;return c.sort((a,b)=>s[a]-s[b]).slice(0,expected-1).sort((a,b)=>a-b)}
function splitByCuts(box,cuts,axis){if(!cuts.length)return[box];const points=[0,...cuts,axis==='x'?box.width:box.height],out=[];for(let i=0;i<points.length-1;i++){const a=points[i],b=points[i+1];if(b-a<4)continue;out.push(axis==='x'?{...box,x:box.x+a,width:b-a}:{...box,y:box.y+a,height:b-a})}return out}
function estimateStampSize(seed,w,h){const good=seed.filter(b=>b.width/w>=.085&&b.width/w<=.18&&b.height/h>=.085&&b.height/h<=.22);return{mw:median(good.map(b=>b.width))||0,mh:median(good.map(b=>b.height))||0}}
function splitMerged(box,mask,w,h,mw,mh,depth=0){if(depth>2)return[box];const nx=Math.max(1,Math.round(box.width/mw)),ny=Math.max(1,Math.round(box.height/mh));if(nx===1&&ny===1)return[box];let parts=[box];if(nx>1&&nx<=6){const cuts=valleyCuts(projection(mask,w,h,box,'x'),nx);if(cuts.length)parts=splitByCuts(box,cuts,'x')}const after=[];for(const p of parts){const py=Math.max(1,Math.round(p.height/mh));if(py>1&&py<=6){const cuts=valleyCuts(projection(mask,w,h,p,'y'),py);if(cuts.length){after.push(...splitByCuts(p,cuts,'y'));continue}}after.push(p)}if(after.length===1)return[box];return after.flatMap(p=>p.width>mw*1.65||p.height>mh*1.65?splitMerged(p,mask,w,h,mw,mh,depth+1):[p])}
// Split any box that's clearly several album slots merged together (their printed frame
// lines touch, so they flood-fill as one shape), then keep only pieces that are close to a
// real single-stamp size. Falls back to the plain area/aspect rule when no size estimate
// is available yet (e.g. a page with only one stamp on it).
function splitAndFilter(raw,mask,w,h,grid,cell,gw,gh){
  const {mw,mh}=estimateStampSize(raw,w,h);
  const pieces=raw.flatMap(b=>(mw&&mh&&(b.width>mw*1.55||b.height>mh*1.55))?splitMerged(b,mask,w,h,mw,mh):[b]);
  return pieces.filter(b=>{
    const area=(b.width*b.height)/(w*h),asp=b.width/Math.max(1,b.height);
    if(b.width<w*.07||b.height<h*.07)return false;
    if(area>.30||asp<.28||asp>3.2)return false;
    if(mw&&mh&&(b.width<mw*.45||b.height<mh*.45||b.width>mw*1.7||b.height>mh*1.7))return false;
    return boxDensity(grid,cell,gw,gh,b)>=.20;
  }).map(b=>({...b,density:boxDensity(grid,cell,gw,gh,b)}));
}
function denseAlbum(mask,w,h){const fine=makeGrid(mask,w,h,2,.20);let seed=dedupe(splitAndFilter(componentsRaw(fine.grid,fine.cell,fine.gw,fine.gh,w,h),mask,w,h,fine.grid,fine.cell,fine.gw,fine.gh));return seed}
function cropStats(ctx,b){const c=document.createElement('canvas');c.width=10;c.height=10;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(ctx.canvas,b.x,b.y,b.width,b.height,0,0,10,10);const d=x.getImageData(0,0,10,10).data,gray=[],rgb=[0,0,0];for(let i=0;i<100;i++){const p=i*4;rgb[0]+=d[p];rgb[1]+=d[p+1];rgb[2]+=d[p+2];gray.push((d[p]+d[p+1]+d[p+2])/3)}const mean=gray.reduce((a,v)=>a+v,0)/100,std=Math.sqrt(gray.reduce((a,v)=>a+(v-mean)**2,0)/100)||1,signature=gray.map(v=>(v-mean)/std);let hash='';for(let y=0;y<10;y++)for(let xx=0;xx<9;xx++)hash+=gray[y*10+xx]>gray[y*10+xx+1]?'1':'0';return{hash,colour:rgb.map(v=>v/100),signature}}
function hamming(a,b){let n=0;for(let i=0;i<Math.min(a.length,b.length);i++)if(a[i]!==b[i])n++;return n+Math.abs(a.length-b.length)}
function sigDist(a,b){let s=0;for(let i=0;i<Math.min(a.length,b.length);i++)s+=(a[i]-b[i])**2;return Math.sqrt(s/Math.max(1,Math.min(a.length,b.length)))}
// A mounted stamp carries real ink: engraving lines, a portrait, numerals, colour. An empty
// pre-printed album slot is almost blank apart from a thin frame and a small caption, so its
// interior (once the frame itself is cropped away) reads as near-uniform. This is what lets
// the detector tell "there's a stamp here" apart from "this position is still empty" instead
// of treating every printed slot on the page as an owned stamp.
function interiorRichness(ctx,b){const insetX=b.width*.16,insetY=b.height*.16,x=Math.max(0,Math.round(b.x+insetX)),y=Math.max(0,Math.round(b.y+insetY)),w=Math.max(2,Math.round(b.width-2*insetX)),h=Math.max(2,Math.round(b.height-2*insetY));const data=ctx.getImageData(x,y,w,h).data;let sum=0,sumSq=0,n=0;for(let i=0;i<data.length;i+=4){const gr=(data[i]+data[i+1]+data[i+2])/3;sum+=gr;sumSq+=gr*gr;n++}const mean=sum/Math.max(1,n),variance=Math.max(0,sumSq/Math.max(1,n)-mean*mean);return Math.sqrt(variance)}
const MIN_INTERIOR_STD=20;
export async function detectStampGroups(blob){
  const bm=await createImageBitmap(blob),scale=Math.min(1,MAX_SIDE/Math.max(bm.width,bm.height)),w=Math.max(1,Math.round(bm.width*scale)),h=Math.max(1,Math.round(bm.height*scale)),canvas=document.createElement('canvas');
  canvas.width=w;canvas.height=h;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});
  ctx.drawImage(bm,0,0,w,h);
  bm.close?.();
  const imageData=ctx.getImageData(0,0,w,h),mask=buildMask(canvas,imageData,w,h),coarse=makeGrid(mask,w,h,4,.15);
  let standard=dedupe(splitAndFilter(componentsRaw(coarse.grid,coarse.cell,coarse.gw,coarse.gh,w,h),mask,w,h,coarse.grid,coarse.cell,coarse.gw,coarse.gh));
  let dense=denseAlbum(mask,w,h),boxes=standard,mode='standard';
  if((standard.length<15&&dense.length>standard.length*1.45)||(dense.length>=30&&dense.length>standard.length*1.15)){boxes=dense;mode='dense-album'}
  if(!boxes.length||boxes.length>MAX_REGIONS){boxes=[{x:0,y:0,width:w,height:h,fallback:true,density:1}];mode='fallback'}
  let filtered=boxes;
  if(mode!=='fallback'){
    const rich=boxes.filter(b=>interiorRichness(ctx,b)>=MIN_INTERIOR_STD);
    // Never let an over-strict filter erase a whole photo's results — fall back to the
    // unfiltered boxes so the user still gets rows to review rather than nothing at all.
    if(rich.length)filtered=rich;
  }
  const regions=filtered.map(b=>({...b,normalized:{x:b.x/w,y:b.y/h,width:b.width/w,height:b.height/h},...cropStats(ctx,b)})),groups=regionsToPhysicalStampGroups(regions);
  return{groups,detected:mode!=='fallback',totalDetected:regions.length,mode};
}
